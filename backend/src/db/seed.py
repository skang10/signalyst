from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MarketProfile

_OIL_PROFILE = MarketProfile(
    id="oil",
    name="Oil Markets",
    description="WTI/Brent crude oil regime analysis using macro, geopolitical, and energy signals.",  # noqa: E501
    default_connectors=["yfinance", "fred", "eia", "gpr"],
    default_featurizer_config={
        "windows": [5, 20, 60],
        "lags": [1, 5, 20],
        "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
        "energy_specific": True,
    },
    regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
    created_at=datetime.now(UTC),
)


async def seed_profiles(db: AsyncSession) -> None:
    existing = await db.get(MarketProfile, "oil")
    if existing is None:
        db.add(_OIL_PROFILE)
        await db.commit()
