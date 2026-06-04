"""
Unit tests for FeaturizerService internals.
End-to-end service behaviour is covered by test_pipeline.py.
"""

import pandas as pd

from src.services.featurizer import _raw_data_to_series


def test_raw_data_to_series_reconstructs_correctly():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    raw = {
        "CL=F": {
            "index": [str(d.date()) for d in dates],
            "data": [70.0, 71.0, 72.0, 73.0, 74.0],
        }
    }
    result = _raw_data_to_series(raw)
    assert "CL=F" in result
    s = result["CL=F"]
    assert len(s) == 5
    assert float(s.iloc[0]) == 70.0
    assert s.index.dtype == "datetime64[ns]"


def test_raw_data_to_series_handles_none_values():
    raw = {
        "col": {
            "index": ["2023-01-01", "2023-01-02"],
            "data": [1.0, None],
        }
    }
    result = _raw_data_to_series(raw)
    assert pd.isna(result["col"].iloc[1])
