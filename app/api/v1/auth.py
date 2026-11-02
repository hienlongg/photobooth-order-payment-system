from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Precomputed dummy hash at startup to enforce constant-time execution against timing attacks
DUMMY_HASH = get_password_hash("timing_attack_mitigation_constant_salt")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate user via username & password and return a JWT access token.
    - Constant-time execution prevents username enumeration via timing attacks.
    - Offloaded to threadpool to prevent event loop starvation.
    - Returns HTTP 401 if credentials are invalid or user does not exist.
    - Returns HTTP 403 if user or tenant is deactivated.
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.tenant))
        .where(User.username == payload.username)
    )
    user = result.scalar_one_or_none()

    # Mitigate timing attack: ALWAYS run bcrypt even when user does not exist
    hash_to_verify = user.hashed_password if user else DUMMY_HASH
    is_valid_password = await run_in_threadpool(
        verify_password, payload.password, hash_to_verify
    )

    if not user or not is_valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    if not user.tenant or not user.tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant account is deactivated",
        )

    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
    )
    return TokenResponse(access_token=access_token, token_type="bearer")
