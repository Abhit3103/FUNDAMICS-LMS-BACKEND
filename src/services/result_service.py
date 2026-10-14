import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.audit import record_audit_log
from src.core.exceptions import NotFoundError, ValidationError, ConflictError, ForbiddenError
from src.models.academic import Class, Batch, Subject
from src.models.exam_result import Exam, Result
from src.models.user import Student, User, UserRole
from src.models.note_file import FileRecord
from src.services.note_service import note_service
from src.schemas.exam_result import (
    CreateExamRequest,
    ExamResponse,
    EnterMarksItem,
    ResultResponse,
    StudentExamSummaryResponse,
    ExamDetailResponse,
)


class ResultService:

    @staticmethod
    async def create_exam(
        db: AsyncSession,
        req: CreateExamRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> ExamResponse:
        class_obj = await db.get(Class, req.class_id)
        if not class_obj:
            raise NotFoundError("Class not found")

        if req.batch_id:
            batch_obj = await db.get(Batch, req.batch_id)
            if not batch_obj or batch_obj.class_id != req.class_id:
                raise ValidationError("Batch does not belong to the selected class")

        exam = Exam(
            class_id=req.class_id,
            batch_id=req.batch_id,
            name=req.name.strip(),
            date=req.date,
            status="SCHEDULED",
        )
        db.add(exam)
        await db.flush()

        await record_audit_log(
            db=db,
            action="EXAM_CREATED",
            resource_type="exam",
            resource_id=str(exam.id),
            actor_id=actor_id,
            after_json={"name": exam.name, "class_id": str(exam.class_id), "date": str(exam.date)},
            request_id=request_id,
        )
        await db.commit()

        return ExamResponse.model_validate(exam)

    @staticmethod
    async def record_bulk_marks(
        db: AsyncSession,
        exam_id: uuid.UUID,
        entries: List[EnterMarksItem],
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> int:
        exam = await db.get(Exam, exam_id)
        if not exam:
            raise NotFoundError("Exam container not found")

        inserted_count = 0
        for item in entries:
            if item.marks_obtained > item.max_marks:
                raise ValidationError(f"Marks obtained ({item.marks_obtained}) exceeds max marks ({item.max_marks})")

            # Check existing result
            stmt = select(Result).where(
                Result.exam_id == exam_id,
                Result.student_id == item.student_id,
                Result.subject_id == item.subject_id,
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()

            if existing:
                existing.marks_obtained = item.marks_obtained
                existing.max_marks = item.max_marks
                existing.grade = item.grade
            else:
                new_result = Result(
                    exam_id=exam_id,
                    student_id=item.student_id,
                    subject_id=item.subject_id,
                    marks_obtained=item.marks_obtained,
                    max_marks=item.max_marks,
                    grade=item.grade,
                )
                db.add(new_result)
            inserted_count += 1

        exam.status = "MARKS_ENTERED"

        await record_audit_log(
            db=db,
            action="MARKS_RECORDED",
            resource_type="exam",
            resource_id=str(exam_id),
            actor_id=actor_id,
            after_json={"records_count": inserted_count},
            request_id=request_id,
        )
        await db.commit()
        return inserted_count

    @staticmethod
    async def toggle_publication(
        db: AsyncSession,
        exam_id: uuid.UUID,
        publish: bool,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> int:
        exam = await db.get(Exam, exam_id)
        if not exam:
            raise NotFoundError("Exam not found")

        stmt = select(Result).where(Result.exam_id == exam_id)
        res = await db.execute(stmt)
        results = res.scalars().all()

        pub_time = datetime.now(timezone.utc) if publish else None
        for r in results:
            r.published_at = pub_time

        exam.status = "PUBLISHED" if publish else "MARKS_ENTERED"

        await record_audit_log(
            db=db,
            action="RESULTS_PUBLISHED" if publish else "RESULTS_UNPUBLISHED",
            resource_type="exam",
            resource_id=str(exam_id),
            actor_id=actor_id,
            after_json={"publish": publish, "affected_records": len(results)},
            request_id=request_id,
        )
        await db.commit()
        return len(results)

    @staticmethod
    async def get_student_results(
        db: AsyncSession,
        student_id: uuid.UUID,
    ) -> List[StudentExamSummaryResponse]:
        # Enforce published only
        stmt = (
            select(Result)
            .options(selectinload(Result.exam), selectinload(Result.subject))
            .where(
                Result.student_id == student_id,
                Result.published_at.is_not(None),
            )
            .order_by(Result.created_at.desc())
        )
        res = await db.execute(stmt)
        results = res.scalars().all()

        # Group by exam
        exams_dict = {}
        for r in results:
            eid = r.exam_id
            if eid not in exams_dict:
                exams_dict[eid] = {
                    "exam_id": eid,
                    "exam_name": r.exam.name,
                    "exam_date": r.exam.date,
                    "results": [],
                }

            pct = round((float(r.marks_obtained) / float(r.max_marks)) * 100, 2) if r.max_marks > 0 else 0.0
            exams_dict[eid]["results"].append(
                ResultResponse(
                    id=r.id,
                    exam_id=r.exam_id,
                    exam_name=r.exam.name,
                    student_id=r.student_id,
                    subject_id=r.subject_id,
                    subject_name=r.subject.name,
                    marks_obtained=float(r.marks_obtained),
                    max_marks=float(r.max_marks),
                    percentage=pct,
                    grade=r.grade,
                    published_at=r.published_at,
                )
            )

        summaries = []
        for eid, data in exams_dict.items():
            tot_obtained = sum(item.marks_obtained for item in data["results"])
            tot_max = sum(item.max_marks for item in data["results"])
            overall_pct = round((tot_obtained / tot_max) * 100, 2) if tot_max > 0 else 0.0

            summaries.append(
                StudentExamSummaryResponse(
                    exam_id=data["exam_id"],
                    exam_name=data["exam_name"],
                    exam_date=data["exam_date"],
                    total_marks_obtained=tot_obtained,
                    total_max_marks=tot_max,
                    overall_percentage=overall_pct,
                    results=data["results"],
                )
            )

        return summaries

    @staticmethod
    async def list_exams(
        db: AsyncSession,
        class_id: Optional[uuid.UUID] = None,
        batch_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExamResponse]:
        query = select(Exam).order_by(Exam.date.desc()).limit(limit).offset(offset)
        if class_id:
            query = query.where(Exam.class_id == class_id)
        if batch_id:
            query = query.where(Exam.batch_id == batch_id)
        if status:
            query = query.where(Exam.status == status)

        res = await db.execute(query)
        exams = res.scalars().all()
        return [ExamResponse.model_validate(e) for e in exams]

    @staticmethod
    async def get_exam_detail(
        db: AsyncSession,
        exam_id: uuid.UUID,
    ) -> ExamDetailResponse:
        stmt = (
            select(Exam)
            .options(
                selectinload(Exam.class_rel),
                selectinload(Exam.results).selectinload(Result.student).selectinload(Student.user),
                selectinload(Exam.results).selectinload(Result.subject),
            )
            .where(Exam.id == exam_id)
        )
        res = await db.execute(stmt)
        exam = res.scalar_one_or_none()
        if not exam:
            raise NotFoundError("Exam not found")

        results_list = []
        for r in exam.results:
            pct = round((float(r.marks_obtained) / float(r.max_marks)) * 100, 2) if r.max_marks > 0 else 0.0
            results_list.append(
                ResultResponse(
                    id=r.id,
                    exam_id=r.exam_id,
                    exam_name=exam.name,
                    student_id=r.student_id,
                    student_name=r.student.user.name if r.student and r.student.user else None,
                    student_code=r.student.student_code if r.student else None,
                    subject_id=r.subject_id,
                    subject_name=r.subject.name if r.subject else None,
                    marks_obtained=float(r.marks_obtained),
                    max_marks=float(r.max_marks),
                    percentage=pct,
                    grade=r.grade,
                    published_at=r.published_at,
                    document_file_id=r.document_file_id,
                    has_document=r.document_file_id is not None,
                )
            )

        return ExamDetailResponse(
            id=exam.id,
            class_id=exam.class_id,
            class_name=exam.class_rel.name if exam.class_rel else None,
            batch_id=exam.batch_id,
            name=exam.name,
            date=exam.date,
            status=exam.status,
            results=results_list,
        )

    @staticmethod
    async def upload_result_document(
        db: AsyncSession,
        result_id: uuid.UUID,
        file: UploadFile,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> ResultResponse:
        stmt = (
            select(Result)
            .options(
                selectinload(Result.exam),
                selectinload(Result.subject),
                selectinload(Result.student).selectinload(Student.user),
            )
            .where(Result.id == result_id)
        )
        res = await db.execute(stmt)
        result = res.scalar_one_or_none()
        if not result:
            raise NotFoundError("Result record not found")

        # Save file using note_service
        file_rec = await note_service.upload_file(db=db, file=file, actor_id=actor_id, request_id=request_id)
        result.document_file_id = file_rec.id

        await record_audit_log(
            db=db,
            action="RESULT_DOCUMENT_UPLOADED",
            resource_type="result",
            resource_id=str(result.id),
            actor_id=actor_id,
            after_json={"file_id": str(file_rec.id), "filename": file_rec.original_filename},
            request_id=request_id,
        )
        await db.commit()

        pct = round((float(result.marks_obtained) / float(result.max_marks)) * 100, 2) if result.max_marks > 0 else 0.0
        return ResultResponse(
            id=result.id,
            exam_id=result.exam_id,
            exam_name=result.exam.name if result.exam else None,
            student_id=result.student_id,
            student_name=result.student.user.name if result.student and result.student.user else None,
            student_code=result.student.student_code if result.student else None,
            subject_id=result.subject_id,
            subject_name=result.subject.name if result.subject else None,
            marks_obtained=float(result.marks_obtained),
            max_marks=float(result.max_marks),
            percentage=pct,
            grade=result.grade,
            published_at=result.published_at,
            document_file_id=result.document_file_id,
            has_document=True,
        )

    @staticmethod
    async def get_authorized_result_document(
        db: AsyncSession,
        result_id: uuid.UUID,
        user: User,
    ) -> Tuple[str, str, str]:
        stmt = (
            select(Result)
            .options(
                selectinload(Result.student),
                selectinload(Result.document_file),
            )
            .where(Result.id == result_id)
        )
        res = await db.execute(stmt)
        result = res.scalar_one_or_none()
        if not result or not result.document_file_id:
            raise NotFoundError("Result document not found")

        # Ownership & Security validation:
        if user.role == UserRole.STUDENT:
            if not result.student or result.student.user_id != user.id:
                raise ForbiddenError("You can only access your own result documents")
            if result.published_at is None:
                raise ForbiddenError("This result has not been published yet")

        file_rec = result.document_file or await db.get(FileRecord, result.document_file_id)
        if not file_rec or not os.path.exists(file_rec.storage_key):
            raise NotFoundError("Underlying document file is unavailable")

        return file_rec.storage_key, file_rec.original_filename, file_rec.mime_type


result_service = ResultService()
