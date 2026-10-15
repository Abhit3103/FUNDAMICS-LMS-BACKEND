import uuid
import pytest
from src.core.security import hash_password, verify_password, create_access_token, decode_access_token
from src.core.exceptions import UnauthorizedError


def test_password_hashing():
    pwd = "StrongAdminPassword123!"
    h = hash_password(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password("WrongPassword!", h) is False


def test_jwt_claims_and_validation():
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_access_token(user_id, "ADMIN")
    claims = decode_access_token(token)

    assert claims["sub"] == user_id
    assert claims["role"] == "ADMIN"
    assert "exp" in claims


def test_invalid_jwt():
    with pytest.raises(UnauthorizedError):
        decode_access_token("invalid.token.structure")


def test_rate_limiter_stops_rapid_multiple_attempts():
    from src.core.rate_limit import InMemoryRateLimiter
    from src.core.exceptions import RateLimitError

    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60, min_interval_seconds=1.0)
    key = "test:127.0.0.1"

    # First attempt should pass
    limiter.check(key)

    # Immediate second attempt (< 1.0s) must be rejected with debounce RateLimitError
    with pytest.raises(RateLimitError) as exc_info:
        limiter.check(key)
    assert "rapid submissions" in str(exc_info.value.message)


def test_rate_limiter_exceeds_max_attempts():
    import time
    from src.core.rate_limit import InMemoryRateLimiter
    from src.core.exceptions import RateLimitError

    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60, min_interval_seconds=0.0)
    key = "test:max_attempts"

    limiter.check(key)
    limiter.check(key)

    # 3rd attempt exceeds max_requests=2
    with pytest.raises(RateLimitError) as exc_info:
        limiter.check(key)
    assert "Too many login attempts" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_database_unavailability_never_authenticates_or_issues_jwt():
    """Verify that a database failure NEVER falls back to demo credentials or issues a JWT."""
    from unittest.mock import AsyncMock
    from src.services.auth_service import auth_service
    from src.core.exceptions import ServiceUnavailableError
    from sqlalchemy.exc import OperationalError

    mock_db = AsyncMock()
    mock_db.execute.side_effect = OperationalError("connection refused", {}, None)

    # Attempting to login with demo credentials when DB is down must raise ServiceUnavailableError (503)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await auth_service.authenticate_user(
            db=mock_db,
            email="admin@fundamics.com",
            password="SecurePassword123!",
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_database_unavailability_never_creates_synthetic_user():
    """Verify that database failure in get_current_user raises ServiceUnavailableError and NEVER creates synthetic user."""
    from unittest.mock import AsyncMock
    import uuid
    from src.core.dependencies import get_current_user
    from src.core.security import create_access_token
    from src.core.exceptions import ServiceUnavailableError
    from fastapi.security import HTTPAuthorizationCredentials
    from sqlalchemy.exc import OperationalError

    mock_db = AsyncMock()
    mock_db.execute.side_effect = OperationalError("connection refused", {}, None)

    # Valid token with a demo admin ID
    token = create_access_token(subject="00000000-0000-0000-0000-000000000001", role="ADMIN", session_id=str(uuid.uuid4()))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await get_current_user(credentials=creds, db=mock_db)
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_invalid_credentials_rejected_without_fallback():
    """Verify that invalid credentials against an active DB return 401 UnauthorizedError without falling back."""
    from unittest.mock import AsyncMock, MagicMock
    from src.services.auth_service import auth_service
    from src.models.user import User, UserStatus, UserRole
    from src.core.security import hash_password
    from src.core.exceptions import UnauthorizedError

    mock_db = AsyncMock()
    real_user = User(
        id=uuid.uuid4(),
        email="test@fundamics.com",
        name="Real User",
        password_hash=hash_password("CorrectPassword123!"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = real_user
    mock_db.execute.return_value = mock_result

    # Wrong password
    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.authenticate_user(
            db=mock_db,
            email="test@fundamics.com",
            password="WrongPassword123!",
        )
    assert exc_info.value.status_code == 401
    assert "Invalid email or password" in exc_info.value.message

    # User not in DB
    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_none

    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.authenticate_user(
            db=mock_db,
            email="nonexistent@fundamics.com",
            password="AnyPassword123!",
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_role_checks_strictly_enforced():
    """Verify that role dependencies require_admin, require_teacher, and require_student reject incorrect roles."""
    from src.core.permissions import require_admin, require_teacher, require_student
    from src.core.exceptions import ForbiddenError
    from src.models.user import User, UserRole, UserStatus, Student, Teacher

    student_user = User(
        id=uuid.uuid4(),
        email="student@fundamics.com",
        name="Student User",
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    student_user.student = Student(id=uuid.uuid4(), user_id=student_user.id, student_code="S-01")

    # Student cannot access admin
    with pytest.raises(ForbiddenError):
        require_admin(current_user=student_user)

    # Student cannot access teacher
    with pytest.raises(ForbiddenError):
        require_teacher(current_user=student_user)

    # Student can access student
    assert require_student(current_user=student_user) == student_user

    # Teacher user
    teacher_user = User(
        id=uuid.uuid4(),
        email="teacher@fundamics.com",
        name="Teacher User",
        role=UserRole.TEACHER,
        status=UserStatus.ACTIVE,
    )
    teacher_user.teacher = Teacher(id=uuid.uuid4(), user_id=teacher_user.id, teacher_code="T-01")

    with pytest.raises(ForbiddenError):
        require_admin(current_user=teacher_user)

    with pytest.raises(ForbiddenError):
        require_student(current_user=teacher_user)

    assert require_teacher(current_user=teacher_user) == teacher_user



