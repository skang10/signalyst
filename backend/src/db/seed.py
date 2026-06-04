from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connector, ConnectorType, MarketProfile


async def seed_profiles(db: AsyncSession) -> None:
    existing = await db.get(MarketProfile, "oil")
    if existing is None:
        db.add(
            MarketProfile(
                id="oil",
                name="Oil Markets",
                description=(
                    "WTI/Brent crude oil regime analysis using macro, geopolitical, "
                    "and energy signals."
                ),
                default_connectors=["yfinance", "fred", "eia", "gpr"],
                default_featurizer_config={
                    "windows": [5, 20, 60],
                    "lags": [1, 5, 20],
                    "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
                    "energy_specific": True,
                },
                regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await db.commit()


_BUILTIN_CONNECTOR_SPECS = [
    (
        "yfinance",
        "Yahoo Finance",
        "Daily price series from Yahoo Finance. Supports equities, ETFs, and futures.",
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
