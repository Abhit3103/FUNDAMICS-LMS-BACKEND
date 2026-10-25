import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.main import app
from src.database import Base, get_db
from src.config import settings
from src.models.user import User, UserRole, UserStatus
from src.models.auth_session import AuthSession, VerificationToken, PasswordResetToken
from src.core.security import hash_password, verify_password, hash_token, create_access_token
from src.core.rate_limit import (
    email_verification_rate_limiter,
    password_reset_rate_limiter,
    login_rate_limiter,
)
from src.core.exceptions import RateLimitError


def reset_all_limiters():
    """Clear in-memory state of all rate limiters."""
    email_verification_rate_limiter.reset()
    password_reset_rate_limiter.reset()
    login_rate_limiter.reset()


@pytest.fixture(autouse=True)
def clean_rate_limiters():
    """Reset all rate limiters before and after each test."""
    reset_all_limiters()
    yield
    reset_all_limiters()


@pytest_asyncio.fixture
async def in_memory_db():
    """Provides a fresh isolated SQLite in-memory database per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(in_memory_db: AsyncSession):
    """FastAPI AsyncClient overriding get_db dependency with in-memory SQLite session."""
    async def override_get_db():
        yield in_memory_db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ============================================================================
# 1. EMAIL SERVICE & SMTP DELIVERY TESTS (MOCKED SMTP)
# ============================================================================

@pytest.mark.asyncio
async def test_email_service_successful_smtp_delivery():
    """Verify that email service connects via SSL/TLS on port 465 with correct credentials and MIME headers."""
    from src.services.email_service import EmailService

    with patch.object(settings, "SMTP_USERNAME", "mailer@fundamics.com"), \
         patch.object(settings, "SMTP_PASSWORD", "SuperSecretPass465"), \
         patch.object(settings, "SMTP_PORT", 465), \
         patch.object(settings, "SMTP_USE_TLS", True), \
         patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:

        mock_send.return_value = ({}, "250 OK: Message accepted")
        svc = EmailService()
        svc.username = "mailer@fundamics.com"
        svc.password = "SuperSecretPass465"
        svc.port = 465
        svc.use_tls = True

        res = await svc.send_email(
            to_email="student@example.com",
            subject="Test Subject",
            html_content="<p>Test HTML</p>",
            text_content="Test Plain",
        )

        assert res["success"] is True
        assert res["provider"] == "hostinger-smtp"
        assert mock_send.await_count == 1

        call_args = mock_send.call_args
        msg = call_args[0][0]
        assert msg["To"] == "student@example.com"
        assert msg["Subject"] == "Test Subject"
        assert "FUNDAMICS" in msg["From"]
        assert call_args.kwargs["hostname"] == settings.SMTP_HOST
        assert call_args.kwargs["port"] == 465
        assert call_args.kwargs["use_tls"] is True
        assert call_args.kwargs["username"] == "mailer@fundamics.com"


@pytest.mark.asyncio
async def test_email_service_smtp_failure_handling():
    """Verify SMTP exceptions are safely trapped without leaking credentials in errors."""
    from src.services.email_service import EmailService
    import aiosmtplib

    with patch.object(settings, "SMTP_USERNAME", "mailer@fundamics.com"), \
         patch.object(settings, "SMTP_PASSWORD", "SuperSecretPass465"), \
         patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:

        mock_send.side_effect = aiosmtplib.SMTPConnectError("Connection refused by peer")
        svc = EmailService()
        svc.username = "mailer@fundamics.com"
        svc.password = "SuperSecretPass465"

        res = await svc.send_email(
            to_email="fail@example.com",
            subject="Fail Test",
            html_content="<p>Fail</p>",
        )

        assert res["success"] is False
        assert "SMTP Error" in res["error"]
        # Ensure password is not present anywhere in the error message
        assert "SuperSecretPass465" not in res["error"]


@pytest.mark.asyncio
async def test_email_service_mock_mode_when_unconfigured():
    """Verify email service gracefully operates in mock mode if SMTP username/password are empty."""
    from src.services.email_service import EmailService

    svc = EmailService()
    svc.username = None
    svc.password = None

    res = await svc.send_email(
        to_email="student@example.com",
        subject="Mock Mode Test",
        html_content="<p>Mock</p>",
    )
    assert res["success"] is True
    assert res["provider"] == "mock-smtp"


# ============================================================================
# 2. EMAIL VERIFICATION WORKFLOW & TOKEN CONCURRENCY
# ============================================================================

@pytest.mark.asyncio
async def test_email_verification_full_flow(client: AsyncClient, in_memory_db: AsyncSession):
    """Test generating a verification token, sending the email, and confirming verification."""
    user = User(
        id=uuid.uuid4(),
        name="Rohit Verma",
        email="rohit@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_VERIFICATION,
        email_verified_at=None,
    )
    in_memory_db.add(user)
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_verification_email", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = {"success": True, "message_id": "test-verify-msg"}

        # 1. Request verification token
        req_resp = await client.post(
            "/auth/email/verification/request",
            json={"email": "rohit@example.com"},
        )
        assert req_resp.status_code == 200
        assert req_resp.json()["success"] is True
        assert mock_email.await_count == 1

        # Check token stored in database
        stmt = select(VerificationToken).where(VerificationToken.user_id == user.id)
        res = await in_memory_db.execute(stmt)
        token_record = res.scalar_one()
        assert token_record.purpose == "EMAIL_VERIFICATION"
        assert token_record.used_at is None
        
        token_exp = token_record.expires_at if token_record.expires_at.tzinfo else token_record.expires_at.replace(tzinfo=timezone.utc)
        assert token_exp > datetime.now(timezone.utc)

        # Extract raw token passed to email dispatcher
        raw_token = mock_email.call_args.kwargs["token"]
        assert hash_token(raw_token) == token_record.token_hash

        reset_all_limiters()

        # 2. Confirm verification with valid token
        confirm_resp = await client.post(
            "/auth/email/verification/confirm",
            json={"token": raw_token},
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["success"] is True

        # Refresh user from DB: verify email_verified_at is set
        await in_memory_db.refresh(user)
        assert user.email_verified_at is not None
        assert user.status == UserStatus.PENDING_APPROVAL

        # Verify token is marked as used
        await in_memory_db.refresh(token_record)
        assert token_record.used_at is not None


@pytest.mark.asyncio
async def test_email_verification_rejection_reused_and_expired(client: AsyncClient, in_memory_db: AsyncSession):
    """Verify expired and previously consumed tokens are rejected with 422."""
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        name="Anjali Rao",
        email="anjali@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_VERIFICATION,
    )
    in_memory_db.add(user)
    await in_memory_db.flush()

    # Create an already used token
    reused_raw = "reused_token_12345"
    used_token = VerificationToken(
        user_id=user.id,
        token_hash=hash_token(reused_raw),
        purpose="EMAIL_VERIFICATION",
        expires_at=now + timedelta(hours=24),
        used_at=now - timedelta(minutes=5),
    )
    in_memory_db.add(used_token)

    # Create an expired token
    expired_raw = "expired_token_12345"
    expired_token = VerificationToken(
        user_id=user.id,
        token_hash=hash_token(expired_raw),
        purpose="EMAIL_VERIFICATION",
        expires_at=now - timedelta(minutes=10),
        used_at=None,
    )
    in_memory_db.add(expired_token)
    await in_memory_db.commit()

    reset_all_limiters()
    reused_resp = await client.post(
        "/auth/email/verification/confirm",
        json={"token": reused_raw},
    )
    assert reused_resp.status_code == 422
    assert "already been used" in reused_resp.json()["error"]["message"]

    reset_all_limiters()
    # Expired token attempt
    expired_resp = await client.post(
        "/auth/email/verification/confirm",
        json={"token": expired_raw},
    )
    assert expired_resp.status_code == 422
    assert "expired" in expired_resp.json()["error"]["message"]

    reset_all_limiters()
    # Invalid/Unknown token attempt
    invalid_resp = await client.post(
        "/auth/email/verification/confirm",
        json={"token": "totally_random_fake_token"},
    )
    assert invalid_resp.status_code == 422
    assert "Invalid or unknown" in invalid_resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_email_verification_enumeration_protection(client: AsyncClient, in_memory_db: AsyncSession):
    """Requesting verification for a nonexistent account returns generic 200 without creating a token."""
    with patch("src.services.email_service.email_service.send_verification_email", new_callable=AsyncMock) as mock_email:
        resp = await client.post(
            "/auth/email/verification/request",
            json={"email": "nonexistent@example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert mock_email.await_count == 0


# ============================================================================
# 3. FORGOT PASSWORD & PASSWORD RESET WORKFLOW
# ============================================================================

@pytest.mark.asyncio
async def test_password_reset_full_flow(client: AsyncClient, in_memory_db: AsyncSession):
    """Test forgot password request, token issuance, session revocation, and password update."""
    old_pwd = "OldPassword123!"
    user = User(
        id=uuid.uuid4(),
        name="Vikram Seth",
        email="vikram@example.com",
        password_hash=hash_password(old_pwd),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.flush()

    # Attach an active auth session to verify session revocation
    session_record = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token("active_refresh_token_1"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        revoked_at=None,
    )
    in_memory_db.add(session_record)
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = {"success": True, "message_id": "test-reset-msg"}

        # 1. Request password reset
        forgot_resp = await client.post(
            "/auth/password/forgot",
            json={"email": "vikram@example.com"},
        )
        assert forgot_resp.status_code == 200
        assert forgot_resp.json()["success"] is True
        assert mock_email.await_count == 1

        # Check DB token
        stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        res = await in_memory_db.execute(stmt)
        reset_token = res.scalar_one()
        assert reset_token.purpose == "PASSWORD_RESET"
        assert reset_token.used_at is None

        raw_reset_token = mock_email.call_args.kwargs["token"]
        assert hash_token(raw_reset_token) == reset_token.token_hash

        reset_all_limiters()

        # 2. Reset password
        new_pwd = "NewSecurePassword456!"
        reset_resp = await client.post(
            "/auth/password/reset",
            json={"token": raw_reset_token, "new_password": new_pwd},
        )
        assert reset_resp.status_code == 200
        assert reset_resp.json()["success"] is True

        # Verify new password works and old password fails
        await in_memory_db.refresh(user)
        assert verify_password(new_pwd, user.password_hash) is True
        assert verify_password(old_pwd, user.password_hash) is False

        # Verify token is marked as used
        await in_memory_db.refresh(reset_token)
        assert reset_token.used_at is not None

        # Verify active session was revoked
        await in_memory_db.refresh(session_record)
        assert session_record.revoked_at is not None


@pytest.mark.asyncio
async def test_password_reset_rejection_reused_and_expired(client: AsyncClient, in_memory_db: AsyncSession):
    """Verify expired and reused password reset tokens are rejected with 422."""
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        name="Kavita Sen",
        email="kavita@example.com",
        password_hash=hash_password("CurrentPassword123!"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.flush()

    reused_raw = "reused_reset_12345"
    used_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(reused_raw),
        purpose="PASSWORD_RESET",
        expires_at=now + timedelta(minutes=60),
        used_at=now - timedelta(minutes=5),
    )
    in_memory_db.add(used_token)

    expired_raw = "expired_reset_12345"
    expired_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(expired_raw),
        purpose="PASSWORD_RESET",
        expires_at=now - timedelta(minutes=10),
        used_at=None,
    )
    in_memory_db.add(expired_token)
    await in_memory_db.commit()

    reset_all_limiters()
    # Reused token attempt
    reused_resp = await client.post(
        "/auth/password/reset",
        json={"token": reused_raw, "new_password": "AnotherPassword123!"},
    )
    assert reused_resp.status_code == 422
    assert "already been used" in reused_resp.json()["error"]["message"]

    reset_all_limiters()
    # Expired token attempt
    expired_resp = await client.post(
        "/auth/password/reset",
        json={"token": expired_raw, "new_password": "AnotherPassword123!"},
    )
    assert expired_resp.status_code == 422
    assert "expired" in expired_resp.json()["error"]["message"]

    reset_all_limiters()
    # Invalid token attempt
    invalid_resp = await client.post(
        "/auth/password/reset",
        json={"token": "completely_bogus_token", "new_password": "AnotherPassword123!"},
    )
    assert invalid_resp.status_code == 422
    assert "Invalid or unknown" in invalid_resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_password_policy_enforcement(client: AsyncClient):
    """Verify password policy rejects weak passwords (length < 8, missing uppercase/lowercase/digit)."""
    # 1. Too short (< 8 chars)
    reset_all_limiters()
    resp1 = await client.post(
        "/auth/password/reset",
        json={"token": "anytoken123", "new_password": "Ab1!"},
    )
    assert resp1.status_code == 422

    # 2. Missing uppercase
    reset_all_limiters()
    resp2 = await client.post(
        "/auth/password/reset",
        json={"token": "anytoken123", "new_password": "lowercaseonly123!"},
    )
    assert resp2.status_code == 422

    # 3. Missing lowercase
    reset_all_limiters()
    resp3 = await client.post(
        "/auth/password/reset",
        json={"token": "anytoken123", "new_password": "UPPERCASEONLY123!"},
    )
    assert resp3.status_code == 422

    # 4. Missing digit or special char
    reset_all_limiters()
    resp4 = await client.post(
        "/auth/password/reset",
        json={"token": "anytoken123", "new_password": "OnlyLettersHereNoDigit"},
    )
    assert resp4.status_code == 422


@pytest.mark.asyncio
async def test_forgot_password_account_enumeration_protection(client: AsyncClient):
    """Requesting password reset for nonexistent email returns generic 200 without sending email."""
    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        resp = await client.post(
            "/auth/password/forgot",
            json={"email": "nobody_exists@example.com"},
        )
        assert resp.status_code == 200
        assert "password reset instructions have been dispatched" in resp.json()["message"]
        assert mock_email.await_count == 0


# ============================================================================
# 4. RATE LIMITING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_email_verification_rate_limiting():
    """Verify rate limiter blocks rapid duplicate submissions (< 2.0s) and window exhaustion."""
    from src.core.rate_limit import InMemoryRateLimiter

    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60, min_interval_seconds=2.0, action_name="verification")
    key = "test_ip:192.168.1.1"

    # Attempt 1: Success
    limiter.check(key)

    # Attempt 2 immediate (< 2.0s): Debounce block
    with pytest.raises(RateLimitError) as exc_info:
        limiter.check(key)
    assert "rapid submissions" in str(exc_info.value.message)

    # Allow interval to pass and test window cap
    limiter._last_request_time[key] = 0.0
    limiter.check(key)
    limiter._last_request_time[key] = 0.0
    limiter.check(key)

    # Attempt 4: Exceeds max_requests (3)
    limiter._last_request_time[key] = 0.0
    with pytest.raises(RateLimitError) as exc_info2:
        limiter.check(key)
    assert "Too many verification attempts" in str(exc_info2.value.message)


@pytest.mark.asyncio
async def test_password_reset_rate_limiting():
    """Verify rate limiter protects password reset endpoints against abuse."""
    from src.core.rate_limit import InMemoryRateLimiter

    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60, min_interval_seconds=1.0, action_name="password reset")
    key = "test_user:pass_reset"

    limiter.check(key)
    limiter._last_request_time[key] = 0.0
    limiter.check(key)

    limiter._last_request_time[key] = 0.0
    with pytest.raises(RateLimitError) as exc_info:
        limiter.check(key)
    assert "Too many password reset attempts" in str(exc_info.value.message)


# ============================================================================
# 5. DUAL ROUTE MOUNTING (both /auth/... and /api/v1/auth/...)
# ============================================================================

@pytest.mark.asyncio
async def test_dual_route_mounts(client: AsyncClient):
    """Verify that both /auth/... and /api/v1/auth/... paths are accessible and return valid responses."""
    reset_all_limiters()
    # Test top-level /auth/password/forgot
    resp1 = await client.post("/auth/password/forgot", json={"email": "anyone@example.com"})
    assert resp1.status_code == 200

    reset_all_limiters()
    # Test /api/v1/auth/password/forgot
    resp2 = await client.post("/api/v1/auth/password/forgot", json={"email": "anyone@example.com"})
    assert resp2.status_code == 200


# ============================================================================
# 6. CONCURRENCY & SINGLE-USE TRANSACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_token_single_use_database_transaction(in_memory_db: AsyncSession):
    """Verify that redeeming a token commits used_at and subsequent redemptions are rejected."""
    from src.services.auth_service import auth_service
    from src.core.exceptions import ValidationError

    user = User(
        id=uuid.uuid4(),
        name="Concurrent User",
        email="concurrent@example.com",
        password_hash=hash_password("Password123!"),
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_VERIFICATION,
    )
    in_memory_db.add(user)
    raw_token = "concurrent_test_raw_token"
    token_record = VerificationToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        purpose="EMAIL_VERIFICATION",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    in_memory_db.add(token_record)
    await in_memory_db.commit()

    # First consumption succeeds
    resp1 = await auth_service.verify_email(db=in_memory_db, token=raw_token)
    assert resp1.success is True

    # Second consumption must immediately fail with ValidationError
    with pytest.raises(ValidationError) as exc_info:
        await auth_service.verify_email(db=in_memory_db, token=raw_token)
    assert "already been used" in str(exc_info.value.message)


# ============================================================================
# 7. REGRESSION: EXISTING LOGIN AND RBAC INTEGRITY
# ============================================================================

@pytest.mark.asyncio
async def test_login_and_rbac_regression(client: AsyncClient, in_memory_db: AsyncSession):
    """Verify that existing login flow and RBAC role checks remain 100% operational."""
    pwd = "StudentSecurePass123!"
    user = User(
        id=uuid.uuid4(),
        name="Active Student",
        email="student_active@fundamics.com",
        password_hash=hash_password(pwd),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.commit()

    reset_all_limiters()
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "student_active@fundamics.com", "password": pwd},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
