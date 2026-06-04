from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def stable_hash(*parts: str) -> str:
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:24]
