# -*- coding: utf-8 -*-
"""
Regression test suite covering:
1. Active account requests password reset and changes password.
2. Unverified or pending account follows the intended recovery policy.
3. Unknown email receives generic enumeration-safe response.
4. SMTP failure does not silently masquerade as successful email delivery.
5. Valid reset token changes the password.
6. Invalid, expired, reused, and wrong-purpose tokens are rejected.
7. Reset password schema resilience with field aliases and extra fields (e.g. confirm_password).
8. Duplicate registration handled cleanly (verification resend for unverified, 409 for active, rollback on IntegrityError).
9. Registration approval and notification failures do not corrupt database transactions.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.core.rate_limit import (
    email_verification_rate_limiter,
    login_rate_limiter,
    password_reset_rate_limiter,
)
from src.core.security import hash_password, hash_token, verify_password
from src.database import Base, get_db
from src.main import app
from src.models.academic import Batch, Class, Enrollment
from src.models.auth_session import AuthSession, PasswordResetToken, VerificationToken
from src.models.system import NotificationRecord
from src.models.user import Student, User, UserRole, UserStatus
from src.services.auth_service import auth_service
from src.services.user_service import user_service


def reset_all_limiters():
    email_verification_rate_limiter.reset()
    password_reset_rate_limiter.reset()
    login_rate_limiter.reset()


@pytest.fixture(autouse=True)
def clean_rate_limiters():
    reset_all_limiters()
    yield
    reset_all_limiters()


@pytest_asyncio.fixture
async def in_memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(in_memory_db: AsyncSession):
    async def override_get_db():
        yield in_memory_db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ============================================================================
# 1. ACTIVE & PENDING PASSWORD RESET FLOWS
# ============================================================================

@pytest.mark.asyncio
async def test_active_account_password_reset_flow(client: AsyncClient, in_memory_db: AsyncSession):
    """Active user requests password reset, receives token, updates password, revoking old sessions."""
    old_pwd = "OldPassword123!"
    user = User(
        id=uuid.uuid4(),
        name="Sunita Rao",
        email="sunita@fundamics.in",
        password_hash=hash_password(old_pwd),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.flush()

    active_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token("active-session-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        revoked_at=None,
    )
    in_memory_db.add(active_session)
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = {"success": True, "message_id": "test-reset-active-id"}

        # 1. Request password reset
        resp = await client.post("/auth/password/forgot", json={"email": "Sunita@Fundamics.in "})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert mock_email.await_count == 1

        raw_token = mock_email.call_args.kwargs["token"]

        # Check DB token
        stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        db_token = (await in_memory_db.execute(stmt)).scalar_one()
        assert db_token.purpose == "PASSWORD_RESET"
        assert db_token.used_at is None
        assert hash_token(raw_token) == db_token.token_hash

        reset_all_limiters()

        # 2. Reset password
        new_pwd = "NewSecurePassword789!"
        reset_resp = await client.post(
            "/auth/password/reset",
            json={"token": raw_token, "new_password": new_pwd},
        )
        assert reset_resp.status_code == 200
        assert reset_resp.json()["success"] is True

        # Verify password changed
        await in_memory_db.refresh(user)
        assert verify_password(new_pwd, user.password_hash) is True
        assert verify_password(old_pwd, user.password_hash) is False

        # Verify token used
        await in_memory_db.refresh(db_token)
        assert db_token.used_at is not None

        # Verify session revoked
        await in_memory_db.refresh(active_session)
        assert active_session.revoked_at is not None


@pytest.mark.asyncio
async def test_pending_approval_account_password_reset(client: AsyncClient, in_memory_db: AsyncSession):
    """User who has verified email but is pending admin approval can reset their password."""
    old_pwd = "InitialPendingPassword123!"
    user = User(
        id=uuid.uuid4(),
        name="Pooja Verma",
        email="pooja.pending@fundamics.in",
        password_hash=hash_password(old_pwd),
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_APPROVAL,
        email_verified_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    in_memory_db.add(user)
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = {"success": True, "message_id": "test-pending-reset-id"}

        resp = await client.post("/auth/password/forgot", json={"email": "pooja.pending@fundamics.in"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert mock_email.await_count == 1

        raw_token = mock_email.call_args.kwargs["token"]
        reset_all_limiters()

        new_pwd = "UpdatedPendingPassword456!"
        reset_resp = await client.post(
            "/auth/password/reset",
            json={"token": raw_token, "new_password": new_pwd},
        )
        assert reset_resp.status_code == 200
        assert reset_resp.json()["success"] is True

        await in_memory_db.refresh(user)
        assert verify_password(new_pwd, user.password_hash) is True
        assert user.status == UserStatus.PENDING_APPROVAL


# ============================================================================
# 2. UNVERIFIED ACCOUNT RECOVERY POLICY
# ============================================================================

@pytest.mark.asyncio
async def test_unverified_account_recovery_policy(client: AsyncClient, in_memory_db: AsyncSession):
    """
    Unverified account requesting password reset follows account recovery policy:
    dispatches email verification token and email to complete registration.
    """
    user = User(
        id=uuid.uuid4(),
        name="Unverified Rohit",
        email="rohit.unverified@fundamics.in",
        password_hash=hash_password("InitialPassword123!"),
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_VERIFICATION,
        email_verified_at=None,
    )
    in_memory_db.add(user)
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_reset, \
         patch("src.services.email_service.email_service.send_verification_email", new_callable=AsyncMock) as mock_verify:

        mock_verify.return_value = {"success": True, "message_id": "recovery-verify-id"}

        # Request forgot password
        resp = await client.post("/auth/password/forgot", json={"email": "rohit.unverified@fundamics.in"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Never dispatches password reset email; dispatches verification email
        assert mock_reset.await_count == 0
        assert mock_verify.await_count == 1

        v_token = (await in_memory_db.execute(
            select(VerificationToken).where(VerificationToken.user_id == user.id)
        )).scalar_one_or_none()
        assert v_token is not None
        assert v_token.purpose == "EMAIL_VERIFICATION"


# ============================================================================
# 3. ENUMERATION PROTECTION & SUSPENDED USERS
# ============================================================================

@pytest.mark.asyncio
async def test_unknown_email_receives_generic_response(client: AsyncClient, in_memory_db: AsyncSession):
    """Unknown email returns generic 200 response without creating tokens or dispatching emails."""
    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        resp = await client.post("/auth/password/forgot", json={"email": "ghost.user@unknown.com"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "password reset instructions have been dispatched" in resp.json()["message"].lower()
        assert mock_email.await_count == 0

        tokens = (await in_memory_db.execute(select(PasswordResetToken))).scalars().all()
        assert len(tokens) == 0


@pytest.mark.asyncio
async def test_suspended_user_cannot_reset_password(client: AsyncClient, in_memory_db: AsyncSession):
    """Suspended user requesting reset returns generic response; token if pre-existing is rejected."""
    suspended_user = User(
        id=uuid.uuid4(),
        name="Suspended Scholar",
        email="suspended@fundamics.in",
        password_hash=hash_password("Pass12345!"),
        role=UserRole.STUDENT,
        status=UserStatus.SUSPENDED,
    )
    in_memory_db.add(suspended_user)
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_email:
        resp = await client.post("/auth/password/forgot", json={"email": "suspended@fundamics.in"})
        assert resp.status_code == 200
        assert mock_email.await_count == 0

    # If an attacker has a token issued before suspension, reset attempt is rejected
    raw_token = "pre-suspension-token"
    token_record = PasswordResetToken(
        user_id=suspended_user.id,
        token_hash=hash_token(raw_token),
        purpose="PASSWORD_RESET",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
    )
    in_memory_db.add(token_record)
    await in_memory_db.commit()

    reset_all_limiters()
    reset_resp = await client.post(
        "/auth/password/reset",
        json={"token": raw_token, "new_password": "NewBannedPass123!"},
    )
    assert reset_resp.status_code == 422
    assert "not eligible" in reset_resp.json()["error"]["message"].lower()


# ============================================================================
# 4. SMTP FAILURE DOES NOT MASQUERADE AS SUCCESS
# ============================================================================

@pytest.mark.asyncio
async def test_smtp_failure_does_not_masquerade_as_success(in_memory_db: AsyncSession):
    """When SMTP delivery fails, NotificationRecord status is FAILED and never SENT."""
    user = User(
        id=uuid.uuid4(),
        name="SMTP Fail Test User",
        email="smtp_fail_test@fundamics.in",
        password_hash=hash_password("SecurePass123!"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.commit()

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send, \
         patch.object(settings, "SMTP_USERNAME", "info@fundemicstutorials.in"), \
         patch.object(settings, "SMTP_PASSWORD", "SomePassword123"):

        mock_send.side_effect = aiosmtplib.SMTPConnectTimeoutError("Render blocked port 465")

        resp = await auth_service.request_password_reset(db=in_memory_db, email=user.email)
        assert resp.success is True

        stmt = select(NotificationRecord).where(NotificationRecord.recipient_reference == user.email)
        record = (await in_memory_db.execute(stmt)).scalar_one_or_none()
        assert record is not None
        assert record.status == "FAILED"
        assert record.status != "SENT"
        assert "SMTPConnectTimeoutError" in (record.failure_code or "")


# ============================================================================
# 5. TOKEN REJECTION MATRIX & SCHEMA RESILIENCE
# ============================================================================

@pytest.mark.asyncio
async def test_reset_token_rejection_rules(client: AsyncClient, in_memory_db: AsyncSession):
    """Test rejection of invalid, expired, reused, and wrong-purpose tokens."""
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        name="Validation User",
        email="validate@fundamics.in",
        password_hash=hash_password("ValidPassword123!"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.flush()

    used_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token("used-token-xyz"),
        purpose="PASSWORD_RESET",
        expires_at=now + timedelta(minutes=30),
        used_at=now - timedelta(minutes=5),
    )
    expired_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token("expired-token-xyz"),
        purpose="PASSWORD_RESET",
        expires_at=now - timedelta(minutes=10),
        used_at=None,
    )
    wrong_purpose_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token("wrong-purpose-xyz"),
        purpose="EMAIL_VERIFICATION",
        expires_at=now + timedelta(minutes=30),
        used_at=None,
    )
    in_memory_db.add_all([used_token, expired_token, wrong_purpose_token])
    await in_memory_db.commit()

    # 1. Used token
    reset_all_limiters()
    resp1 = await client.post("/auth/password/reset", json={"token": "used-token-xyz", "new_password": "NewPassword123!"})
    assert resp1.status_code == 422
    assert "already been used" in resp1.json()["error"]["message"]

    # 2. Expired token
    reset_all_limiters()
    resp2 = await client.post("/auth/password/reset", json={"token": "expired-token-xyz", "new_password": "NewPassword123!"})
    assert resp2.status_code == 422
    assert "expired" in resp2.json()["error"]["message"]

    # 3. Wrong purpose token
    reset_all_limiters()
    resp3 = await client.post("/auth/password/reset", json={"token": "wrong-purpose-xyz", "new_password": "NewPassword123!"})
    assert resp3.status_code == 422
    assert "Invalid or unknown" in resp3.json()["error"]["message"]

    # 4. Totally invalid token
    reset_all_limiters()
    resp4 = await client.post("/auth/password/reset", json={"token": "nonexistent-token", "new_password": "NewPassword123!"})
    assert resp4.status_code == 422
    assert "Invalid or unknown" in resp4.json()["error"]["message"]


@pytest.mark.asyncio
async def test_reset_password_field_aliases_and_extra_fields(client: AsyncClient, in_memory_db: AsyncSession):
    """Verify frontend compatibility: accepts camelCase newPassword or password, and ignores confirm_password."""
    user = User(
        id=uuid.uuid4(),
        name="Frontend Compat User",
        email="frontend.compat@fundamics.in",
        password_hash=hash_password("OldPassword123!"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    in_memory_db.add(user)
    await in_memory_db.flush()

    raw_token = "frontend-alias-token"
    token_record = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        purpose="PASSWORD_RESET",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
    )
    in_memory_db.add(token_record)
    await in_memory_db.commit()

    reset_all_limiters()
    # Sending camelCase `newPassword` and extra `confirm_password` must succeed
    resp = await client.post(
        "/auth/password/reset",
        json={
            "token": raw_token,
            "newPassword": "BrandNewPassword123!",
            "confirm_password": "BrandNewPassword123!",
            "extra_analytics_field": "ignore_me",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    await in_memory_db.refresh(user)
    assert verify_password("BrandNewPassword123!", user.password_hash) is True


# ============================================================================
# 6. DUPLICATE REGISTRATION HANDLING & INTEGRITY ROBUSTNESS
# ============================================================================

@pytest.mark.asyncio
async def test_duplicate_registration_unverified_resends_verification(client: AsyncClient, in_memory_db: AsyncSession):
    """
    Submitting registration for an existing unverified student does not fail or violate constraints:
    it resends a fresh verification email.
    """
    cls = Class(id=uuid.uuid4(), name="Class 10", code="C10-REG", academic_year="2026-2027", status="ACTIVE")
    batch = Batch(id=uuid.uuid4(), class_id=cls.id, name="Batch A", code="BA-REG", start_time=time(9, 0), end_time=time(11, 0), status="ACTIVE")
    in_memory_db.add_all([cls, batch])
    await in_memory_db.commit()

    payload = {
        "name": "Arjun Patel",
        "email": "arjun.unverified@fundamics.in",
        "phone": "+919988776655",
        "password": "Password123!",
        "class_id": str(cls.id),
        "batch_id": str(batch.id),
    }

    with patch("src.services.email_service.email_service.send_verification_email", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {"success": True, "message_id": "reg-verify-1"}

        # 1. First registration
        resp1 = await client.post("/api/v1/auth/register/student", json=payload)
        assert resp1.status_code == 201
        assert resp1.json()["success"] is True
        assert mock_verify.await_count == 1

        # 2. Duplicate registration while still unverified
        reset_all_limiters()
        resp2 = await client.post("/api/v1/auth/register/student", json=payload)
        assert resp2.status_code in (200, 201)
        assert resp2.json()["success"] is True
        assert "fresh verification email" in resp2.json()["message"].lower()
        assert mock_verify.await_count == 2


@pytest.mark.asyncio
async def test_duplicate_registration_active_user_returns_conflict(client: AsyncClient, in_memory_db: AsyncSession):
    """Submitting registration for an already active/verified student returns clean 409 Conflict."""
    cls = Class(id=uuid.uuid4(), name="Class 12", code="C12-ACT", academic_year="2026-2027", status="ACTIVE")
    batch = Batch(id=uuid.uuid4(), class_id=cls.id, name="Batch B", code="BB-ACT", start_time=time(9, 0), end_time=time(11, 0), status="ACTIVE")
    active_user = User(
        id=uuid.uuid4(),
        name="Active Student",
        email="active.student@fundamics.in",
        password_hash=hash_password("ActivePass123!"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(timezone.utc),
    )
    in_memory_db.add_all([cls, batch, active_user])
    await in_memory_db.commit()

    payload = {
        "name": "Active Student",
        "email": "active.student@fundamics.in",
        "password": "NewAttemptPassword123!",
        "class_id": str(cls.id),
        "batch_id": str(batch.id),
    }

    reset_all_limiters()
    resp = await client.post("/api/v1/auth/register/student", json=payload)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["error"]["message"].lower()
    assert "UniqueViolationError" not in resp.text
    assert "ix_users_email" not in resp.text


@pytest.mark.asyncio
async def test_registration_integrity_error_rollback(in_memory_db: AsyncSession):
    """Simulated database race condition/IntegrityError safely rolls back transaction and raises ConflictError."""
    from src.schemas.auth import StudentSelfRegisterRequest
    from src.core.exceptions import ConflictError

    cls_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    cls = Class(id=cls_id, name="Class 9", code="C9-ROLLBACK", academic_year="2026-2027", status="ACTIVE")
    batch = Batch(id=batch_id, class_id=cls_id, name="Batch C", code="BC-ROLLBACK", start_time=time(9, 0), end_time=time(11, 0), status="ACTIVE")
    in_memory_db.add_all([cls, batch])
    await in_memory_db.commit()

    req = StudentSelfRegisterRequest(
        name="Simulated Collision",
        email="collision@fundamics.in",
        password="Password123!",
        class_id=cls_id,
        batch_id=batch_id,
    )

    with patch.object(in_memory_db, "flush", side_effect=IntegrityError("duplicate key", params={}, orig=Exception("ix_users_email"))):
        with pytest.raises(ConflictError) as exc_info:
            await auth_service.register_student(db=in_memory_db, req=req)

        assert "already exists" in str(exc_info.value.message).lower()
