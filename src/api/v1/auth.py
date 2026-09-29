from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.dependencies import get_current_user
from src.database import get_db
from src.models.user import User
from src.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserProfileResponse,
)
from src.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication & Profile"])


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with email and password, returning short-lived access and rotating refresh tokens."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.authenticate_user(
        db=db,
        email=req.email,
        password=req.password,
        device_reference=req.device_info,
        request_id=request_id,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(
    req: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Rotate refresh token and issue new access token."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.refresh_tokens(
        db=db,
        raw_refresh_token=req.refresh_token,
        request_id=request_id,
    )


@router.get("/me", response_model=UserProfileResponse, status_code=status.HTTP_200_OK)
async def get_me(current_user: User = Depends(get_current_user)):
    """Fetch profile of currently authenticated user."""
    return UserProfileResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        phone=current_user.phone,
        role=current_user.role,
        status=current_user.status,
        student_id=current_user.student.id if current_user.student else None,
        teacher_id=current_user.teacher.id if current_user.teacher else None,
        student_code=current_user.student.student_code if current_user.student else None,
        teacher_code=current_user.teacher.teacher_code if current_user.teacher else None,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke user's current session."""
    await auth_service.logout(db=db, user=current_user)
    return {"success": True, "message": "Logged out successfully"}
