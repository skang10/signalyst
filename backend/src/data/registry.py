from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from src.config import settings


@dataclass
class ConnectorMeta:
    name: str
    description: str
    provides: list[str]
    params_schema: dict[str, Any]
    requires_env: str | None
    compute_tier: str
    examples: list[dict[str, Any]]
    module: ModuleType


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorMeta] = {}

    def scan(self, connectors_dir: Path) -> None:
        """Scan a directory for connector subdirs containing manifest.yaml."""
        if not connectors_dir.is_dir():
            return
        for subdir in sorted(connectors_dir.iterdir()):
            manifest_path = subdir / "manifest.yaml"
            connector_path = subdir / "connector.py"
            if not manifest_path.exists() or not connector_path.exists():
                continue
            with manifest_path.open() as f:
                data = yaml.safe_load(f)
            module = _load_module(data["name"], connector_path)
            meta = ConnectorMeta(
                name=data["name"],
                description=data.get("description", ""),
                provides=data.get("provides", []),
                params_schema=data.get(
                    "params", {"type": "object", "properties": {}, "required": []}
                ),
                requires_env=data.get("requires", {}).get("env"),
                compute_tier=data.get("compute_tier", "low"),
                examples=data.get("examples", []),
                module=module,
            )
            self._connectors[meta.name] = meta

    def list(self) -> dict[str, Any]:
        """Return available and blocked connector metadata."""
        available = []
        blocked = []
        for meta in self._connectors.values():
            if meta.requires_env and not _config_value(meta.requires_env):
                blocked.append(
                    {
                        "name": meta.name,
                        "reason": f"{meta.requires_env} not set",
                    }
                )
            else:
                available.append(
                    {
                        "name": meta.name,
                        "description": meta.description,
                        "provides": meta.provides,
                        "params_schema": meta.params_schema,
                        "examples": meta.examples,
                    }
                )
        return {"available": available, "blocked": blocked}

    def is_available(self, name: str) -> bool:
        if name not in self._connectors:
            return False
        meta = self._connectors[name]
        return not meta.requires_env or bool(_config_value(meta.requires_env))

    def fetch(self, name: str, params: dict[str, Any], context: Any) -> dict[str, Any]:
        """Dispatch to the named connector's fetch() function."""
        if name not in self._connectors:
            raise KeyError(f"Unknown connector: {name!r}")
        meta = self._connectors[name]
        if meta.requires_env and not _config_value(meta.requires_env):
            raise RuntimeError(
                f"Connector {name!r} requires env var {meta.requires_env!r} which is not set"
            )
        return meta.module.fetch(params, context)  # type: ignore[no-any-return]


def _config_value(env_name: str) -> str:
    return os.environ.get(env_name, "") or str(getattr(settings, env_name.lower(), ""))


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"connectors.{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


connector_registry = ConnectorRegistry()
