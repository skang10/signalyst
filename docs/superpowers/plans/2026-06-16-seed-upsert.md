# Self-Healing Seed Data (Upsert) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `seed_profiles()` and `seed_connectors()` upsert existing rows to match `seed.py`, so stale rows self-heal on the next backend restart instead of silently keeping outdated field values forever.

**Architecture:** Both functions currently skip any row whose `id` already exists. Change them to update a fixed set of fields on existing rows to match the in-code definitions, while leaving unrelated runtime fields (on `Connector`: `spec`, `code`, `tests`, `is_active`, `created_at`) untouched. No new trigger is needed — both already run on every app startup (`api/main.py` lifespan) and in test setup (`tests/conftest.py`).

**Tech Stack:** Python, SQLModel, pytest + pytest-asyncio (sqlite in-memory, matching `tests/conftest.py`).

---

### Task 1: Upsert `seed_profiles()`

**Files:**
- Modify: `backend/src/db/seed.py:77-81`
- Test: `backend/tests/test_seed.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_seed.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from src.db.models import Connector, ConnectorType, MarketProfile
from src.db.seed import _BUILTIN_CONNECTOR_SPECS, _build_profiles, seed_connectors, seed_profiles


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


async def test_seed_profiles_inserts_when_missing(db_session: AsyncSession) -> None:
    await seed_profiles(db_session)

    oil = await db_session.get(MarketProfile, "oil")
    assert oil is not None
    assert oil.primary_ticker == "CL=F"


async def test_seed_profiles_upserts_stale_row(db_session: AsyncSession) -> None:
    # Simulate a row created before regime_thresholds/primary_ticker/
    # default_connector_params were added to seed.py.
    stale = MarketProfile(
        id="oil",
        name="Oil Markets",
        description="stale description",
        default_connectors=["yfinance", "fred", "eia", "gpr"],
        default_connector_params={},
        default_featurizer_config={
            "windows": [5, 20, 60],
            "lags": [1, 5, 20],
            "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
            "energy_specific": True,
        },
        regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
        regime_thresholds={},
        primary_ticker="",
    )
    db_session.add(stale)
    await db_session.commit()

    await seed_profiles(db_session)

    oil = await db_session.get(MarketProfile, "oil")
    assert oil is not None
    seed_oil = next(p for p in _build_profiles() if p.id == "oil")
    assert oil.regime_thresholds == seed_oil.regime_thresholds
    assert oil.primary_ticker == seed_oil.primary_ticker
    assert oil.default_connector_params == seed_oil.default_connector_params
    assert oil.description == seed_oil.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: `test_seed_profiles_upserts_stale_row` FAILS — `oil.regime_thresholds == {}` (stale value retained), not equal to `seed_oil.regime_thresholds`. `test_seed_profiles_inserts_when_missing` should PASS already (insert path is unchanged).

- [ ] **Step 3: Implement the upsert in `seed_profiles()`**

In `backend/src/db/seed.py`, replace the existing `seed_profiles` function (lines 77-81):

```python
_PROFILE_UPSERT_FIELDS = (
    "name",
    "description",
    "default_connectors",
    "default_connector_params",
    "default_featurizer_config",
    "regime_labels",
    "regime_thresholds",
    "primary_ticker",
)


async def seed_profiles(db: AsyncSession) -> None:
    for profile in _build_profiles():
        existing = await db.get(MarketProfile, profile.id)
        if existing is None:
            db.add(profile)
        else:
            for field in _PROFILE_UPSERT_FIELDS:
                setattr(existing, field, getattr(profile, field))
            db.add(existing)
    await db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: both `test_seed_profiles_*` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/db/seed.py backend/tests/test_seed.py
git commit -m "fix(db): upsert market profiles on seed so stale rows self-heal"
```

---

### Task 2: Upsert `seed_connectors()`

**Files:**
- Modify: `backend/src/db/seed.py:96-104`
- Test: `backend/tests/test_seed.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_seed.py`:

```python
async def test_seed_connectors_inserts_when_missing(db_session: AsyncSession) -> None:
    await seed_connectors(db_session)

    yfinance = await db_session.get(Connector, "yfinance")
    assert yfinance is not None
    assert yfinance.type == ConnectorType.BUILTIN


async def test_seed_connectors_upserts_stale_row_without_clobbering_custom_fields(
    db_session: AsyncSession,
) -> None:
    # Simulate a builtin connector row with outdated name/description, plus
    # runtime fields (is_active, spec) that an upsert must not touch.
    stale = Connector(
        id="yfinance",
        name="stale name",
        description="stale description",
        type=ConnectorType.BUILTIN,
        spec={"some": "custom-spec"},
        is_active=False,
    )
    db_session.add(stale)
    await db_session.commit()

    await seed_connectors(db_session)

    yfinance = await db_session.get(Connector, "yfinance")
    assert yfinance is not None
    seed_name, seed_description = next(
        (cid, name, description)[1:] for cid, name, description in _BUILTIN_CONNECTOR_SPECS
        if cid == "yfinance"
    )
    assert yfinance.name == seed_name
    assert yfinance.description == seed_description
    assert yfinance.type == ConnectorType.BUILTIN
    # Runtime fields untouched by the upsert
    assert yfinance.spec == {"some": "custom-spec"}
    assert yfinance.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: `test_seed_connectors_upserts_stale_row_without_clobbering_custom_fields` FAILS — `yfinance.name == "stale name"`, not equal to the seeded name "Yahoo Finance".

- [ ] **Step 3: Implement the upsert in `seed_connectors()`**

In `backend/src/db/seed.py`, replace the existing `seed_connectors` function (lines 96-104):

```python
async def seed_connectors(db: AsyncSession) -> None:
    for connector_id, name, description in _BUILTIN_CONNECTOR_SPECS:
        existing = await db.get(Connector, connector_id)
        if existing is None:
            db.add(
                Connector(
                    id=connector_id, name=name, description=description, type=ConnectorType.BUILTIN
                )
            )
        else:
            existing.name = name
            existing.description = description
            existing.type = ConnectorType.BUILTIN
            db.add(existing)
    await db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: all 4 tests in `test_seed.py` PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/db/seed.py backend/tests/test_seed.py
git commit -m "fix(db): upsert builtin connectors on seed without clobbering custom fields"
```

---

### Task 3: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest`
Expected: all tests pass (239+ existing tests plus the 4 new ones in `test_seed.py`).

- [ ] **Step 2: Run lint and type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: no new errors introduced by `src/db/seed.py` changes. (Pre-existing mypy errors elsewhere are unrelated — confirm none are in `src/db/seed.py` or `tests/test_seed.py`.)

- [ ] **Step 3: Manual sanity check against the real local DB**

Run the upsert against the actual local Postgres DB to confirm it's idempotent and doesn't error on the now-correct `oil` row (which we already manually fixed to match `seed.py`):

```bash
cd backend && uv run python -c "
import asyncio
from src.db.session import engine
from src.db.seed import seed_profiles, seed_connectors
from sqlalchemy.ext.asyncio import AsyncSession

async def main():
    async with AsyncSession(engine) as db:
        await seed_profiles(db)
    async with AsyncSession(engine) as db:
        await seed_connectors(db)
    print('seed upsert ran cleanly')

asyncio.run(main())
"
```

Expected: prints `seed upsert ran cleanly` with no errors, and a follow-up read of the `oil` `MarketProfile` row still shows `regime_thresholds`, `primary_ticker`, and `default_connector_params` matching `seed.py` (unchanged, since they already matched).

---

### Task 4: Finish the branch

- [ ] **Step 1: Use the finishing-a-development-branch skill**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." and follow it to verify tests, present options, and execute the chosen workflow.
