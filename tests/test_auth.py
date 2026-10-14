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
async def test_demo_login_fallback():
    from unittest.mock import AsyncMock
    from src.services.auth_service import auth_service
    from src.core.dependencies import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB offline")

    # Test Admin login
    res = await auth_service.authenticate_user(
        db=mock_db,
        email="admin@fundamics.com",
        password="SecurePassword123!",
    )
    assert res.access_token is not None
    assert res.refresh_token is not None

    # Test resolving demo user via get_current_user
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=res.access_token)
    user = await get_current_user(credentials=creds, db=mock_db)
    assert user.role.value == "ADMIN"
    assert user.email == "admin@fundamics.com"

    # Test Teacher login
    res_t = await auth_service.authenticate_user(
        db=mock_db,
        email="sunita.rao@fundamics.com",
        password="TeacherSecurePass123!",
    )
    user_t = await get_current_user(credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=res_t.access_token), db=mock_db)
    assert user_t.role.value == "TEACHER"
    assert user_t.teacher is not None

    # Test Student login
    res_s = await auth_service.authenticate_user(
        db=mock_db,
        email="rohan.sharma@example.com",
        password="SecurePassword123!",
    )
    user_s = await get_current_user(credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=res_s.access_token), db=mock_db)
    assert user_s.role.value == "STUDENT"
    assert user_s.student is not None


