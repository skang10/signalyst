from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import ConnectorCreate, ConnectorOut
from src.data.registry import connector_registry
from src.db.models import Connector, ConnectorType
from src.db.session import get_session

router = APIRouter(tags=["connectors"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(db: SessionDep) -> list[ConnectorOut]:
    rows = (
        (await db.execute(select(Connector).where(Connector.is_active)))
          # type: ignore[arg-type]
        .scalars()
        .all()
    )
    return [
        ConnectorOut(
            id=row.id,
            name=row.name,
            description=row.description,
            type=row.type,
            available=(
                connector_registry.is_available(row.id)
                if row.type == ConnectorType.BUILTIN
                else True
            ),
        )
        for row in rows
    ]


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
async def create_connector(body: ConnectorCreate, db: SessionDep) -> ConnectorOut:
    existing = await db.get(Connector, body.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Connector {body.id!r} already exists")
    c = Connector(
        id=body.id,
        name=body.name,
        description=body.description,
        type=ConnectorType.SPEC,
        spec=dict(body.spec),
    )
    db.add(c)
    await db.commit()
    log.info("connector.created", connector_id=body.id)
    return ConnectorOut(
        id=body.id,
        name=body.name,
        description=body.description,
        type=ConnectorType.SPEC,
        available=True,
    )
