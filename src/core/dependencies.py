import uuid
from datetime import date
from typing import Optional
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.config import settings
from src.core.demo import DEMO_CREDENTIALS
from src.core.exceptions import UnauthorizedError, ForbiddenError
from src.core.security import decode_access_token
from src.database import get_db
from src.models.user import User, UserStatus, UserRole, Student, Teacher
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

    user = None
    try:
        # Fetch user with linked student and teacher records
        stmt = (
            select(User)
            .options(selectinload(User.student), selectinload(User.teacher))
            .where(User.id == user_uuid)
        )
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
    except Exception:
        user = None

    if not user:
        if settings.APP_ENV == "development":
            for demo in DEMO_CREDENTIALS.values():
                if demo["id"] == user_uuid:
                    demo_user = User(
                        id=demo["id"],
                        name=demo["name"],
                        email=demo["email"],
                        phone=demo.get("phone"),
                        role=demo["role"],
                        status=UserStatus.ACTIVE,
                        password_hash="demo_password_hash",
                    )
                    if demo["role"] == UserRole.TEACHER:
                        demo_user.teacher = Teacher(
                            id=uuid.uuid4(),
                            user_id=demo["id"],
                            teacher_code=demo.get("teacher_code", "TCH-001"),
                            status="ACTIVE",
                        )
                    elif demo["role"] == UserRole.STUDENT:
                        demo_user.student = Student(
                            id=uuid.uuid4(),
                            user_id=demo["id"],
                            student_code=demo.get("student_code", "FND-2025-1042"),
                            class_id=uuid.uuid4(),
                            batch_id=uuid.uuid4(),
                            admission_date=date.today(),
                            status="ACTIVE",
                        )
                    return demo_user
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

    user.current_session_id = session_id_str

    return user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Attempts to extract and verify JWT bearer token.
    Returns None if missing, expired, or invalid without raising an exception.
    """
    if not credentials or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except Exception:
        return None
