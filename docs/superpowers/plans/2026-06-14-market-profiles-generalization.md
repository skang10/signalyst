# Market Profiles Generalization (sp500, eurusd) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make regime-label generation and default connector params profile-driven in `src/services/tabpfn.py` and `src/services/discovery.py`, then seed two new `MarketProfile` rows (`sp500`, `eurusd`) that work end-to-end with zero further code changes.

**Architecture:** `MarketProfile` gains three new columns (`default_connector_params`, `regime_thresholds`, `primary_ticker`). `tabpfn.py`'s `_make_regime_labels` becomes a pure function parameterized by `regime_labels`/`thresholds`/`known_regimes`, and `_run` loads the session's `MarketProfile` row to drive proxy-column selection, label names, thresholds, and historical overrides. `discovery.py` reads per-connector default params from the profile instead of a hardcoded module dict.

**Tech Stack:** FastAPI, SQLModel, Alembic, pytest (`asyncio_mode = "auto"`), sqlite in-memory test DBs.

All commands below assume `cd backend` first (the project's `backend/` directory).

---

## Reference: full spec

See `docs/superpowers/specs/2026-06-14-market-profiles-generalization-design.md` for the approved design. This plan implements it task-by-task.

---

### Task 1: Add new `MarketProfile` columns + Alembic migration

**Files:**
- Modify: `src/db/models.py:147-158`
- Create: `alembic/versions/b7a1c9d4e02f_generalize_market_profile_regime_config.py`

- [ ] **Step 1: Add the three new fields to `MarketProfile`**

In `src/db/models.py`, replace the `MarketProfile` class (lines 147-158):

```python
class MarketProfile(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str = Field(default="")
    default_connectors: list[str] = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    default_connector_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    default_featurizer_config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    regime_labels: list[str] = Field(default_factory=list, sa_column=Column(SAJson, nullable=False))
    regime_thresholds: dict[str, float] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    primary_ticker: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
```

- [ ] **Step 2: Write the Alembic migration**

Create `alembic/versions/b7a1c9d4e02f_generalize_market_profile_regime_config.py`:

```python
"""generalize market profile regime config

Revision ID: b7a1c9d4e02f
Revises: e463c94b4427
Create Date: 2026-06-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "b7a1c9d4e02f"
down_revision: str | None = "e463c94b4427"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketprofile",
        sa.Column("default_connector_params", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "marketprofile",
        sa.Column("regime_thresholds", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "marketprofile",
        sa.Column(
            "primary_ticker", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("marketprofile", "primary_ticker")
    op.drop_column("marketprofile", "regime_thresholds")
    op.drop_column("marketprofile", "default_connector_params")
```

- [ ] **Step 3: Verify the project still imports cleanly**

Run: `uv run python -c "import src.db.models"`
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add src/db/models.py alembic/versions/b7a1c9d4e02f_generalize_market_profile_regime_config.py
git commit -m "feat: add regime config and connector param columns to MarketProfile"
```

---

### Task 2: Seed `sp500` and `eurusd` profiles, backfill `oil`

**Files:**
- Modify: `src/db/seed.py`
- Modify: `tests/test_profiles.py`

- [ ] **Step 1: Write failing tests for the new profiles**

Append to `tests/test_profiles.py`:

```python
def test_list_profiles_includes_sp500_and_eurusd(client):
    res = client.get("/api/profiles")
    ids = [p["id"] for p in res.json()]
    assert "sp500" in ids
    assert "eurusd" in ids


def test_get_sp500_profile(client):
    res = client.get("/api/profiles/sp500")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "sp500"
    assert body["name"] == "S&P 500"
    assert body["regime_labels"] == ["bull_market", "range_bound", "bear_market", "high_volatility"]
    assert "windows" in body["default_featurizer_config"]


def test_get_eurusd_profile(client):
    res = client.get("/api/profiles/eurusd")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "eurusd"
    assert body["name"] == "EUR/USD"
    assert body["regime_labels"] == ["uptrend", "range_bound", "downtrend", "volatility_spike"]
    assert "windows" in body["default_featurizer_config"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_profiles.py -v`
Expected: `test_list_profiles_includes_sp500_and_eurusd`, `test_get_sp500_profile`, `test_get_eurusd_profile` FAIL (404 / missing ids); the three pre-existing oil tests still PASS.

- [ ] **Step 3: Rewrite `seed_profiles` to seed all three profiles**

Replace the full contents of `src/db/seed.py` with:

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connector, ConnectorType, MarketProfile

_PROFILES: list[MarketProfile] = [
    MarketProfile(
        id="oil",
        name="Oil Markets",
        description=(
            "WTI/Brent crude oil regime analysis using macro, geopolitical, "
            "and energy signals."
        ),
        default_connectors=["yfinance", "fred", "eia", "gpr"],
        default_connector_params={
            "yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]},
            "fred": {"series_ids": ["INDPRO"]},
        },
        default_featurizer_config={
            "windows": [5, 20, 60],
            "lags": [1, 5, 20],
            "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
            "energy_specific": True,
        },
        regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
        regime_thresholds={"trend_up": 0.15, "trend_down": -0.15, "spike": 0.08},
        primary_ticker="CL=F",
    ),
    MarketProfile(
        id="sp500",
        name="S&P 500",
        description=(
            "US large-cap equity regime analysis using price, volatility, and macro signals."
        ),
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
    ),
    MarketProfile(
        id="eurusd",
        name="EUR/USD",
        description=(
            "EUR/USD currency pair regime analysis using price, rate, and dollar-strength signals."
        ),
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
    ),
]


async def seed_profiles(db: AsyncSession) -> None:
    for profile in _PROFILES:
        if await db.get(MarketProfile, profile.id) is None:
            db.add(profile)
    await db.commit()


_BUILTIN_CONNECTOR_SPECS = [
    (
        "yfinance",
        "Yahoo Finance",
        "Daily price series from Yahoo Finance.",
    ),
    ("fred", "FRED", "Macro time series from the St. Louis Fed FRED database."),
    ("eia", "EIA", "Weekly US crude oil inventory change from the EIA."),
    ("gpr", "GPR Index", "Daily Geopolitical Risk Index from the Federal Reserve."),
]


async def seed_connectors(db: AsyncSession) -> None:
    for connector_id, name, description in _BUILTIN_CONNECTOR_SPECS:
        if await db.get(Connector, connector_id) is None:
            db.add(
                Connector(
                    id=connector_id, name=name, description=description, type=ConnectorType.BUILTIN
                )
            )
    await db.commit()
```

Note: `created_at` is no longer set explicitly in `_PROFILES` — `MarketProfile.created_at`'s `default_factory` already produces the same value, so the explicit assignment was redundant.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_profiles.py -v`
Expected: all 7 tests PASS (4 existing oil tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/db/seed.py tests/test_profiles.py
git commit -m "feat: seed sp500 and eurusd market profiles, backfill oil regime config"
```

---

### Task 3: Generalize `_make_regime_labels` in `tabpfn.py`

**Files:**
- Modify: `src/services/tabpfn.py:29-50`
- Test: `tests/test_tabpfn_service.py`

- [ ] **Step 1: Write failing tests for the generalized function**

Append to `tests/test_tabpfn_service.py`:

```python
def test_make_regime_labels_generic_thresholds_and_symmetric_spike() -> None:
    from src.services.tabpfn import _make_regime_labels

    index = pd.date_range("2024-01-01", periods=70, freq="D")
    # Flat at 100 for 65 days, then a sharp 10% drop that holds for 5 days.
    prices = [100.0] * 65 + [90.0] * 5
    proxy = pd.Series(prices, index=index)

    regime_labels = ["trend_up", "range_bound", "trend_down", "spike"]
    thresholds = {"trend_up": 0.15, "trend_down": -0.15, "spike": 0.05}

    labels = _make_regime_labels(proxy, index, regime_labels, thresholds, known_regimes=[])

    # Day 66 (iloc 65): 5-day return = (90-100)/100 = -0.10, abs(-0.10) > 0.05 -> spike
    assert labels.iloc[65] == "spike"
    # Flat region (iloc 10): no threshold crossed -> range_bound
    assert labels.iloc[10] == "range_bound"


def test_make_regime_labels_known_regimes_override() -> None:
    from src.services.tabpfn import _make_regime_labels

    index = pd.date_range("2024-01-01", periods=20, freq="D")
    proxy = pd.Series([100.0] * 20, index=index)

    regime_labels = ["trend_up", "range_bound", "trend_down", "spike"]
    thresholds = {"trend_up": 0.15, "trend_down": -0.15, "spike": 0.05}
    known_regimes = [("2024-01-05", "2024-01-10", "trend_down")]

    labels = _make_regime_labels(proxy, index, regime_labels, thresholds, known_regimes)

    assert (labels.loc["2024-01-05":"2024-01-10"] == "trend_down").all()
    assert labels.iloc[0] == "range_bound"
```

This test file already imports `pandas as pd` at the top — no new import needed for the test bodies themselves (the `_make_regime_labels` import is local to each test).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tabpfn_service.py -v -k make_regime_labels`
Expected: both new tests FAIL with `TypeError: _make_regime_labels() takes 2 positional arguments but 5 were given`.

- [ ] **Step 3: Generalize `_make_regime_labels` and rename `_KNOWN_REGIMES`**

In `src/services/tabpfn.py`, replace lines 29-50:

```python
# Heuristic regime labels (same as demo.py — source of truth).
_KNOWN_REGIMES: list[tuple[str, str, str]] = [
    ("2014-07-01", "2016-12-31", "bust"),
    ("2020-02-01", "2020-10-31", "bust"),
    ("2021-01-01", "2022-06-30", "bull_supercycle"),
    ("2022-02-01", "2022-04-30", "geopolitical_spike"),
    ("2023-10-01", "2023-12-31", "geopolitical_spike"),
]


def _make_regime_labels(wti: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    ret5 = wti_daily.pct_change(5)
    ret60 = wti_daily.pct_change(60)
    labels = pd.Series("range_bound", index=index, name="regime")
    labels[ret60 > 0.15] = "bull_supercycle"
    labels[ret60 < -0.15] = "bust"
    labels[ret5 > 0.08] = "geopolitical_spike"
    for start, end, regime in _KNOWN_REGIMES:
        mask = (index >= start) & (index <= end)
        labels[mask] = regime
    return labels
```

with:

```python
# Hand-labeled historical regime windows, by market profile id.
# Only "oil" has researched windows; other profiles get no historical overrides.
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tabpfn_service.py -v -k make_regime_labels`
Expected: both new tests PASS.

Note: this step intentionally leaves `_run` (which still calls `_make_regime_labels(wti_proxy, features.index)` with the old 2-arg signature) broken — Task 4 fixes that. Do not run the full `test_tabpfn_service.py` file yet.

- [ ] **Step 5: Commit**

```bash
git add src/services/tabpfn.py tests/test_tabpfn_service.py
git commit -m "refactor: generalize _make_regime_labels to take profile-driven labels and thresholds"
```

---

### Task 4: Make `_run` profile-driven

**Files:**
- Modify: `src/services/tabpfn.py:18-22` (imports), `~145-200` (`_run` body)
- Modify: `tests/test_tabpfn_service.py` (cache-hit test setup)

- [ ] **Step 1: Update the cache-hit test to seed an `oil` `MarketProfile` row**

In `tests/test_tabpfn_service.py`, add `MarketProfile` to the import from `src.db.models`:

```python
from src.db.models import (
    AnalysisResult,
    DataArtifact,
    FeatureArtifact,
    MarketProfile,
    SessionStage,
    SessionStatus,
)
```

(This replaces the existing line `from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact, SessionStage, SessionStatus`.)

Then, in `test_tabpfn_cache_hit_transitions_to_explaining_and_chains_explanation`, inside the `async with AsyncSession(engine) as db:` block, add the profile row alongside the other `db.add(...)` calls (before `await db.commit()`):

```python
        db.add(
            MarketProfile(
                id="oil",
                name="Oil Markets",
                default_connectors=["yfinance", "fred", "eia", "gpr"],
                default_connector_params={
                    "yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]},
                    "fred": {"series_ids": ["INDPRO"]},
                },
                default_featurizer_config={},
                regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
                regime_thresholds={"trend_up": 0.15, "trend_down": -0.15, "spike": 0.08},
                primary_ticker="CL=F",
            )
        )
```

- [ ] **Step 2: Run the test to verify it still fails for the right reason**

Run: `uv run pytest tests/test_tabpfn_service.py -v`
Expected: FAILs — `_run` still uses the old 2-arg `_make_regime_labels` call and the hardcoded `regime_labels` list, so this is the same pre-existing failure from Task 3 Step 4's note, not a new one. (If `settings.tabpfn_token` is unset in the test environment, the cache-hit test may actually already pass at this point since the `if settings.tabpfn_token:` branch is skipped entirely — either way, proceed to Step 3.)

- [ ] **Step 3: Add the `MarketProfile` import to `tabpfn.py`**

In `src/services/tabpfn.py`, update the import block (currently lines 18-20):

```python
from src.config import settings
from src.db.models import AnalysisResult, FeatureArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
```

to:

```python
from src.config import settings
from src.db.models import AnalysisResult, FeatureArtifact, MarketProfile, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
```

- [ ] **Step 4: Load the profile and use it for `feature_hash`**

In `_run`, replace:

```python
    fa = (await db.execute(stmt)).scalars().first()
    if fa is None:
        raise ValueError("no FeatureArtifact found for session")

    regime_labels = ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]
    analysis_config: dict[str, Any] = {}
    feature_hash = stable_hash(
        fa.matrix_hash,
        canonical_json(regime_labels),
        canonical_json(analysis_config),
    )
```

with:

```python
    fa = (await db.execute(stmt)).scalars().first()
    if fa is None:
        raise ValueError("no FeatureArtifact found for session")

    market_profile = await db.get(MarketProfile, s.market_profile)
    if market_profile is None:
        raise ValueError(f"unknown market profile: {s.market_profile}")

    analysis_config: dict[str, Any] = {}
    feature_hash = stable_hash(
        fa.matrix_hash,
        canonical_json(market_profile.regime_labels),
        canonical_json(analysis_config),
    )
```

- [ ] **Step 5: Use the profile for proxy-column selection, regime labels, and thresholds**

Inside the `if settings.tabpfn_token:` block, replace:

```python
            # Pick WTI proxy column for labeling
            wti_col = next(
                (c for c in features.columns if "CL=F" in c or "wti" in c.lower()),
                features.columns[0],
            )
            wti_proxy = features[wti_col]

            regime_labels_series = _make_regime_labels(wti_proxy, features.index)
            direction_labels_series = _make_direction_labels(wti_proxy, features.index)
```

with:

```python
            # Pick the profile's primary-ticker column for labeling
            proxy_col = next(
                (c for c in features.columns if c.startswith(market_profile.primary_ticker)),
                features.columns[0],
            )
            proxy = features[proxy_col]

            regime_labels_series = _make_regime_labels(
                proxy,
                features.index,
                market_profile.regime_labels,
                market_profile.regime_thresholds,
                _KNOWN_REGIMES_BY_PROFILE.get(market_profile.id, []),
            )
            direction_labels_series = _make_direction_labels(proxy, features.index)
```

- [ ] **Step 6: Run the full tabpfn test file**

Run: `uv run pytest tests/test_tabpfn_service.py -v`
Expected: all tests PASS, including `test_tabpfn_cache_hit_transitions_to_explaining_and_chains_explanation` and the two new `_make_regime_labels` tests from Task 3.

- [ ] **Step 7: Run the full backend test suite to catch any other regressions**

Run: `uv run python -m pytest`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/services/tabpfn.py tests/test_tabpfn_service.py
git commit -m "feat: drive regime/direction labeling in tabpfn service from MarketProfile"
```

---

### Task 5: Profile-driven default connector params in discovery service

**Files:**
- Modify: `src/services/discovery.py:20-25, ~74`

- [ ] **Step 1: Remove the module-level default and read from the profile**

In `src/services/discovery.py`, remove the module-level constant (currently lines 20-25):

```python
_DEFAULT_CONNECTOR_PARAMS: dict[str, dict[str, Any]] = {
    "yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]},
    "fred": {"series_ids": ["INDPRO"]},
    "eia": {},
    "gpr": {},
}
```

Then in `_run`, replace:

```python
        profile = await db.get(MarketProfile, market_profile)
        default_connectors = list(profile.default_connectors) if profile else []
        pending_sources = []
        for connector_id in default_connectors:
            params = _DEFAULT_CONNECTOR_PARAMS.get(connector_id, {})
            pending_sources.append({"connector_id": connector_id, "params": params})
```

with:

```python
        profile = await db.get(MarketProfile, market_profile)
        default_connectors = list(profile.default_connectors) if profile else []
        pending_sources = []
        for connector_id in default_connectors:
            params = profile.default_connector_params.get(connector_id, {}) if profile else {}
            pending_sources.append({"connector_id": connector_id, "params": params})
```

If `typing.Any` was only used by the removed `_DEFAULT_CONNECTOR_PARAMS` constant, check whether `Any` is still used elsewhere in the file before deciding whether to remove the `from typing import Any` import — `services/discovery.py` uses `dict[str, Any]` for `_DEFAULT_CONNECTOR_PARAMS` and also for event dicts (e.g. `sources_event: dict[str, Any]`, `new_event: dict[str, Any]`), so `Any` is still needed and the import stays.

- [ ] **Step 2: Run discovery tests**

Run: `uv run pytest tests/test_discovery_service.py tests/test_discovery_agent.py -v`
Expected: all PASS, including `test_discovery_service_uses_profile_defaults_when_agent_approves_fewer` (which asserts the exact oil `pending_sources` shape — now sourced from `oil`'s `default_connector_params` seeded in Task 2, which is identical to the old `_DEFAULT_CONNECTOR_PARAMS`).

- [ ] **Step 3: Commit**

```bash
git add src/services/discovery.py
git commit -m "refactor: source default connector params from MarketProfile instead of a hardcoded dict"
```

---

### Task 6: Update `docs/backend-redesign.md`

**Files:**
- Modify: `docs/backend-redesign.md`

- [ ] **Step 1: Add a note about the discovery agent's dead-code fallback path**

Find the section describing `DataSourceDiscoveryAgent` (or the discovery service) in `docs/backend-redesign.md`. Add a short note (one or two sentences) stating that `services/discovery.py` now sources `pending_sources` entirely from `MarketProfile.default_connectors`/`default_connector_params` for all seeded profiles (`oil`, `sp500`, `eurusd`), so the `make_discovery_agent()` LLM fallback — including its oil-specific prompt step — only runs for a profile seeded with empty `default_connectors`, which none currently are.

- [ ] **Step 2: Update the PR Breakdown section**

Find the "PR 6" entry in the PR Breakdown section and mark it done (✅), consistent with how PRs 1-5 are marked, with a short description: "Generalized regime-label generation (`MarketProfile.regime_labels`/`regime_thresholds`/`primary_ticker`/`default_connector_params`); seeded `sp500` and `eurusd` profiles."

- [ ] **Step 3: Commit**

```bash
git add docs/backend-redesign.md
git commit -m "docs: update backend-redesign.md for generalized market profiles (PR 6)"
```

---

### Task 7: Full verification

- [ ] **Step 1: Run the full backend test suite**

Run: `uv run python -m pytest`
Expected: all tests PASS.

- [ ] **Step 2: Run lint and type-check**

Run: `uv run ruff check .` and `uv run mypy .`
Expected: no errors. (If `mypy` flags `proxy_col`/`proxy` or the new `MarketProfile` fields, fix types inline — e.g. ensure `regime_thresholds: dict[str, float]` access uses float-typed keys as written above.)

- [ ] **Step 3: Confirm no remaining references to the old names**

Run: `grep -rn "_DEFAULT_CONNECTOR_PARAMS\|wti_col\|wti_proxy" src/`
Expected: no matches in `src/services/` (matches in `src/agent/tools.py` / `src/eval/backtest.py`, if any, are pre-existing legacy code outside this plan's scope and should be left alone).

---

## Out of scope (do not touch)

- `src/agent/tools.py` and `src/eval/backtest.py` contain their own pre-existing copies of `_make_regime_labels`/`_KNOWN_REGIMES`, duplicated from `src/services/tabpfn.py` before this change. They are not imported by the active session pipeline (`src/services/*`, `src/agents/*`) and are unrelated legacy/demo code — leave them as-is.
- `agents/discovery.py`'s oil-specific prompt text (`"3. For oil markets: recommend WTI + Brent + DXY..."`) — documented as dead code in Task 6, not removed.
- `TimeSeriesFeaturizer.energy_specific` — remains an unused reserved flag.
- Frontend — no changes needed; `NewAnalysisModal` already reads `GET /api/profiles` dynamically and `ProfileResponse` is unchanged.
