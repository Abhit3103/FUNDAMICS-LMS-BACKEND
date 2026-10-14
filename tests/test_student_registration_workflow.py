import uuid
import pytest
from datetime import date, time
from httpx import AsyncClient
from sqlalchemy import select
from src.core.security import hash_password, create_access_token
from src.models.user import User, Student, UserRole, UserStatus
from src.models.academic import Class, Batch
from src.models.auth_session import VerificationToken, PasswordResetToken


@pytest.mark.asyncio
async def test_student_self_registration_and_verification_flow(async_client: AsyncClient, db_session):
    # Setup class and batch
    cls = Class(name="Grade 11 - Science", code="G11-SCI", board="CBSE", academic_year="2026-2027", status="ACTIVE")
    db_session.add(cls)
    await db_session.flush()

    batch = Batch(class_id=cls.id, name="Morning Batch", code="MB-1", start_time=time(9, 0), end_time=time(11, 0), status="ACTIVE")
    db_session.add(batch)
    await db_session.flush()

    # Setup admin user
    admin = User(
        name="Admin User",
        email="admin_reg@fundamics.com",
        password_hash=hash_password("Admin@123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    await db_session.flush()
    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)

    # 1. Register student
    reg_payload = {
        "name": "Aarav Sharma",
        "email": "aarav@example.com",
        "phone": "+919876543210",
        "password": "Password@123",
        "class_id": str(cls.id),
        "batch_id": str(batch.id),
    }
    resp = await async_client.post("/api/v1/auth/register/student", json=reg_payload)
    assert resp.status_code == 201
    assert resp.json()["success"] is True

    # Duplicate registration fails
    dup_resp = await async_client.post("/api/v1/auth/register/student", json=reg_payload)
    assert dup_resp.status_code == 409

    # Find created user
    u_res = await db_session.execute(select(User).where(User.email == "aarav@example.com"))
    student_user = u_res.scalar_one()
    assert student_user.status == UserStatus.PENDING_VERIFICATION
    assert student_user.email_verified_at is None

    # Find verification token
    v_res = await db_session.execute(select(VerificationToken).where(VerificationToken.user_id == student_user.id))
    v_token = v_res.scalar_one()

    # 2. Verify with wrong token fails
    bad_verify = await async_client.post("/api/v1/auth/verify-email", json={"token": "invalid-token"})
    assert bad_verify.status_code == 422

    # Verify email using the token (mock token hash match by querying raw token)
    # We simulate verifying with a known token
    from src.core.security import hash_token
    test_raw_token = "valid_test_token_123"
    v_token.token_hash = hash_token(test_raw_token)
    await db_session.flush()

    verify_resp = await async_client.post("/api/v1/auth/verify-email", json={"token": test_raw_token})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["success"] is True

    # Refresh user
    await db_session.refresh(student_user)
    assert student_user.status == UserStatus.PENDING_APPROVAL
    assert student_user.email_verified_at is not None

    # 3. Admin lists pending registrations
    pending_resp = await async_client.get(
        "/api/v1/admin/users/pending-registrations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(p["user_id"] == str(student_user.id) for p in pending_list)

    # 4. Admin approves registration
    approve_resp = await async_client.post(
        f"/api/v1/admin/users/{student_user.id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"remarks": "Documents verified"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "ACTIVE"

    await db_session.refresh(student_user)
    assert student_user.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_password_management_workflow(async_client: AsyncClient, db_session):
    user = User(
        name="Pooja Patel",
        email="pooja@example.com",
        phone="+919876543222",
        password_hash=hash_password("OldPassword@123"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()

    user_token = create_access_token(subject=str(user.id), role=UserRole.STUDENT.value)

    # 1. Authenticated Change Password
    # Wrong old password fails
    bad_change = await async_client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"old_password": "WrongPassword", "new_password": "NewPassword@123"},
    )
    assert bad_change.status_code == 401

    # Correct old password succeeds
    good_change = await async_client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"old_password": "OldPassword@123", "new_password": "NewPassword@123"},
    )
    assert good_change.status_code == 200
    assert good_change.json()["success"] is True

    # 2. Forgot Password and Reset flow
    forgot_resp = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "pooja@example.com"},
    )
    assert forgot_resp.status_code == 200

    # Inject mock token
    from src.core.security import hash_token
    reset_raw = "test_reset_token_xyz"
    r_res = await db_session.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    r_token = r_res.scalars().first()
    r_token.token_hash = hash_token(reset_raw)
    await db_session.flush()

    reset_resp = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_raw, "new_password": "BrandNewPassword@123"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["success"] is True

    # 3. Profile update
    profile_resp = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"name": "Pooja P. Patel", "phone": "+919876543999"},
    )
    assert profile_resp.status_code == 200
    assert profile_resp.json()["name"] == "Pooja P. Patel"
    assert profile_resp.json()["phone"] == "+919876543999"
