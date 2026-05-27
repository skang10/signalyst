"""
End-to-end demo: fetch market data → featurize → classify regime + direction with TabPFN.

Usage:
    cd backend && uv run python scripts/demo.py
    cd backend && uv run python scripts/demo.py --start 2021-01-01 --end 2024-12-31

Requires in .env:
    FRED_API_KEY   (for macro data)
    TABPFN_TOKEN   (for TabPFN API — register at https://ux.priorlabs.ai)
    EIA_API_KEY    (optional, for inventory data)

Regime labels are assigned from hand-labeled historical periods first, then fall back to
WTI rolling-return heuristics for dates not covered. The split is train = first 80 %,
test = last 20 %.
"""

import argparse

import pandas as pd

from src.config import settings
from src.data.connectors import fetch_eia_inventory, fetch_fred_series, fetch_price_series
from src.featurizer import TimeSeriesFeaturizer
from src.inference import DirectionClassifier, OilRegimeClassifier

# Hand-labeled historical regime periods (inclusive on both ends).
# These override the heuristic labels for dates that fall within a known period.
# Sources: EIA, IEA historical reports, Baker Hughes rig count data.
_KNOWN_REGIMES: list[tuple[str, str, str]] = [
    ("2014-07-01", "2016-12-31", "bust"),  # shale glut + OPEC no-cut decision
    ("2020-02-01", "2020-10-31", "bust"),  # COVID demand collapse
    ("2021-01-01", "2022-06-30", "bull_supercycle"),  # post-COVID demand rebound + war spike
    ("2022-02-01", "2022-04-30", "geopolitical_spike"),  # Russia invasion of Ukraine
    ("2023-10-01", "2023-12-31", "geopolitical_spike"),  # Middle East escalation
]


def _make_regime_labels(wti: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Assign a regime label to each date.

    Priority order:
        1. Hand-labeled periods (_KNOWN_REGIMES) — historically verified
        2. geopolitical_spike  — 5-day WTI return > +8 %
        3. bull_supercycle     — 60-day WTI return > +15 %
        4. bust                — 60-day WTI return < -15 %
        5. range_bound         — everything else
    """
    wti_daily = wti.reindex(index, method="ffill")
    ret5 = wti_daily.pct_change(5)
    ret60 = wti_daily.pct_change(60)

    labels = pd.Series("range_bound", index=index, name="regime")
    labels[ret60 > 0.15] = "bull_supercycle"
    labels[ret60 < -0.15] = "bust"
    labels[ret5 > 0.08] = "geopolitical_spike"

    # Hand-labeled periods take priority over heuristics
    for start, end, regime in _KNOWN_REGIMES:
        mask = (index >= start) & (index <= end)
        labels[mask] = regime

    return labels


def _make_direction_labels(wti: pd.Series, index: pd.DatetimeIndex, horizon: int = 20) -> pd.Series:
    """Label each date 'up' or 'down' based on WTI return over the next `horizon` trading days.

    The last `horizon` rows have no forward data and are dropped from the returned series.
    """
    wti_daily = wti.reindex(index, method="ffill")
    forward_ret = wti_daily.shift(-horizon) / wti_daily - 1
    forward_ret = forward_ret.dropna()
    labels = forward_ret.map(lambda r: "up" if r > 0 else "down")
    labels.name = "direction"
    return labels


def _sample_prediction_dates(
    regime_index: pd.DatetimeIndex, direction_index: pd.DatetimeIndex, n: int = 10
) -> pd.DatetimeIndex:
    """Pick the last n dates that have both regime and direction predictions."""
    shared_index = regime_index.intersection(direction_index)
    if len(shared_index) >= n:
        return shared_index[-n:]
    if len(shared_index) > 0:
        return shared_index
    return regime_index[-n:]


def main() -> None:
    parser = argparse.ArgumentParser(description="TemporalAgent pipeline demo")
    parser.add_argument("--start", default="2022-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-12-31", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    start, end = args.start, args.end
    print(f"\nTemporalAgent demo  |  {start} → {end}\n{'─' * 45}")

    # ── 1. Fetch price data ──────────────────────────────
    signals: dict[str, pd.Series] = {}

    for name, ticker in [("wti", "CL=F"), ("dxy", "DX-Y.NYB"), ("xle", "XLE"), ("spy", "SPY")]:
        print(f"Fetching {name} ({ticker})...")
        signals[name] = fetch_price_series(ticker, start, end)
        print(f"  {len(signals[name])} rows")

    # ── 2. Fetch macro data (requires FRED_API_KEY) ──────
    if settings.fred_api_key:
        print("Fetching Industrial Production Index (FRED: INDPRO)...")
        signals["indpro"] = fetch_fred_series("INDPRO", start, end, api_key=settings.fred_api_key)
        print(f"  {len(signals['indpro'])} rows")
    else:
        print("Skipping FRED data (FRED_API_KEY not set)")

    # ── 3. Fetch EIA inventory (requires EIA_API_KEY) ────
    if settings.eia_api_key:
        print("Fetching EIA crude inventory...")
        signals["eia_inventory"] = fetch_eia_inventory(start, end, api_key=settings.eia_api_key)
        print(f"  {len(signals['eia_inventory'])} rows")
    else:
        print("Skipping EIA data (EIA_API_KEY not set)")

    # ── 4. Featurize ─────────────────────────────────────
    print("\nFeaturizing...")
    featurizer = TimeSeriesFeaturizer(windows=[5, 20, 60], lags=[1, 5, 20])
    features = featurizer.transform(signals)

    print(f"Feature matrix:  {features.shape[0]} rows × {features.shape[1]} columns")
    print(f"Date range:      {features.index[0].date()} → {features.index[-1].date()}")

    # ── 5. Generate heuristic labels ─────────────────────
    wti = signals["wti"]
    regime_labels = _make_regime_labels(wti, features.index)
    direction_labels = _make_direction_labels(wti, features.index, horizon=20)

    # Align direction labels (drops last 20 rows that have no forward data)
    common_idx = features.index.intersection(direction_labels.index)
    features_dir = features.loc[common_idx]

    # 80/20 train/test split (strict temporal — no shuffling)
    split = int(len(features) * 0.8)
    split_dir = int(len(features_dir) * 0.8)

    X_train, X_test = features.iloc[:split], features.iloc[split:]
    y_regime_train = regime_labels.iloc[:split]

    X_train_dir, X_test_dir = features_dir.iloc[:split_dir], features_dir.iloc[split_dir:]
    y_dir_train = direction_labels.iloc[:split_dir]

    print(f"\nTrain rows: {len(X_train)}  |  Test rows: {len(X_test)}")
    print(f"Regime label distribution (train):\n  {y_regime_train.value_counts().to_dict()}")

    # ── 6. TabPFN inference ───────────────────────────────
    if not settings.tabpfn_token:
        print("\nSkipping TabPFN inference (TABPFN_TOKEN not set).")
        print("Pipeline OK — featurizer output ready for inference.\n")
        return

    print("\nFitting OilRegimeClassifier...")
    regime_clf = OilRegimeClassifier(n_estimators=8)
    regime_clf.fit(X_train, y_regime_train)

    print("Fitting DirectionClassifier...")
    dir_clf = DirectionClassifier(n_estimators=8)
    dir_clf.fit(X_train_dir, y_dir_train)

    # Predict on test set
    regime_pred = regime_clf.predict(X_test)
    regime_proba = regime_clf.predict_proba(X_test)
    regime_uncertainty = regime_clf.uncertainty(X_test)

    dir_pred = dir_clf.predict(X_test_dir)
    dir_proba = dir_clf.predict_proba(X_test_dir)
    dir_uncertainty = dir_clf.uncertainty(X_test_dir)

    # ── 7. Print results ──────────────────────────────────
    print(f"\n{'─' * 65}")
    print(f"{'Date':<14} {'Regime':<22} {'Conf':>6}  {'Direction':>10} {'Conf':>6}  {'Entropy':>7}")
    print(f"{'─' * 65}")

    sample_dates = _sample_prediction_dates(regime_pred.index, dir_pred.index)
    for date in sample_dates:
        regime = regime_pred[date]
        r_conf = regime_proba.loc[date, regime]

        if date in dir_pred.index:
            direction = dir_pred[date]
            d_conf = dir_proba.loc[date, direction]
            d_entropy = dir_uncertainty[date]
            dir_str = f"{direction:>10} {d_conf:>6.1%}  {d_entropy:>7.3f}"
        else:
            dir_str = f"{'—':>10} {'—':>6}   {'—':>7}"

        print(f"{str(date.date()):<14} {regime:<22} {r_conf:>6.1%}  {dir_str}")

    print(f"{'─' * 65}")

    # Summary stats over full test set
    regime_counts = regime_pred.value_counts()
    up_pct = (dir_pred == "up").mean() * 100
    mean_r_entropy = regime_uncertainty.mean()
    mean_d_entropy = dir_uncertainty.mean()

    print("\nTest-set summary")
    print(f"  Regime distribution: {regime_counts.to_dict()}")
    print(f"  Direction → up: {up_pct:.1f}%  down: {100 - up_pct:.1f}%")
    print(f"  Mean regime entropy:    {mean_r_entropy:.3f}  (lower = more confident)")
    print(f"  Mean direction entropy: {mean_d_entropy:.3f}  (lower = more confident)")

    # Show most uncertain days
    top_uncertain = regime_uncertainty.nlargest(3)
    print("\n  Most uncertain regime days:")
    for date, h in top_uncertain.items():
        print(f"    {date.date()}  entropy={h:.3f}  predicted={regime_pred[date]}")

    print(f"\n{'─' * 65}")
    print("Pipeline OK.\n")


if __name__ == "__main__":
    main()
