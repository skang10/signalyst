from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import ProfileResponse
from src.db.models import MarketProfile
from src.db.session import get_session

router = APIRouter(tags=["profiles"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(db: SessionDep) -> list[ProfileResponse]:
    rows = (await db.execute(select(MarketProfile))).scalars().all()
    return [
        ProfileResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            default_connectors=p.default_connectors,
            default_featurizer_config=p.default_featurizer_config,
            regime_labels=p.regime_labels,
        )
        for p in rows
    ]


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, db: SessionDep) -> ProfileResponse:
    p = await db.get(MarketProfile, profile_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        default_connectors=p.default_connectors,
        default_featurizer_config=p.default_featurizer_config,
        regime_labels=p.regime_labels,
    )
