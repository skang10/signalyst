# Market Profiles Generalization (sp500, eurusd) — Design

**Status:** Approved, not yet implemented.

## Context

`docs/backend-redesign.md` PR 6 calls for stub market profiles beyond oil (`sp500`, `eurusd`). Today, regime
classification and direction labeling in `src/services/tabpfn.py` are hardcoded for oil:

- `_KNOWN_REGIMES` is a fixed list of historical oil regime date ranges.
- `_make_regime_labels` uses oil-specific return thresholds and produces oil's four hardcoded label names
  (`bull_supercycle`, `range_bound`, `bust`, `geopolitical_spike`), ignoring `MarketProfile.regime_labels`
  (which exists on the model but is unused).
- `_run` picks the "proxy" price column via a substring match on `"CL=F"` / `"wti"`.
- `services/discovery.py` has a module-level `_DEFAULT_CONNECTOR_PARAMS` dict keyed by connector id (not by
  profile), containing oil tickers/series IDs.

This design makes regime labeling and default connector params profile-driven so that adding a new market
profile is a DB row (seed data), not a code change.

`DirectionClassifier` and `_make_direction_labels` are already generic and require no changes.
`TimeSeriesFeaturizer.energy_specific` remains an unused reserved flag — not addressed here.

## 1. `MarketProfile` schema changes

Add three columns (new Alembic migration):

```python
class MarketProfile(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str = Field(default="")
    default_connectors: list[str] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    default_connector_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    default_featurizer_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(SAJson, nullable=False))
    regime_labels: list[str] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    regime_thresholds: dict[str, float] = Field(default_factory=dict, sa_column=Column(SAJson, nullable=False))
    primary_ticker: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
```

- `regime_labels` (existing field, currently unused by `tabpfn.py`) becomes an ordered 4-tuple
  `[trend_up, range_bound, trend_down, spike]`.
- `regime_thresholds` has fixed generic keys: `trend_up`, `trend_down` (60-day return cutoffs), `spike`
  (5-day absolute return cutoff).
- `primary_ticker` is the proxy column used for regime/direction labeling, replacing the
  `"CL=F" in c or "wti" in c.lower()` substring match. Column lookup is `c.startswith(primary_ticker)`,
  falling back to `features.columns[0]` if no match (preserving current fallback behavior).
- `default_connector_params` moves `services/discovery.py`'s module-level `_DEFAULT_CONNECTOR_PARAMS` dict
  into per-profile seed data; that module-level dict is removed.

## 2. Regime labeling generalization (`src/services/tabpfn.py`)

```python
_KNOWN_REGIMES_BY_PROFILE: dict[str, list[tuple[str, str, str]]] = {
    "oil": [
        ("2014-07-01", "2016-12-31", "bust"),
        ("2020-02-01", "2020-10-31", "bust"),
        ("2021-01-01", "2022-06-30", "bull_supercycle"),
        ("2022-02-01", "2022-04-30", "geopolitical_spike"),
        ("2023-10-01", "2023-12-31", "geopolitical_spike"),
    ],
}

def _make_regime_labels(
    proxy: pd.Series,
    index: pd.DatetimeIndex,
    regime_labels: list[str],
    thresholds: dict[str, float],
    known_regimes: list[tuple[str, str, str]],
) -> pd.Series:
    trend_up, range_bound, trend_down, spike = regime_labels
    proxy_daily = proxy.reindex(index, method="ffill")
    ret5 = proxy_daily.pct_change(5)
    ret60 = proxy_daily.pct_change(60)
    labels = pd.Series(range_bound, index=index, name="regime")
    labels[ret60 > thresholds["trend_up"]] = trend_up
    labels[ret60 < thresholds["trend_down"]] = trend_down
    labels[ret5.abs() > thresholds["spike"]] = spike
    for start, end, regime in known_regimes:
        mask = (index >= start) & (index <= end)
        labels[mask] = regime
    return labels
```

Two intentional behavior changes from today:

1. The `spike` condition becomes symmetric (`ret5.abs() > thresholds["spike"]` instead of `ret5 > 0.08`).
   A sharp drop is as much a "spike" as a sharp rise — this is more correct for oil's `geopolitical_spike`
   (e.g. a sudden price collapse from a supply shock) and necessary for sp500/eurusd where both directions
   matter.
2. `known_regimes` is `[]` for `sp500`/`eurusd` (absent from `_KNOWN_REGIMES_BY_PROFILE`), so the historical
   override loop is a no-op for them.

In `_run`:

```python
market_profile = await db.get(MarketProfile, s.market_profile)
proxy_col = next(
    (c for c in features.columns if c.startswith(market_profile.primary_ticker)),
    features.columns[0],
)
proxy = features[proxy_col]
regime_labels_series = _make_regime_labels(
    proxy, features.index,
    market_profile.regime_labels, market_profile.regime_thresholds,
    _KNOWN_REGIMES_BY_PROFILE.get(market_profile.id, []),
)
direction_labels_series = _make_direction_labels(proxy, features.index)
```

The hardcoded `regime_labels = ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]` list inside
`_run` is deleted. `OilRegimeClassifier`'s class name and docstring are left as-is — the class itself is
already generic; renaming is out of scope.

## 3. Seed data for `sp500` and `eurusd`

Added to `src/db/seed.py` alongside the existing `oil` profile (whose row is backfilled with
`primary_ticker="CL=F"`, `regime_thresholds={"trend_up": 0.15, "trend_down": -0.15, "spike": 0.08}`, and
`default_connector_params={"yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]}, "fred": {"series_ids": ["INDPRO"]}}`):

```python
MarketProfile(
    id="sp500",
    name="S&P 500",
    description="US large-cap equity regime analysis using price, volatility, and macro signals.",
    default_connectors=["yfinance", "fred"],
    default_connector_params={
        "yfinance": {"tickers": ["^GSPC", "^VIX", "DX-Y.NYB"]},
        "fred": {"series_ids": ["FEDFUNDS", "UNRATE"]},
    },
    default_featurizer_config={
        "windows": [5, 20, 60],
        "lags": [1, 5, 20],
        "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
        "energy_specific": False,
    },
    regime_labels=["bull_market", "range_bound", "bear_market", "high_volatility"],
    regime_thresholds={"trend_up": 0.10, "trend_down": -0.10, "spike": 0.05},
    primary_ticker="^GSPC",
)

MarketProfile(
    id="eurusd",
    name="EUR/USD",
    description="EUR/USD currency pair regime analysis using price, rate, and dollar-strength signals.",
    default_connectors=["yfinance", "fred"],
    default_connector_params={
        "yfinance": {"tickers": ["EURUSD=X", "DX-Y.NYB"]},
        "fred": {"series_ids": ["DFF"]},
    },
    default_featurizer_config={
        "windows": [5, 20, 60],
        "lags": [1, 5, 20],
        "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
        "energy_specific": False,
    },
    regime_labels=["uptrend", "range_bound", "downtrend", "volatility_spike"],
    regime_thresholds={"trend_up": 0.05, "trend_down": -0.05, "spike": 0.015},
    primary_ticker="EURUSD=X",
)
```

Notes:
- `^VIX` and `DX-Y.NYB` are reused as cross-asset context signals for sp500/eurusd via the existing
  profile-agnostic `yfinance` connector — no connector code changes needed.
- `FEDFUNDS`, `UNRATE`, `DFF` are standard FRED series IDs already supported by the existing `fred`
  connector — no connector code changes needed.
- Thresholds scale down across oil → sp500 → eurusd to reflect each asset's typical volatility (FX moves
  roughly 5-10x less than oil in percentage terms).
- `energy_specific: False` is set explicitly for clarity even though the flag is currently a no-op.

## 4. Discovery service wiring (`src/services/discovery.py`)

The module-level `_DEFAULT_CONNECTOR_PARAMS` dict is removed. `_run` becomes:

```python
profile = await db.get(MarketProfile, market_profile)
default_connectors = list(profile.default_connectors) if profile else []
pending_sources = []
for connector_id in default_connectors:
    params = profile.default_connector_params.get(connector_id, {}) if profile else {}
    pending_sources.append({"connector_id": connector_id, "params": params})
```

Since `oil`, `sp500`, and `eurusd` all define non-empty `default_connectors`, `pending_sources` is always
populated from the profile, and the `make_discovery_agent()` LLM fallback path (with its hardcoded oil
prompt step in `agents/discovery.py`, `"3. For oil markets: recommend WTI + Brent + DXY..."`) is never
reached for any of these three profiles. That prompt line is pre-existing dead code for all current
profiles — out of scope for this change. `docs/backend-redesign.md` will get a one-line note that this
fallback path only fires for a profile seeded with empty `default_connectors`.

## 5. Migration

One Alembic autogenerate migration:
- Adds `default_connector_params` (default `{}`), `regime_thresholds` (default `{}`), `primary_ticker`
  (default `""`) columns to `market_profile`.
- Data migration backfills the existing `oil` row with the values listed in Section 3.
- Seed script (`src/db/seed.py`) inserts the `sp500` and `eurusd` rows on next startup (idempotent, same
  pattern as `seed_profiles` today).

## Out of scope

- New connectors or connector manifest changes — yfinance/fred already support all needed tickers/series.
- Frontend changes — `NewAnalysisModal`'s profile picker already reads from `GET /api/profiles` dynamically.
- `TimeSeriesFeaturizer.energy_specific` — remains an unused reserved flag.
- `_KNOWN_REGIMES`-style historical override windows for `sp500`/`eurusd` — none seeded; can be added later
  as a follow-up without further schema changes.
- Renaming `OilRegimeClassifier` or updating its docstring.
- Fixing `agents/discovery.py`'s oil-specific prompt text — documented as dead code, not removed.
