from __future__ import annotations

import pandas as pd

_ALL_FAMILIES = {"rolling_stats", "lag", "momentum"}


class TimeSeriesFeaturizer:
    def __init__(
        self,
        windows: list[int] | None = None,
        lags: list[int] | None = None,
        feature_families: list[str] | None = None,
        energy_specific: bool = False,
    ):
        self.windows: list[int] = windows or [5, 20, 60]
        self.lags: list[int] = lags or [1, 5, 20]
        self.feature_families: set[str] = (
            set(feature_families) if feature_families else _ALL_FAMILIES
        )
        self.energy_specific = energy_specific  # reserved for oil-specific features in PR 3

    def align(self, series_dict: dict[str, pd.Series]) -> pd.DataFrame:
        """Align all series to a common daily index using forward-fill only.

        Uses ffill (not bfill) so no future values are introduced.
        """
        if not series_dict:
            return pd.DataFrame()

        all_dates = pd.DatetimeIndex(
            sorted({date for s in series_dict.values() for date in s.index})
        )
        daily_index = pd.date_range(start=all_dates.min(), end=all_dates.max(), freq="D")

        aligned = {
            name: series.reindex(daily_index, method="ffill")
            for name, series in series_dict.items()
        }
        return pd.DataFrame(aligned, index=daily_index)

    def _rolling_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        frames: dict[str, pd.Series] = {}
        for w in self.windows:
            rolling = series.rolling(w, min_periods=w)
            frames[f"{name}_mean_{w}d"] = rolling.mean()
            frames[f"{name}_std_{w}d"] = rolling.std()
            frames[f"{name}_min_{w}d"] = rolling.min()
            frames[f"{name}_max_{w}d"] = rolling.max()
        return pd.DataFrame(frames, index=series.index)

    def _lag_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {f"{name}_lag_{lag}d": series.shift(lag) for lag in self.lags},
            index=series.index,
        )

    def _momentum_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {f"{name}_roc_{w}d": series.pct_change(w) for w in self.windows},
            index=series.index,
        )

    def transform(self, series_dict: dict[str, pd.Series]) -> pd.DataFrame:
        """Full pipeline: align → compute selected feature families → drop NaN rows."""
        aligned = self.align(series_dict)
        feature_frames = []
        for col in aligned.columns:
            s = aligned[col]
            if "rolling_stats" in self.feature_families:
                feature_frames.append(self._rolling_features(s, col))
            if "lag" in self.feature_families:
                feature_frames.append(self._lag_features(s, col))
            if "momentum" in self.feature_families:
                feature_frames.append(self._momentum_features(s, col))
        if not feature_frames:
            return pd.DataFrame(index=aligned.index)
        return pd.concat(feature_frames, axis=1).dropna()
