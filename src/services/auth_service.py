import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.core.audit import record_audit_log
from src.core.exceptions import UnauthorizedError, NotFoundError, ConflictError, ValidationError
from src.core.security import verify_password, hash_password, hash_token, create_access_token
from src.models.user import User, UserStatus
from src.models.auth_session import AuthSession, PasswordResetToken
from src.schemas.auth import TokenResponse, UserProfileResponse


class AuthService:

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
        device_reference: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> TokenResponse:
        stmt = select(User).where(User.email == email.lower().strip())
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

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
        stmt = select(AuthSession).where(AuthSession.refresh_token_hash == hashed_input)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if not session or session.revoked_at is not None or session.expires_at < now:
            raise UnauthorizedError("Refresh token has expired or is invalid")

        # Invalidate current session (Rotation)
        session.revoked_at = now

        # Fetch associated user
        user_stmt = select(User).where(User.id == session.user_id)
        u_result = await db.execute(user_stmt)
        user = u_result.scalar_one_or_none()

        if not user or user.status != UserStatus.ACTIVE:
            await db.commit()
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
        db.add(new_session)
        await db.flush()

        new_access_token = create_access_token(
            subject=str(user.id),
            role=user.role.value,
            session_id=str(new_session.id),
        )

        await db.commit()

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_raw_refresh,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def logout(db: AsyncSession, user: User, session_id: Optional[str] = None) -> None:
        if session_id:
            try:
                s_uuid = uuid.UUID(session_id)
                stmt = select(AuthSession).where(AuthSession.id == s_uuid, AuthSession.user_id == user.id)
                result = await db.execute(stmt)
                session = result.scalar_one_or_none()
                if session:
                    session.revoked_at = datetime.now(timezone.utc)
            except ValueError:
                pass
        await db.commit()


auth_service = AuthService()
