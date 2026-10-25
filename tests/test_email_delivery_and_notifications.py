# -*- coding: utf-8 -*-
"""
Automated unit and integration tests for SMTP delivery, STARTTLS, error diagnosis,
notification status auditing, registration approval resilience, and password-reset early exits.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.database import Base

from src.config import settings
from src.models.auth_session import PasswordResetToken
from src.models.system import NotificationRecord
from src.models.user import User, Student, UserRole, UserStatus
from src.services.email_service import EmailService, mask_email
from src.services.notification_service import notification_service
from src.services.user_service import user_service
from src.services.auth_service import auth_service


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


# ============================================================================
# 1. SMTP CONFIGURATION, STARTTLS, TIMEOUT & AUTH TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_smtp_port_587_uses_starttls():
    """Verify that port 587 sets start_tls=True and use_tls=False on aiosmtplib.send."""
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        svc = EmailService()
        svc.username = "info@fundemicstutorials.in"
        svc.password = "SecretPassword123"
        svc.port = 587
        svc.use_tls = True

        res = await svc.send_email(
            to_email="test@fundamics.in",
            subject="Test Port 587",
            html_content="<p>587 STARTTLS</p>",
        )

        assert res["success"] is True
        assert res["mocked"] is False
        assert mock_send.await_count == 1
        kwargs = mock_send.call_args.kwargs
        assert kwargs["port"] == 587
        assert kwargs["start_tls"] is True
        assert kwargs["use_tls"] is False


@pytest.mark.asyncio
async def test_smtp_port_465_uses_direct_tls():
    """Verify that port 465 sets use_tls=True and start_tls=False on aiosmtplib.send."""
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        svc = EmailService()
        svc.username = "info@fundemicstutorials.in"
        svc.password = "SecretPassword123"
        svc.port = 465
        svc.use_tls = True

        res = await svc.send_email(
            to_email="test@fundamics.in",
            subject="Test Port 465",
            html_content="<p>465 Direct TLS</p>",
        )

        assert res["success"] is True
        assert res["mocked"] is False
        assert mock_send.await_count == 1
        kwargs = mock_send.call_args.kwargs
        assert kwargs["port"] == 465
        assert kwargs["use_tls"] is True
        assert kwargs["start_tls"] is False


@pytest.mark.asyncio
async def test_smtp_connect_timeout_error_diagnosis():
    """Verify that SMTPConnectTimeoutError (e.g. cloud port 465 blockage) is diagnosed accurately."""
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = aiosmtplib.SMTPConnectTimeoutError("Timed out connecting to host")
        svc = EmailService()
        svc.username = "info@fundemicstutorials.in"
        svc.password = "SecretPassword123"
        svc.port = 465

        res = await svc.send_email(
            to_email="student@fundamics.in",
            subject="Timeout Test",
            html_content="<p>Timeout</p>",
        )

        assert res["success"] is False
        assert res["mocked"] is False
        assert "SMTPConnectTimeoutError" in res["error"]
        assert res["failure_category"] == "TCP_CONNECT_TIMEOUT_OR_BLOCKED_PORT"


@pytest.mark.asyncio
async def test_smtp_authentication_failure_diagnosis():
    """Verify that authentication failure returns safe category and never leaks credentials."""
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = aiosmtplib.SMTPAuthenticationError(535, "Authentication credentials invalid")
        svc = EmailService()
        svc.username = "info@fundemicstutorials.in"
        svc.password = "SuperSecretPasswordDoNotLeak"
        svc.port = 587

        res = await svc.send_email(
            to_email="student@fundamics.in",
            subject="Auth Failure Test",
            html_content="<p>Auth Failure</p>",
        )

        assert res["success"] is False
        assert res["mocked"] is False
        assert "SMTPAuthenticationError" in res["error"]
        assert res["failure_category"] == "AUTHENTICATION_FAILED"
        assert "SuperSecretPasswordDoNotLeak" not in str(res)


# ============================================================================
# 2. NOTIFICATION STATUS ACCURACY: SENT vs MOCKED vs SKIPPED vs FAILED
# ============================================================================

@pytest.mark.asyncio
async def test_notification_status_mocked_when_credentials_missing(in_memory_db: AsyncSession):
    """When SMTP credentials are not configured, notification record must be MOCKED, not DELIVERED."""
    with patch.object(settings, "SMTP_USERNAME", None), \
         patch.object(settings, "SMTP_PASSWORD", None):

        res = await notification_service.send_verification_email(
            db=in_memory_db,
            to_email="unconfigured@fundamics.in",
            user_name="Mock Student",
            token="TEST-TOKEN-123",
        )

        # Mock mode does not perform actual external delivery
        assert res is False

        # Verify database record
        stmt = select(NotificationRecord).where(NotificationRecord.recipient_reference == "unconfigured@fundamics.in")
        record = (await in_memory_db.execute(stmt)).scalar_one_or_none()

        assert record is not None
        assert record.status == "MOCKED"
        assert record.sent_at is None
        assert "mock-smtp" in (record.payload_reference or "")


@pytest.mark.asyncio
async def test_notification_status_sent_on_smtp_acceptance(in_memory_db: AsyncSession):
    """When SMTP server accepts the message, status must be SENT with sent_at set (not premature DELIVERED)."""
    with patch.object(settings, "SMTP_USERNAME", "info@fundemicstutorials.in"), \
         patch.object(settings, "SMTP_PASSWORD", "ValidPassword123"), \
         patch("aiosmtplib.send", new_callable=AsyncMock):

        res = await notification_service.send_verification_email(
            db=in_memory_db,
            to_email="realstudent@fundamics.in",
            user_name="Real Student",
            token="TEST-TOKEN-456",
        )

        assert res is True

        stmt = select(NotificationRecord).where(NotificationRecord.recipient_reference == "realstudent@fundamics.in")
        record = (await in_memory_db.execute(stmt)).scalar_one_or_none()

        assert record is not None
        assert record.status == "SENT"
        assert record.sent_at is not None
        assert "smtp-" in (record.payload_reference or "")


@pytest.mark.asyncio
async def test_notification_status_skipped_when_disabled(in_memory_db: AsyncSession):
    """When notifications are disabled, status must be recorded as SKIPPED."""
    with patch.object(settings, "NOTIFICATIONS_ENABLED", False):
        res = await notification_service.send_verification_email(
            db=in_memory_db,
            to_email="disabled@fundamics.in",
            user_name="Disabled Student",
            token="TEST-TOKEN-789",
        )

        assert res is False

        stmt = select(NotificationRecord).where(NotificationRecord.recipient_reference == "disabled@fundamics.in")
        record = (await in_memory_db.execute(stmt)).scalar_one_or_none()

        assert record is not None
        assert record.status == "SKIPPED"
        assert record.sent_at is None
        assert record.failure_code == "NOTIFICATIONS_DISABLED"


# ============================================================================
# 3. REGISTRATION APPROVAL RESILIENCE: EMAIL FAILURE DOES NOT ROLL BACK
# ============================================================================

@pytest.mark.asyncio
async def test_registration_approval_persists_even_when_email_times_out(in_memory_db: AsyncSession):
    """
    If the email provider encounters SMTPConnectTimeoutError or fails, the student's
    approval status in PostgreSQL MUST NOT be rolled back.
    """
    admin = User(
        id=uuid.uuid4(),
        name="System Admin",
        email="admin_approve@fundamics.in",
        password_hash="fakehash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    student_user = User(
        id=uuid.uuid4(),
        name="Pending Candidate",
        email="candidate@fundamics.in",
        password_hash="fakehash",
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_APPROVAL,
    )
    from datetime import date, time
    from src.models.academic import Class as AcademicClass, Batch as AcademicBatch

    cls = AcademicClass(
        id=uuid.uuid4(),
        name="Grade 10",
        code=f"G10-{uuid.uuid4().hex[:4]}",
        academic_year="2026-2027",
        status="ACTIVE",
    )
    batch = AcademicBatch(
        id=uuid.uuid4(),
        class_id=cls.id,
        name="Morning Batch",
        code=f"B1-{uuid.uuid4().hex[:4]}",
        start_time=time(9, 0),
        end_time=time(11, 0),
        status="ACTIVE",
    )
    student_record = Student(
        id=uuid.uuid4(),
        user_id=student_user.id,
        student_code=f"STU-{uuid.uuid4().hex[:6]}",
        class_id=cls.id,
        batch_id=batch.id,
        admission_date=date.today(),
        status="PENDING_APPROVAL",
    )
    in_memory_db.add_all([admin, cls, batch, student_user, student_record])
    await in_memory_db.commit()

    # Simulate email connection timeout
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send, \
         patch.object(settings, "SMTP_USERNAME", "info@fundemicstutorials.in"), \
         patch.object(settings, "SMTP_PASSWORD", "ValidPassword123"):

        mock_send.side_effect = aiosmtplib.SMTPConnectTimeoutError("Render blocked port 465")

        resp = await user_service.approve_registration(
            db=in_memory_db,
            user_id=student_user.id,
            actor_id=admin.id,
            remarks="Approved by exam coordinator",
        )

        assert resp is not None

        # Verify student user and student record are ACTIVE in PostgreSQL despite email failure
        refreshed_user = await in_memory_db.get(User, student_user.id)
        refreshed_student = await in_memory_db.get(Student, student_record.id)

        assert refreshed_user.status == UserStatus.ACTIVE
        assert refreshed_student.status == "ACTIVE"

        # Verify notification was logged as FAILED
        stmt = select(NotificationRecord).where(NotificationRecord.recipient_reference == "candidate@fundamics.in")
        record = (await in_memory_db.execute(stmt)).scalar_one_or_none()
        assert record is not None
        assert record.status == "FAILED"
        assert "SMTPConnectTimeoutError" in (record.failure_code or "")


# ============================================================================
# 4. PASSWORD RESET EARLY EXITS & ENUMERATION DEFENSE
# ============================================================================

@pytest.mark.asyncio
async def test_password_reset_nonexistent_email_early_exit(in_memory_db: AsyncSession):
    """
    Nonexistent email must return generic success message, create no token,
    attempt no SMTP dispatch, and execute cleanly.
    """
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        resp = await auth_service.request_password_reset(
            db=in_memory_db,
            email="nonexistent.user.12345@fundamics.in",
        )

        assert resp.success is True
        assert "password reset instructions have been dispatched" in resp.message.lower()

        # No SMTP dispatch attempted
        assert mock_send.await_count == 0

        # No token in DB
        stmt = select(PasswordResetToken)
        tokens = (await in_memory_db.execute(stmt)).scalars().all()
        assert len(tokens) == 0


@pytest.mark.asyncio
async def test_password_reset_account_status_policies(in_memory_db: AsyncSession):
    """
    Verify password reset policy across account statuses:
    1. PENDING_APPROVAL (verified email) -> issues password reset token and dispatches reset instructions.
    2. PENDING_VERIFICATION (unverified email) -> issues verification token and dispatches verification email.
    3. SUSPENDED/REJECTED -> returns generic response, issues no tokens or emails.
    All return identical public response to prevent account state enumeration.
    """
    from src.models.auth_session import VerificationToken

    pending_user = User(
        id=uuid.uuid4(),
        name="Pending Approval User",
        email="pending_pass_reset@fundamics.in",
        password_hash="fakehash",
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_APPROVAL,
    )
    unverified_user = User(
        id=uuid.uuid4(),
        name="Unverified User",
        email="unverified_pass_reset@fundamics.in",
        password_hash="fakehash",
        role=UserRole.STUDENT,
        status=UserStatus.PENDING_VERIFICATION,
    )
    suspended_user = User(
        id=uuid.uuid4(),
        name="Suspended User",
        email="suspended_pass_reset@fundamics.in",
        password_hash="fakehash",
        role=UserRole.STUDENT,
        status=UserStatus.SUSPENDED,
    )
    in_memory_db.add_all([pending_user, unverified_user, suspended_user])
    await in_memory_db.commit()

    with patch("src.services.email_service.email_service.send_password_reset_email", new_callable=AsyncMock) as mock_reset, \
         patch("src.services.email_service.email_service.send_verification_email", new_callable=AsyncMock) as mock_verify:

        mock_reset.return_value = {"success": True, "message_id": "test-reset-id"}
        mock_verify.return_value = {"success": True, "message_id": "test-verify-id"}

        # 1. PENDING_APPROVAL: issues password reset token
        resp1 = await auth_service.request_password_reset(db=in_memory_db, email="pending_pass_reset@fundamics.in")
        assert resp1.success is True
        assert mock_reset.await_count == 1
        stmt1 = select(PasswordResetToken).where(PasswordResetToken.user_id == pending_user.id)
        p_token = (await in_memory_db.execute(stmt1)).scalar_one_or_none()
        assert p_token is not None
        assert p_token.purpose == "PASSWORD_RESET"

        # 2. PENDING_VERIFICATION: issues verification recovery token
        resp2 = await auth_service.request_password_reset(db=in_memory_db, email="unverified_pass_reset@fundamics.in")
        assert resp2.success is True
        assert mock_verify.await_count == 1
        stmt2 = select(VerificationToken).where(VerificationToken.user_id == unverified_user.id)
        v_token = (await in_memory_db.execute(stmt2)).scalar_one_or_none()
        assert v_token is not None
        assert v_token.purpose == "EMAIL_VERIFICATION"

        # 3. SUSPENDED: no reset or verify dispatched, generic response returned
        mock_reset.reset_mock()
        mock_verify.reset_mock()
        resp3 = await auth_service.request_password_reset(db=in_memory_db, email="suspended_pass_reset@fundamics.in")
        assert resp3.success is True
        assert mock_reset.await_count == 0
        assert mock_verify.await_count == 0
        stmt3 = select(PasswordResetToken).where(PasswordResetToken.user_id == suspended_user.id)
        assert (await in_memory_db.execute(stmt3)).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_mask_email_utility():
    """Verify email masking correctly conceals personal data for structured logs."""
    assert mask_email("admin@fundamics.in") == "a***n@fundamics.in"
    assert mask_email("ab@example.com") == "a*@example.com"
    assert mask_email("scholar.rahul@fundamics.in") == "s***********l@fundamics.in"
    assert mask_email(None) == "<invalid-email>"
    assert mask_email("invalid-address") == "<invalid-email>"
