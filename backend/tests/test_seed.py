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
        (cid, name, description)[1:]
        for cid, name, description in _BUILTIN_CONNECTOR_SPECS
        if cid == "yfinance"
    )
    assert yfinance.name == seed_name
    assert yfinance.description == seed_description
    assert yfinance.type == ConnectorType.BUILTIN
    # Runtime fields untouched by the upsert
    assert yfinance.spec == {"some": "custom-spec"}
    assert yfinance.is_active is False
