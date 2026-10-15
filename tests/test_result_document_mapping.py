import uuid
import pytest
from datetime import date, time
from httpx import AsyncClient
from src.core.security import hash_password, create_access_token
from src.models.user import User, Student, UserRole, UserStatus
from src.models.academic import Class, Batch, Subject
from src.models.exam_result import Exam, Result
from src.models.note_file import FileRecord


@pytest.mark.asyncio
async def test_direct_pdf_to_student_result_document_mapping_suite(async_client: AsyncClient, db_session):
    # Setup users
    admin = User(
        name="Admin Results Manager",
        email="admin_results_mgr@fundamics.com",
        password_hash=hash_password("Admin@123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    student_user = User(
        name="Aarav Sharma",
        email="aarav.sharma@fundamics.com",
        password_hash=hash_password("Student@123"),
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    db_session.add_all([admin, student_user])
    await db_session.flush()

    # Setup academics
    cls = Class(name="Class 11 Science", code="C11-SCI", board="CBSE", academic_year="2026-2027", status="ACTIVE")
    db_session.add(cls)
    await db_session.flush()

    batch = Batch(class_id=cls.id, name="Morning Batch A", code="MBA-1", start_time=time(8, 0), end_time=time(10, 0), status="ACTIVE")
    subject = Subject(class_id=cls.id, name="Mathematics", code="MATH-11", status="ACTIVE")
    db_session.add_all([batch, subject])
    await db_session.flush()

    student = Student(user_id=student_user.id, student_code="STU-MATH-01", class_id=cls.id, batch_id=batch.id, admission_date=date.today(), status="ACTIVE")
    db_session.add(student)
    await db_session.flush()

    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)
    student_token = create_access_token(subject=str(student_user.id), role=UserRole.STUDENT.value)

    # 1. Create Exam
    exam_res = await async_client.post(
        "/api/v1/admin/exams",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"class_id": str(cls.id), "batch_id": str(batch.id), "name": "Calculus Quiz 1", "date": "2026-10-15"},
    )
    assert exam_res.status_code == 201
    exam_id = exam_res.json()["id"]

    # 2. Upload file via /api/v1/admin/files/upload
    pdf_content = b"%PDF-1.4 Mock Calculus Answer Sheet and Report"
    upload_res = await async_client.post(
        "/api/v1/admin/files/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("calculus_aarav.pdf", pdf_content, "application/pdf")},
    )
    assert upload_res.status_code == 201
    uploaded_file = upload_res.json()
    file_id = uploaded_file["id"]
    assert uploaded_file["original_filename"] == "calculus_aarav.pdf"

    # 3. Test enter marks with embedded file_id and remarks (without explicit subject_id to verify fallback)
    marks_res = await async_client.post(
        "/api/v1/admin/exams/marks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "exam_id": exam_id,
            "marks_entries": [
                {
                    "student_id": str(student.id),
                    "marks_obtained": 95.0,
                    "max_marks": 100.0,
                    "grade": "A+",
                    "remarks": "Outstanding calculus derivation.",
                    "file_id": file_id,
                }
            ],
        },
    )
    assert marks_res.status_code == 200
    assert marks_res.json()["success"] is True

    # 4. Query exam details and verify result record contains document and remarks
    detail_res = await async_client.get(
        f"/api/v1/admin/exams/{exam_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_res.status_code == 200
    results = detail_res.json()["results"]
    assert len(results) == 1
    r = results[0]
    result_id = r["id"]
    assert r["marks_obtained"] == 95.0
    assert r["remarks"] == "Outstanding calculus derivation."
    assert r["has_document"] is True
    assert r["document_file_id"] == file_id
    assert r["document_filename"] == "calculus_aarav.pdf"

    # 5. Test Unlink Document endpoint DELETE /api/v1/admin/results/{result_id}/document
    unlink_res = await async_client.delete(
        f"/api/v1/admin/results/{result_id}/document",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert unlink_res.status_code == 200
    assert unlink_res.json()["has_document"] is False
    assert unlink_res.json()["document_file_id"] is None

    # 6. Test Mapping by Result ID: POST /api/v1/admin/results/{result_id}/document-mapping
    map_res1 = await async_client.post(
        f"/api/v1/admin/results/{result_id}/document-mapping",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"file_id": file_id},
    )
    assert map_res1.status_code == 200
    assert map_res1.json()["has_document"] is True
    assert map_res1.json()["document_file_id"] == file_id

    # 7. Test Mapping by Exam & Student ID: POST /api/v1/admin/exams/{exam_id}/students/{student_id}/document-mapping
    map_res2 = await async_client.post(
        f"/api/v1/admin/exams/{exam_id}/students/{student.id}/document-mapping",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"file_id": file_id},
    )
    assert map_res2.status_code == 200
    assert map_res2.json()["has_document"] is True

    # 8. Test Direct Mapping Root Endpoint: POST /api/v1/admin/results/document-mapping
    map_res3 = await async_client.post(
        "/api/v1/admin/results/document-mapping",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "exam_id": exam_id,
            "student_id": str(student.id),
            "file_id": file_id,
            "remarks": "Updated remark via direct mapping.",
        },
    )
    assert map_res3.status_code == 200
    assert map_res3.json()["remarks"] == "Updated remark via direct mapping."

    # 9. Test Direct Multipart Upload for Student & Exam: POST /api/v1/admin/exams/{exam_id}/students/{student_id}/document
    new_pdf = b"%PDF-1.4 Direct Exam Upload Scorecard Content"
    direct_up_res = await async_client.post(
        f"/api/v1/admin/exams/{exam_id}/students/{student.id}/document?remarks=Directly%20Uploaded",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("direct_aarav_scorecard.pdf", new_pdf, "application/pdf")},
    )
    assert direct_up_res.status_code == 200
    assert direct_up_res.json()["has_document"] is True
    assert direct_up_res.json()["document_filename"] == "direct_aarav_scorecard.pdf"
    assert direct_up_res.json()["remarks"] == "Directly Uploaded"

    # 10. Publish results and verify Student can download the scorecard
    pub_res = await async_client.post(
        "/api/v1/admin/exams/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"exam_id": exam_id, "publish": True},
    )
    assert pub_res.status_code == 200

    # Student downloads published scorecard
    stu_dl = await async_client.get(
        f"/api/v1/student/me/results/{result_id}/document",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert stu_dl.status_code == 200
    assert stu_dl.content == new_pdf
