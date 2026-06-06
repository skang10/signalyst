import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import src.db.models  # noqa: F401 — registers all tables


@pytest.fixture
def client():
    from api.main import app
    from src.db.session import get_session

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as db:
            from src.db.seed import seed_profiles

            await seed_profiles(db)
        async with AsyncSession(engine) as db:
            from src.db.seed import seed_connectors

            await seed_connectors(db)

    asyncio.run(_setup())

    async def override_get_session():
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()

    async def _teardown() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_teardown())
