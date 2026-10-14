import uuid
import pytest
from datetime import time, date
from httpx import AsyncClient
from src.core.security import hash_password, create_access_token
from src.models.user import User, Student, Teacher, UserRole, UserStatus
from src.models.academic import Class, Batch


@pytest.mark.asyncio
async def test_notices_lifecycle_and_role_visibility(async_client: AsyncClient, db_session):
    admin = User(name="Admin Notice", email="admin_notice@fundamics.com", password_hash=hash_password("Admin@123"), role=UserRole.ADMIN, status=UserStatus.ACTIVE)
    s_user = User(name="Student Notice", email="student_notice@fundamics.com", password_hash=hash_password("Student@123"), role=UserRole.STUDENT, status=UserStatus.ACTIVE)
    t_user = User(name="Teacher Notice", email="teacher_notice@fundamics.com", password_hash=hash_password("Teacher@123"), role=UserRole.TEACHER, status=UserStatus.ACTIVE)
    db_session.add_all([admin, s_user, t_user])
    await db_session.flush()

    cls = Class(name="Class 9", code="CLS-9", board="CBSE", academic_year="2026-2027", status="ACTIVE")
    db_session.add(cls)
    await db_session.flush()
    batch = Batch(class_id=cls.id, name="Batch A", code="BA-1", start_time=time(10, 0), end_time=time(12, 0), status="ACTIVE")
    db_session.add(batch)
    await db_session.flush()

    student = Student(user_id=s_user.id, student_code="STU-901", class_id=cls.id, batch_id=batch.id, admission_date=date(2026, 4, 1), status="ACTIVE")
    teacher = Teacher(user_id=t_user.id, teacher_code="TCH-901", biometric_employee_id="BIO-901", status="ACTIVE")
    db_session.add_all([student, teacher])
    await db_session.flush()

    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)
    student_token = create_access_token(subject=str(s_user.id), role=UserRole.STUDENT.value)
    teacher_token = create_access_token(subject=str(t_user.id), role=UserRole.TEACHER.value)

    # 1. Admin creates notice for ALL
    n1 = await async_client.post(
        "/api/v1/admin/notices",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Diwali Vacation", "content": "Institute closed from Nov 1 to Nov 5", "target_audience": "ALL", "priority": "HIGH"},
    )
    assert n1.status_code == 201
    n1_id = n1.json()["id"]

    # 2. Admin creates notice for TEACHERS only
    n2 = await async_client.post(
        "/api/v1/admin/notices",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Faculty Meeting", "content": "Staff meeting on Monday 4 PM", "target_audience": "TEACHERS", "priority": "NORMAL"},
    )
    assert n2.status_code == 201
    n2_id = n2.json()["id"]

    # 3. Admin creates notice for STUDENTS only (Class 9)
    n3 = await async_client.post(
        "/api/v1/admin/notices",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Class 9 Assignment", "content": "Submit assignment by Friday", "target_audience": "STUDENTS", "class_id": str(cls.id), "priority": "URGENT"},
    )
    assert n3.status_code == 201
    n3_id = n3.json()["id"]

    # 4. Student queries feed -> Sees ALL and Class 9 notices, NOT teacher notice
    s_feed = await async_client.get(
        "/api/v1/notices",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert s_feed.status_code == 200
    s_ids = [n["id"] for n in s_feed.json()]
    assert n1_id in s_ids
    assert n3_id in s_ids
    assert n2_id not in s_ids

    # 5. Teacher queries feed -> Sees ALL and TEACHERS notice, NOT student notice
    t_feed = await async_client.get(
        "/api/v1/notices",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert t_feed.status_code == 200
    t_ids = [n["id"] for n in t_feed.json()]
    assert n1_id in t_ids
    assert n2_id in t_ids
    assert n3_id not in t_ids

    # 6. Admin update and delete notice
    upd = await async_client.patch(
        f"/api/v1/admin/notices/{n1_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Diwali Vacation (Updated Dates)"},
    )
    assert upd.status_code == 200
    assert upd.json()["title"] == "Diwali Vacation (Updated Dates)"

    delete_res = await async_client.delete(
        f"/api/v1/admin/notices/{n1_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_res.status_code == 200


@pytest.mark.asyncio
async def test_institute_settings_separation(async_client: AsyncClient, db_session):
    admin = User(name="Admin Settings", email="admin_sett@fundamics.com", password_hash=hash_password("Admin@123"), role=UserRole.ADMIN, status=UserStatus.ACTIVE)
    db_session.add(admin)
    await db_session.flush()

    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Fetch institute settings
    get_res = await async_client.get("/api/v1/admin/settings/institute", headers=headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert "institute_status" in data
    assert "erp_messaging_enabled" in data

    # 2. Update institute to CLOSED while keeping messaging enabled
    patch_closed = await async_client.patch(
        "/api/v1/admin/settings/institute",
        headers=headers,
        json={"institute_status": "CLOSED", "erp_messaging_enabled": True},
    )
    assert patch_closed.status_code == 200
    res_closed = patch_closed.json()
    assert res_closed["institute_status"] == "CLOSED"
    assert res_closed["erp_messaging_enabled"] is True

    # 3. Update messaging to False while keeping institute OPEN
    patch_open = await async_client.patch(
        "/api/v1/admin/settings/institute",
        headers=headers,
        json={"institute_status": "OPEN", "erp_messaging_enabled": False},
    )
    assert patch_open.status_code == 200
    res_open = patch_open.json()
    assert res_open["institute_status"] == "OPEN"
    assert res_open["erp_messaging_enabled"] is False
