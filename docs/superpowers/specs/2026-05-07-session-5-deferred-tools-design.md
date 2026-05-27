# Session 5 — Deferred Tools Design

## Goal

Add the 4 deferred agent tools: `fetch_geopolitical_risk`, `detect_drift`, `evaluate_features`, and `backtest`. Each tool plugs into the existing `ToolRegistry` and `AgentContext` pattern established in Session 4.

## Architecture

New domain modules handle non-trivial logic; `src/agent/tools.py` holds thin wrappers that register each tool and glue results into `AgentContext`. Simple tools (drift, SHAP) stay inline in `tools.py`.

```
src/data/gpr.py          — GPR fetch + in-memory TTL cache
src/eval/backtest.py     — walk-forward engine
src/agent/tools.py       — 4 new @registry.tool wrappers
                           (detect_drift and evaluate_features inline)
```

New dependencies added to `pyproject.toml`:
- `tabpfn-extensions>=0.0.14` — SHAP for TabPFN
- `openpyxl>=3.1.0` — Excel parser for GPR `.xls` download (pandas requires this for `.xls`/`.xlsx`)

No new API routes or DB schema changes.

---

## AgentContext additions

```python
@dataclass
class AgentContext:
    # existing fields ...
    backtest_result: dict[str, Any] | None = None
    drift_result: dict[str, Any] | None = None
    shap_result: dict[str, Any] | None = None
    # Stores fitted classifier + test split for evaluate_features
    _regime_clf: Any | None = None          # OilRegimeClassifier instance after fit
    _regime_X_test: pd.DataFrame | None = None
    _regime_y_test: pd.Series | None = None
    # Lightweight fetch manifest for auditability
    data_manifest: dict[str, Any] = field(default_factory=dict)
```

`_regime_clf`, `_regime_X_test`, and `_regime_y_test` are set by `run_tabpfn(task='regime')` so `evaluate_features` can call SHAP without refitting.

---

## Run result shape

`loop.py` persists all tool outputs when marking a run COMPLETED:

```python
run.result = {
    "regime": context.regime_result,
    "direction": context.direction_result,
    "drift": context.drift_result,
    "feature_importance": context.shap_result,
    "backtest": context.backtest_result,
    "summary": last_text,
    "usage": usage,
    "data_manifest": context.data_manifest,
}
```

Raw fetched series stay in `AgentContext` during the run only — not persisted to DB. The `data_manifest` provides a lightweight audit record:

```python
{
  "data_sources": {
    "CL=F":  {"rows": 250, "start": "2023-01-01", "end": "2023-06-30", "provider": "yfinance"},
    "GPR":   {"rows": 125, "start": "2023-01-01", "end": "2023-06-30", "provider": "matteoiacoviello.com"}
  }
}
```

`fetch_data` and `fetch_geopolitical_risk` both write into `context.data_manifest["data_sources"]` after fetching.

> **Note on data freshness:** Market prices are mostly stable but FRED/macro series can be revised. A persistent time-series cache (symbol, date, value, fetched_at, provider, vintage) is deferred to a later session; for now the manifest records what was fetched and when.

---

## Module: `src/data/gpr.py`

Fetches the daily Geopolitical Risk (GPR) index from Matteo Iacoviello's Fed page.

**Cache:** module-level `dict[str, tuple[datetime, pd.Series]]`. TTL defaults to 24h; overridable via `GPR_CACHE_TTL_HOURS` in `.env`. URL overridable via `GPR_DATA_URL` in `Settings`.

**Parsing:** The source file is an Excel workbook (`.xls`). Parsed with `pd.read_excel(..., engine="openpyxl")`. Expected columns: `date` and `GPRD` (daily GPR). Column names validated on load; raises `ValueError` if schema changes.

**Interface:**
```python
GPR_DATA_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"

def fetch_gpr_series(start: str, end: str) -> pd.Series:
    """Fetch daily GPR index. Returns pd.Series named 'GPR', indexed by date, trimmed to [start, end]."""
```

**Tool wrapper** (`fetch_geopolitical_risk`):
```python
@registry.tool(parameters={
    "type": "object",
    "properties": {},
    "required": []
})
def fetch_geopolitical_risk(context: AgentContext) -> dict[str, Any]:
    """Fetch the Geopolitical Risk (GPR) index and add it to context signals."""
    series = fetch_gpr_series(context.date_range_start, context.date_range_end)
    context.signals["GPR"] = series
    context.data_manifest.setdefault("data_sources", {})["GPR"] = {
        "rows": len(series),
        "start": context.date_range_start,
        "end": context.date_range_end,
        "provider": "matteoiacoviello.com",
    }
    return {"fetched": {"GPR": len(series)}}
```

**Settings additions:**
```python
gpr_data_url: str = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
gpr_cache_ttl_hours: int = 24
```

---

## Module: `src/eval/backtest.py`

Walk-forward evaluation using an expanding window.

**Interface:**
```python
def walk_forward_backtest(
    features: pd.DataFrame,
    wti: pd.Series,
    spy: pd.Series,
    horizon: int = 20,
    step: int = 20,
    min_train: int = 120,
) -> dict[str, Any]:
```

**Label generation per window** — uses the same helpers as `tools.py` to avoid drift between training and eval:
```python
from src.agent.tools import _make_regime_labels, _make_direction_labels
```

At each window split point `t`:
- Regime labels: `_make_regime_labels(wti, features.index)` → slice `[:t]` for train, `[t:t+horizon]` for test
- Direction labels: `_make_direction_labels(wti, features.index, horizon=horizon)` → align to `features.index` via `.intersection()`, then slice

**Algorithm:**
```
for t in range(min_train, len(features) - horizon, step):
    X_train, X_test = features[:t], features[t:t+horizon]
    y_regime_train = regime_labels[:t]
    y_regime_test  = regime_labels[t:t+horizon]
    y_dir_train    = direction_labels[:t].reindex(X_train.index).dropna()
    y_dir_test     = direction_labels[t:t+horizon].reindex(X_test.index).dropna()

    # Regime accuracy
    clf = OilRegimeClassifier(n_estimators=8)
    clf.fit(X_train, y_regime_train)
    regime_correct += (clf.predict(X_test) == y_regime_test).sum()
    regime_total   += len(y_regime_test)

    # Direction strategy returns
    dir_clf = DirectionClassifier(n_estimators=8)
    dir_clf.fit(X_train.loc[y_dir_train.index], y_dir_train)
    pred_dir = dir_clf.predict(X_test.loc[y_dir_test.index])
    wti_returns = wti.pct_change().reindex(y_dir_test.index)
    strategy_returns.extend(wti_returns.where(pred_dir == "up", 0).tolist())
    spy_returns.extend(spy.pct_change().reindex(y_dir_test.index).tolist())
```

**Sharpe calculation:**
```python
def _annualised_sharpe(returns: list[float]) -> float:
    s = pd.Series(returns).dropna()
    if s.std() == 0:
        return 0.0
    return float((s.mean() / s.std()) * (252 ** 0.5))
```

**Output:**
```python
{
  "regime_accuracy": 0.71,
  "strategy_sharpe": 1.43,
  "benchmark_sharpe": 0.89,
  "n_windows": 12,
  "date_range": ["2023-01-01", "2023-06-30"]
}
```

**Tool wrapper** (`backtest`):
- Requires `context.features`, `context.signals["CL=F"]`, `context.signals["SPY"]`
- Calls `walk_forward_backtest(...)`, stores result in `context.backtest_result`
- Parameters: `horizon` (default 20), `step` (default 20)

---

## Tool: `detect_drift` (inline in `tools.py`)

Splits `context.features` into historical (first 80%) and recent (last 20%). Requires `context.features` to be set.

**KS test** — `scipy.stats.ks_2samp(historical[col], recent[col])` per feature. Flags features where p-value < 0.05.

**PSI helper:**
```python
def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    breakpoints = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    expected_dist = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_dist   = np.histogram(actual,   bins=breakpoints)[0] / len(actual)
    # clip to avoid log(0)
    expected_dist = np.clip(expected_dist, 1e-4, None)
    actual_dist   = np.clip(actual_dist,   1e-4, None)
    return float(np.sum((actual_dist - expected_dist) * np.log(actual_dist / expected_dist)))
```

PSI computed as mean across all feature columns.

**Drift thresholds:** PSI ≥ 0.2 = significant, 0.1–0.2 = moderate, < 0.1 = stable. `drift_detected = psi_score >= 0.1`.

**Output stored in** `context.drift_result`:
```python
{
  "drift_detected": True,
  "psi_score": 0.24,
  "drifted_features": ["CL=F_ret_20d", "DX-Y.NYB_vol_60d"],
  "ks_results": {
    "CL=F_ret_20d": {"statistic": 0.31, "p_value": 0.003},
    "DX-Y.NYB_vol_60d": {"statistic": 0.28, "p_value": 0.012}
  }
}
```

---

## Tool: `evaluate_features` (inline in `tools.py`)

Requires `run_tabpfn(task='regime')` to have been called first — the tool uses `context._regime_clf`, `context._regime_X_test`, and `context._regime_y_test` set by that call.

**`run_tabpfn` change:** After fitting, store:
```python
context._regime_clf    = regime_clf
context._regime_X_test = X_test
context._regime_y_test = y_train  # labels for test split
```

**SHAP helper** — wrapped behind a single function so tests can mock it:
```python
def _compute_shap_values(clf: OilRegimeClassifier, X: pd.DataFrame) -> np.ndarray:
    from tabpfn_extensions import interpretability
    explainer = interpretability.TabPFNExplainer(clf.estimators_[0])
    return explainer.shap_values(X)  # shape: (n_samples, n_features, n_classes)
```

Mean absolute SHAP across samples and classes gives per-feature importance.

**Output stored in** `context.shap_result`:
```python
{
  "top_features": [
    {"name": "CL=F_ret_20d",      "importance": 0.42},
    {"name": "DX-Y.NYB_ret_20d",  "importance": 0.31},
    {"name": "XLE_vol_60d",        "importance": 0.18}
  ],
  "n_features_evaluated": 45
}
```

Returns top 10 features by default; `top_n` parameter controls this.

---

## Updated System Prompt

`loop.py` system prompt extended to include all 9 steps:

```
1. fetch_data — pull WTI, DXY, XLE, SPY price series and INDPRO macro data
2. fetch_geopolitical_risk — add GPR index to signals
3. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]
4. detect_drift — check if recent feature distributions have shifted
5. run_tabpfn with task='regime' — classify the current oil market regime
6. run_tabpfn with task='direction' — predict WTI price direction
7. evaluate_features — compute SHAP feature importances
8. backtest — walk-forward regime accuracy + direction strategy Sharpe vs SPY
9. explain_prediction — pass regime, direction, confidence, and key feature names
```

---

## Testing

- `tests/test_gpr_connector.py` — mock `requests.get` / `pd.read_excel`, verify TTL cache hit/miss, date trimming, column validation error
- `tests/test_backtest.py` — synthetic features + WTI/SPY series, verify output keys, `n_windows > 0`, Sharpe is a float
- `tests/test_deferred_tools.py`:
  - `detect_drift`: inject features with known distribution shift, verify `drift_detected=True` and drifted feature names
  - `evaluate_features`: mock `_compute_shap_values` to return a fixed array; verify top_features shape and ordering
  - `backtest` tool wrapper: mock `walk_forward_backtest`, verify `context.backtest_result` is set
  - `fetch_geopolitical_risk` tool wrapper: mock `fetch_gpr_series`, verify `context.signals["GPR"]` and manifest entry
- All tests run without network access (HTTP mocked via `unittest.mock.patch`)

---

## Files Changed

| File | Action |
|---|---|
| `src/data/gpr.py` | Create |
| `src/eval/backtest.py` | Create |
| `src/agent/tools.py` | Add 4 tool wrappers, `_psi` helper, `_compute_shap_values` helper; extend `AgentContext`; update `run_tabpfn` to store `_regime_clf/_regime_X_test/_regime_y_test`; update `fetch_data` to write data manifest |
| `src/agent/loop.py` | Extend system prompt; extend `run.result` to include all 5 new fields + `data_manifest` |
| `src/config.py` | Add `gpr_data_url`, `gpr_cache_ttl_hours` |
| `.env.example` | Document `GPR_DATA_URL`, `GPR_CACHE_TTL_HOURS` |
| `pyproject.toml` | Add `tabpfn-extensions>=0.0.14`, `openpyxl>=3.1.0` |
| `tests/test_gpr_connector.py` | Create |
| `tests/test_backtest.py` | Create |
| `tests/test_deferred_tools.py` | Create |
