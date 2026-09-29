import uuid
from typing import Optional
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.exceptions import UnauthorizedError, ForbiddenError
from src.core.security import decode_access_token
from src.database import get_db
from src.models.user import User, UserStatus
from src.models.auth_session import AuthSession

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extracts and verifies JWT bearer token.
    Loads user with student and teacher relationships.
    Validates user active status and session revocation.
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedError("Missing authentication token")

    payload = decode_access_token(credentials.credentials)
    user_id_str: Optional[str] = payload.get("sub")
    session_id_str: Optional[str] = payload.get("session_id")

    if not user_id_str:
        raise UnauthorizedError("Invalid token subject")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedError("Malformed user identifier in token")

    # Fetch user with linked student and teacher records
    stmt = (
        select(User)
        .options(selectinload(User.student), selectinload(User.teacher))
        .where(User.id == user_uuid)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedError("User account no longer exists")

    if user.status != UserStatus.ACTIVE:
        raise ForbiddenError(f"User account is {user.status.value}")

    # Check session revocation if session_id is present
    if session_id_str:
        try:
            session_uuid = uuid.UUID(session_id_str)
            session_stmt = select(AuthSession).where(
                AuthSession.id == session_uuid,
                AuthSession.user_id == user.id,
            )
            sess_result = await db.execute(session_stmt)
            auth_session = sess_result.scalar_one_or_none()

            if not auth_session or auth_session.revoked_at is not None:
                raise UnauthorizedError("Session has been revoked or expired")
        except ValueError:
            raise UnauthorizedError("Malformed session identifier in token")

    return user
