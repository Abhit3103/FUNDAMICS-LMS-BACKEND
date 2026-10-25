import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.dependencies import get_current_user, get_optional_current_user
from src.database import get_db
from src.models.user import User
from src.services.email_service import mask_email
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
    EmailVerificationRequest,
    EmailVerificationConfirmRequest,
    ChangePasswordRequest,
    UpdateProfileRequest,
    MessageResponse,
)
from src.core.rate_limit import (
    rate_limit_login,
    login_rate_limiter,
    rate_limit_email_verification,
    email_verification_rate_limiter,
    rate_limit_password_reset,
    password_reset_rate_limiter,
)
from src.services.auth_service import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & Profile"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_login)],
)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with email and password, returning short-lived access and rotating refresh tokens."""
    request_id = getattr(request.state, "request_id", None)
    # Stop multiple attempts targeted at the same user/email
    login_rate_limiter.check(f"email:{req.email.lower().strip()}")
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


@router.post(
    "/email/verification/request",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_email_verification)],
)
@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_email_verification)],
)
async def request_email_verification(
    req: EmailVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a cryptographically secure, time-limited token and email a verification link to the user.
    Generic response prevents user enumeration.
    """
    request_id = getattr(request.state, "request_id", None)
    email_verification_rate_limiter.check(f"email:{req.email.lower().strip()}")
    return await auth_service.request_email_verification(
        db=db,
        email=req.email,
        request_id=request_id,
    )


@router.post(
    "/email/verification/confirm",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_email_verification)],
)
@router.post(
    "/verify-email",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_email_verification)],
)
async def confirm_email_verification(
    req: EmailVerificationConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate token, reject expired or previously used tokens, and mark user's email as verified.
    Ensures single consumption via database transaction lock.
    """
    request_id = getattr(request.state, "request_id", None)
    return await auth_service.verify_email(
        db=db,
        token=req.token,
        request_id=request_id,
    )


@router.post(
    "/password/forgot",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_password_reset)],
)
@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_password_reset)],
)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a secure, expiring, single-use password-reset token and send user a reset link.
    Returns generic response to prevent account enumeration.
    """
    request_id = getattr(request.state, "request_id", None)
    logger.info(
        "[PASSWORD_RESET_REQUEST_RECEIVED] req_id=%s email=%s client_ip=%s",
        request_id,
        mask_email(req.email),
        request.client.host if request.client else "unknown",
    )
    password_reset_rate_limiter.check(f"email:{req.email.lower().strip()}")
    return await auth_service.request_password_reset(
        db=db,
        email=req.email,
        request_id=request_id,
    )


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_password_reset)],
)
@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_password_reset)],
)
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate single-use token, enforce password strength policy, hash new password using bcrypt,
    save to PostgreSQL, and revoke existing sessions.
    """
    request_id = getattr(request.state, "request_id", None)
    logger.info(
        "[PASSWORD_RESET_SUBMIT_RECEIVED] req_id=%s client_ip=%s",
        request_id,
        request.client.host if request.client else "unknown",
    )
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
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke user's current session if authenticated; succeed idempotently."""
    if current_user:
        session_id = getattr(current_user, "current_session_id", None)
        request_id = getattr(request.state, "request_id", None)
        await auth_service.logout(db=db, user=current_user, session_id=session_id, request_id=request_id)
    return {"success": True, "message": "Logged out successfully"}
