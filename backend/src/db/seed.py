from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connector, ConnectorType, MarketProfile


def _build_profiles() -> list[MarketProfile]:
    return [
        MarketProfile(
            id="oil",
            name="Oil Markets",
            description=(
                "WTI/Brent crude oil regime analysis using macro, geopolitical, and energy signals."
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
                "EUR/USD currency pair regime analysis using price, rate, and "
                "dollar-strength signals."
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
