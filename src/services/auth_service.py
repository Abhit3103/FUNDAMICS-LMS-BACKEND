import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from src.config import settings
from src.core.audit import record_audit_log
from src.core.exceptions import (
    UnauthorizedError,
    NotFoundError,
    ConflictError,
    ValidationError,
    ServiceUnavailableError,
)
from src.core.security import verify_password, hash_password, hash_token, create_access_token
from src.models.user import User, UserStatus
from src.models.auth_session import AuthSession, PasswordResetToken
from src.schemas.auth import TokenResponse, UserProfileResponse

logger = logging.getLogger(__name__)


class AuthService:

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
        device_reference: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> TokenResponse:
        clean_email = email.lower().strip()

        try:
            stmt = select(User).where(User.email == clean_email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
        except (SQLAlchemyError, Exception) as exc:
            logger.error("Database error during user authentication query: %s", exc)
            raise ServiceUnavailableError("Authentication service is temporarily unavailable. Please try again later.")

        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")

        if user.status != UserStatus.ACTIVE:
            raise UnauthorizedError(f"Account is {user.status.value}. Please contact administrator.")

        # Create refresh token session with rotation
        raw_refresh_token = secrets.token_urlsafe(48)
        hashed_refresh = hash_token(raw_refresh_token)
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=hashed_refresh,
            device_reference=device_reference,
            expires_at=refresh_expires_at,
        )
        try:
            db.add(new_session)
            await db.flush()

            # Create short-lived access token
            access_token = create_access_token(
                subject=str(user.id),
                role=user.role.value,
                session_id=str(new_session.id),
            )

            await record_audit_log(
                db=db,
                action="USER_LOGIN",
                resource_type="auth_session",
                resource_id=str(new_session.id),
                actor_id=user.id,
                request_id=request_id,
            )
            await db.commit()
        except (SQLAlchemyError, Exception) as exc:
            await db.rollback()
            logger.error("Database error persisting auth session during login: %s", exc)
            raise ServiceUnavailableError("Authentication service is temporarily unavailable. Please try again later.")

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def refresh_tokens(
        db: AsyncSession,
        raw_refresh_token: str,
        device_reference: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> TokenResponse:
        hashed_input = hash_token(raw_refresh_token)
        try:
            stmt = select(AuthSession).where(AuthSession.refresh_token_hash == hashed_input)
            result = await db.execute(stmt)
            session = result.scalar_one_or_none()
        except (SQLAlchemyError, Exception) as exc:
            logger.error("Database error during token refresh query: %s", exc)
            raise ServiceUnavailableError("Authentication service is temporarily unavailable. Please try again later.")

        now = datetime.now(timezone.utc)
        if not session or session.revoked_at is not None or session.expires_at < now:
            raise UnauthorizedError("Refresh token has expired or is invalid")

        # Invalidate current session (Rotation)
        session.revoked_at = now

        # Fetch associated user
        try:
            user_stmt = select(User).where(User.id == session.user_id)
            u_result = await db.execute(user_stmt)
            user = u_result.scalar_one_or_none()
        except (SQLAlchemyError, Exception) as exc:
            logger.error("Database error fetching user for token refresh: %s", exc)
            raise ServiceUnavailableError("Authentication service is temporarily unavailable. Please try again later.")

        if not user or user.status != UserStatus.ACTIVE:
            try:
                await db.commit()
            except Exception:
                await db.rollback()
            raise UnauthorizedError("Associated user account is not active")

        # Mint rotated new refresh session
        new_raw_refresh = secrets.token_urlsafe(48)
        new_hashed = hash_token(new_raw_refresh)
        new_session = AuthSession(
            user_id=user.id,
            refresh_token_hash=new_hashed,
            device_reference=device_reference or session.device_reference,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        try:
            db.add(new_session)
            await db.flush()

            new_access_token = create_access_token(
                subject=str(user.id),
                role=user.role.value,
                session_id=str(new_session.id),
            )

            await db.commit()
        except (SQLAlchemyError, Exception) as exc:
            await db.rollback()
            logger.error("Database error persisting rotated session: %s", exc)
            raise ServiceUnavailableError("Authentication service is temporarily unavailable. Please try again later.")

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_raw_refresh,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def logout(
        db: AsyncSession,
        user: User,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        try:
            if session_id:
                try:
                    s_uuid = uuid.UUID(session_id)
                    stmt = select(AuthSession).where(AuthSession.id == s_uuid, AuthSession.user_id == user.id)
                    result = await db.execute(stmt)
                    session = result.scalar_one_or_none()
                    if session and session.revoked_at is None:
                        session.revoked_at = now
                        await record_audit_log(
                            db=db,
                            action="USER_LOGOUT",
                            resource_type="auth_session",
                            resource_id=str(session.id),
                            actor_id=user.id,
                            request_id=request_id,
                        )
                except ValueError:
                    pass
            else:
                stmt = select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                result = await db.execute(stmt)
                sessions = result.scalars().all()
                for s in sessions:
                    s.revoked_at = now
                await record_audit_log(
                    db=db,
                    action="USER_LOGOUT_ALL",
                    resource_type="user",
                    resource_id=str(user.id),
                    actor_id=user.id,
                    request_id=request_id,
                )
            await db.commit()
        except (SQLAlchemyError, Exception) as exc:
            await db.rollback()
            logger.error("Database error during logout: %s", exc)
            raise ServiceUnavailableError("Authentication service is temporarily unavailable. Please try again later.")


    @staticmethod
    async def register_student(
        db: AsyncSession,
        req: "StudentSelfRegisterRequest",
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        from datetime import date
        from src.models.user import Student, UserRole
        from src.models.academic import Class, Batch, Enrollment
        from src.models.auth_session import VerificationToken
        from src.services.notification_service import notification_service
        from src.schemas.auth import MessageResponse

        # Check existing email
        stmt = select(User).where(User.email == req.email.lower().strip())
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ConflictError("A user with this email address already exists")

        # Verify class and batch
        class_obj = await db.get(Class, req.class_id)
        if not class_obj:
            raise NotFoundError("Selected class does not exist")

        batch_obj = await db.get(Batch, req.batch_id)
        if not batch_obj or batch_obj.class_id != req.class_id:
            raise ValidationError("Selected batch does not belong to the chosen class")

        # Generate unique student code
        year = datetime.now(timezone.utc).year
        unique_suffix = secrets.token_hex(3).upper()
        student_code = f"STU-{year}-{unique_suffix}"

        pwd_hash = hash_password(req.password)
        new_user = User(
            name=req.name.strip(),
            email=req.email.lower().strip(),
            phone=req.phone.strip() if req.phone else None,
            password_hash=pwd_hash,
            role=UserRole.STUDENT,
            status=UserStatus.PENDING_VERIFICATION,
        )
        db.add(new_user)
        await db.flush()

        new_student = Student(
            user_id=new_user.id,
            student_code=student_code,
            class_id=req.class_id,
            batch_id=req.batch_id,
            admission_date=date.today(),
            status="PENDING",
        )
        db.add(new_student)
        await db.flush()

        new_enrollment = Enrollment(
            student_id=new_student.id,
            class_id=req.class_id,
            batch_id=req.batch_id,
            start_date=date.today(),
            status="PENDING",
        )
        db.add(new_enrollment)

        # Generate email verification token
        raw_token = secrets.token_urlsafe(32)
        hashed_token = hash_token(raw_token)
        v_token = VerificationToken(
            user_id=new_user.id,
            token_hash=hashed_token,
            purpose="EMAIL_VERIFICATION",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        db.add(v_token)
        await db.flush()

        await record_audit_log(
            db=db,
            action="STUDENT_SELF_REGISTERED",
            resource_type="user",
            resource_id=str(new_user.id),
            actor_id=new_user.id,
            after_json={"email": new_user.email, "student_code": student_code},
            request_id=request_id,
        )

        await notification_service.send_verification_email(
            db=db,
            to_email=new_user.email,
            user_name=new_user.name,
            token=raw_token,
        )
        await db.commit()

        return MessageResponse(
            success=True,
            message="Registration submitted successfully. Please check your email to verify your address.",
        )

    @staticmethod
    async def request_email_verification(
        db: AsyncSession,
        email: str,
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        from src.models.auth_session import VerificationToken
        from src.services.notification_service import notification_service
        from src.schemas.auth import MessageResponse

        clean_email = email.lower().strip()
        stmt = select(User).where(User.email == clean_email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        # Prevent email enumeration and resend only if user exists and is not verified
        if user and user.email_verified_at is None:
            raw_token = secrets.token_urlsafe(32)
            hashed_token = hash_token(raw_token)
            v_token = VerificationToken(
                user_id=user.id,
                token_hash=hashed_token,
                purpose="EMAIL_VERIFICATION",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
            )
            db.add(v_token)
            await db.flush()
            await notification_service.send_verification_email(
                db=db,
                to_email=user.email,
                user_name=user.name,
                token=raw_token,
            )
            await record_audit_log(
                db=db,
                action="EMAIL_VERIFICATION_REQUESTED",
                resource_type="user",
                resource_id=str(user.id),
                actor_id=user.id,
                request_id=request_id,
            )
            await db.commit()

        return MessageResponse(
            success=True,
            message="If an account exists with this email address, a verification link has been sent.",
        )

    @staticmethod
    async def resend_verification(
        db: AsyncSession,
        email: str,
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        """Backward-compatible alias for request_email_verification."""
        return await AuthService.request_email_verification(db=db, email=email, request_id=request_id)

    @staticmethod
    async def verify_email(
        db: AsyncSession,
        token: str,
        email: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        from src.models.auth_session import VerificationToken
        from src.schemas.auth import MessageResponse

        hashed_token = hash_token(token.strip())
        now = datetime.now(timezone.utc)

        # Concurrency safety: Row-level lock ensures single consumption under concurrent requests
        stmt = (
            select(VerificationToken)
            .where(VerificationToken.token_hash == hashed_token)
            .with_for_update()
        )
        res = await db.execute(stmt)
        v_token = res.scalar_one_or_none()

        if not v_token:
            raise ValidationError("Invalid or unknown verification token")
        if v_token.used_at is not None:
            raise ValidationError("Verification token has already been used")
        token_expires_at = v_token.expires_at if v_token.expires_at.tzinfo else v_token.expires_at.replace(tzinfo=timezone.utc)
        if token_expires_at <= now:
            raise ValidationError("Verification token has expired")

        user = await db.get(User, v_token.user_id)
        if not user:
            raise NotFoundError("User account not found")

        v_token.used_at = now
        user.email_verified_at = now
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.PENDING_APPROVAL

        await record_audit_log(
            db=db,
            action="EMAIL_VERIFIED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            request_id=request_id,
        )
        await db.commit()

        return MessageResponse(
            success=True,
            message="Email verified successfully. Your account is now pending administrator approval.",
        )

    @staticmethod
    async def request_password_reset(
        db: AsyncSession,
        email: str,
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        from src.models.auth_session import PasswordResetToken
        from src.services.notification_service import notification_service
        from src.schemas.auth import MessageResponse

        clean_email = email.lower().strip()
        stmt = select(User).where(User.email == clean_email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if user and user.status == UserStatus.ACTIVE:
            raw_token = secrets.token_urlsafe(32)
            hashed = hash_token(raw_token)
            reset_record = PasswordResetToken(
                user_id=user.id,
                token_hash=hashed,
                purpose="PASSWORD_RESET",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
            db.add(reset_record)
            await db.flush()
            await notification_service.send_password_reset(
                db=db,
                to_email=user.email,
                user_name=user.name,
                token=raw_token,
                to_phone=user.phone,
            )
            await record_audit_log(
                db=db,
                action="PASSWORD_RESET_REQUESTED",
                resource_type="user",
                resource_id=str(user.id),
                actor_id=user.id,
                request_id=request_id,
            )
            await db.commit()

        return MessageResponse(
            success=True,
            message="If your account is registered and active, password reset instructions have been dispatched.",
        )

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        token: str,
        new_password: str,
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        from src.models.auth_session import PasswordResetToken
        from src.schemas.auth import MessageResponse

        hashed_token = hash_token(token.strip())
        now = datetime.now(timezone.utc)

        # Concurrency safety: Row-level lock ensures single consumption under concurrent requests
        stmt = (
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == hashed_token)
            .with_for_update()
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        if not record:
            raise ValidationError("Invalid or unknown password reset token")
        if record.used_at is not None:
            raise ValidationError("Password reset token has already been used")
        token_expires_at = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
        if token_expires_at <= now:
            raise ValidationError("Password reset token has expired")

        user = await db.get(User, record.user_id)
        if not user:
            raise NotFoundError("User account not found")

        record.used_at = now
        user.password_hash = hash_password(new_password)

        # Invalidate active login sessions to enforce session revocation
        sess_stmt = select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        active_sessions = (await db.execute(sess_stmt)).scalars().all()
        for s in active_sessions:
            s.revoked_at = now

        await record_audit_log(
            db=db,
            action="PASSWORD_RESET_COMPLETED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            request_id=request_id,
        )
        await db.commit()

        return MessageResponse(
            success=True,
            message="Password has been successfully updated. You may now log in with your new credentials.",
        )

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        old_password: str,
        new_password: str,
        request_id: Optional[str] = None,
    ) -> "MessageResponse":
        from src.schemas.auth import MessageResponse

        if not verify_password(old_password, user.password_hash):
            raise UnauthorizedError("Incorrect current password")

        user.password_hash = hash_password(new_password)
        await record_audit_log(
            db=db,
            action="PASSWORD_CHANGED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            request_id=request_id,
        )
        await db.commit()

        return MessageResponse(
            success=True,
            message="Password changed successfully.",
        )

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        user: User,
        req: "UpdateProfileRequest",
        request_id: Optional[str] = None,
    ) -> UserProfileResponse:
        if req.name is not None and req.name.strip():
            user.name = req.name.strip()
        if req.phone is not None:
            user.phone = req.phone.strip() if req.phone.strip() else None

        await record_audit_log(
            db=db,
            action="PROFILE_UPDATED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            after_json={"name": user.name, "phone": user.phone},
            request_id=request_id,
        )
        await db.commit()

        # Safely reload user with relationships
        stmt = (
            select(User)
            .options(selectinload(User.student), selectinload(User.teacher))
            .where(User.id == user.id)
        )
        refreshed_user = (await db.execute(stmt)).scalar_one()

        return UserProfileResponse(
            id=refreshed_user.id,
            name=refreshed_user.name,
            email=refreshed_user.email,
            phone=refreshed_user.phone,
            role=refreshed_user.role,
            status=refreshed_user.status,
            student_id=refreshed_user.student.id if refreshed_user.student else None,
            teacher_id=refreshed_user.teacher.id if refreshed_user.teacher else None,
            student_code=refreshed_user.student.student_code if refreshed_user.student else None,
            teacher_code=refreshed_user.teacher.teacher_code if refreshed_user.teacher else None,
        )


auth_service = AuthService()
