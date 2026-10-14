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
    StudentSelfRegisterRequest,
    VerifyEmailRequest,
    ResendVerificationRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    UpdateProfileRequest,
    MessageResponse,
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


@router.post("/register/student", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register_student(
    req: StudentSelfRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Student self-registration: Creates account in pending state and sends email verification."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.register_student(
        db=db,
        req=req,
        request_id=request_id,
    )


@router.post("/verify-email", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def verify_email(
    req: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Verify student email address using secure token from verification email."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.verify_email(
        db=db,
        token=req.token,
        email=req.email,
        request_id=request_id,
    )


@router.post("/resend-verification", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def resend_verification(
    req: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Resend email verification token to unverified registered account."""
    return await auth_service.resend_verification(
        db=db,
        email=req.email,
    )


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initiate password reset process via email & WhatsApp."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.request_password_reset(
        db=db,
        email=req.email,
        request_id=request_id,
    )


@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Complete password reset using secure token and set new password."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.reset_password(
        db=db,
        token=req.token,
        new_password=req.new_password,
        request_id=request_id,
    )


@router.post("/change-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authenticated user change own password."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.change_password(
        db=db,
        user=current_user,
        old_password=req.old_password,
        new_password=req.new_password,
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


@router.patch("/me", response_model=UserProfileResponse, status_code=status.HTTP_200_OK)
async def update_me(
    req: UpdateProfileRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authenticated user update own profile (name, phone)."""
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.update_profile(
        db=db,
        user=current_user,
        req=req,
        request_id=request_id,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke user's current session."""
    session_id = getattr(current_user, "current_session_id", None)
    request_id = getattr(request.state, "request_id", None)
    await auth_service.logout(db=db, user=current_user, session_id=session_id, request_id=request_id)
    return {"success": True, "message": "Logged out successfully"}
