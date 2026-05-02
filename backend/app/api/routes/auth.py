import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_session
from app.deps import get_current_user
from app.models.user import User
from app.schemas.auth import TokenResponse, UserLogin, UserPublic, UserRegister

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    tenant_id = uuid.uuid4()
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        tenant_id=tenant_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token(
        str(user.id),
        extra_claims={"tenant_id": str(user.tenant_id), "email": user.email},
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(
        str(user.id),
        extra_claims={"tenant_id": str(user.tenant_id), "email": user.email},
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(current: Annotated[User, Depends(get_current_user)]) -> UserPublic:
    return UserPublic.model_validate(current)
