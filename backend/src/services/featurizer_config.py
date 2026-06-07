from __future__ import annotations

from typing import Any

_VALID_PATCH_KEYS = {"windows", "lags", "feature_families", "energy_specific"}


def apply_config_patch(current: dict[str, Any], raw_patch: dict[str, Any]) -> dict[str, Any]:
    patch = {k: v for k, v in raw_patch.items() if k in _VALID_PATCH_KEYS}
    return {**current, **patch}
