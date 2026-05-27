from configparser import ConfigParser
from pathlib import Path


def test_alembic_uses_configured_async_database_driver() -> None:
    parser = ConfigParser()
    parser.read(Path(__file__).resolve().parents[1] / "alembic.ini")

    assert parser["alembic"]["sqlalchemy.url"].startswith("postgresql+asyncpg://")
