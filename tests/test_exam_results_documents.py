import uuid
import pytest
from datetime import date, datetime, timezone, time
from httpx import AsyncClient
from src.core.security import hash_password, create_access_token
from src.models.user import User, Student, UserRole, UserStatus
from src.models.academic import Class, Batch, Subject
from src.models.exam_result import Exam, Result


@pytest.mark.asyncio
async def test_exam_listing_and_secure_result_document_upload(async_client: AsyncClient, db_session):
    # Setup users
    admin = User(
        name="Admin Results",
        email="admin_results@fundamics.com",
        password_hash=hash_password("Admin@123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)

    s1_user = User(
        name="Student One",
        email="student1@fundamics.com",
        password_hash=hash_password("Student@123"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    s2_user = User(
        name="Student Two",
        email="student2@fundamics.com",
        password_hash=hash_password("Student@123"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    db_session.add_all([s1_user, s2_user])
    await db_session.flush()

    # Setup academics
    cls = Class(name="Class 12 CBSE", code="C12-CBSE", board="CBSE", academic_year="2026-2027", status="ACTIVE")
    db_session.add(cls)
    await db_session.flush()

    batch = Batch(class_id=cls.id, name="Evening Batch", code="EB-1", start_time=time(17, 0), end_time=time(19, 0), status="ACTIVE")
    subject = Subject(class_id=cls.id, name="Physics", code="PHY-12", status="ACTIVE")
    db_session.add_all([batch, subject])
    await db_session.flush()

    student1 = Student(user_id=s1_user.id, student_code="STU-001", class_id=cls.id, batch_id=batch.id, admission_date=date.today(), status="ACTIVE")
    student2 = Student(user_id=s2_user.id, student_code="STU-002", class_id=cls.id, batch_id=batch.id, admission_date=date.today(), status="ACTIVE")
    db_session.add_all([student1, student2])
    await db_session.flush()

    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)
    s1_token = create_access_token(subject=str(s1_user.id), role=UserRole.STUDENT.value)
    s2_token = create_access_token(subject=str(s2_user.id), role=UserRole.STUDENT.value)

    # 1. Create Exam
    exam_res = await async_client.post(
        "/api/v1/admin/exams",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"class_id": str(cls.id), "batch_id": str(batch.id), "name": "Physics Midterm", "date": "2026-10-15"},
    )
    assert exam_res.status_code == 201
    exam_id = exam_res.json()["id"]

    # 2. List exams
    exams_list = await async_client.get(
        f"/api/v1/admin/exams?class_id={cls.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert exams_list.status_code == 200
    assert any(e["id"] == exam_id for e in exams_list.json())

    # 3. Enter Marks
    marks_res = await async_client.post(
        "/api/v1/admin/exams/marks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "exam_id": exam_id,
            "marks_entries": [
                {"student_id": str(student1.id), "subject_id": str(subject.id), "marks_obtained": 85.0, "max_marks": 100.0, "grade": "A"},
                {"student_id": str(student2.id), "subject_id": str(subject.id), "marks_obtained": 92.0, "max_marks": 100.0, "grade": "A+"},
            ],
        },
    )
    assert marks_res.status_code == 200

    # 4. Query Exam Detail (Roster)
    detail_res = await async_client.get(
        f"/api/v1/admin/exams/{exam_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert len(detail_data["results"]) == 2
    r1_id = next(r["id"] for r in detail_data["results"] if r["student_id"] == str(student1.id))

    # 5. Admin upload scorecard document for student1
    file_content = b"%PDF-1.4 Mock Scorecard Document Content"
    upload_res = await async_client.post(
        f"/api/v1/admin/results/{r1_id}/document",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("scorecard_student1.pdf", file_content, "application/pdf")},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["has_document"] is True

    # 6. Student downloads before publish -> FORBIDDEN (403)
    early_dl = await async_client.get(
        f"/api/v1/student/me/results/{r1_id}/document",
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert early_dl.status_code == 403

    # 7. Publish Exam
    pub_res = await async_client.post(
        "/api/v1/admin/exams/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"exam_id": exam_id, "publish": True},
    )
    assert pub_res.status_code == 200

    # 8. Student1 downloads own published scorecard -> SUCCESS (200)
    s1_dl = await async_client.get(
        f"/api/v1/student/me/results/{r1_id}/document",
        headers={"Authorization": f"Bearer {s1_token}"},
    )
    assert s1_dl.status_code == 200
    assert s1_dl.content == file_content

    # 9. IDOR Defense: Student2 attempts to download Student1's scorecard -> FORBIDDEN (403)
    s2_dl = await async_client.get(
        f"/api/v1/student/me/results/{r1_id}/document",
        headers={"Authorization": f"Bearer {s2_token}"},
    )
    assert s2_dl.status_code == 403
