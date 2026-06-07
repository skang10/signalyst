from src.services.featurizer_config import apply_config_patch


def test_apply_config_patch_merges_valid_keys():
    current = {
        "windows": [5, 20, 60],
        "lags": [1, 5],
        "feature_families": ["rolling_stats"],
        "energy_specific": False,
    }
    result = apply_config_patch(current, {"windows": [7, 30, 90]})
    assert result == {**current, "windows": [7, 30, 90]}


def test_apply_config_patch_drops_unknown_keys():
    current = {"windows": [5, 20, 60]}
    result = apply_config_patch(current, {"rolling_windows_days": [7, 30, 90], "lags": [2, 10]})
    assert result == {"windows": [5, 20, 60], "lags": [2, 10]}


def test_apply_config_patch_does_not_mutate_current():
    current = {"windows": [5, 20, 60]}
    apply_config_patch(current, {"windows": [7, 30, 90]})
    assert current == {"windows": [5, 20, 60]}
