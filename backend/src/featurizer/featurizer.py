import pandas as pd


class TimeSeriesFeaturizer:
    def __init__(
        self,
        windows: list[int] | None = None,
        lags: list[int] | None = None,
    ):
        self.windows: list[int] = windows or [5, 20, 60]
        self.lags: list[int] = lags or [1, 5, 20]

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
        """Full pipeline: align → compute features → drop NaN rows."""
        aligned = self.align(series_dict)
        feature_frames = []
        for col in aligned.columns:
            s = aligned[col]
            feature_frames.append(self._rolling_features(s, col))
            feature_frames.append(self._lag_features(s, col))
            feature_frames.append(self._momentum_features(s, col))
        return pd.concat(feature_frames, axis=1).dropna()
