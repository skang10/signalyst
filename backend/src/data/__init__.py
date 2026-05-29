from pathlib import Path

from src.data.connectors import fetch_eia_inventory, fetch_fred_series, fetch_price_series
from src.data.registry import connector_registry

_CONNECTORS_DIR = Path(__file__).parent / "connectors"
connector_registry.scan(_CONNECTORS_DIR)

__all__ = [
    "connector_registry",
    "fetch_eia_inventory",
    "fetch_fred_series",
    "fetch_price_series",
]
