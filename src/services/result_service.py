import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.audit import record_audit_log
from src.core.exceptions import NotFoundError, ValidationError, ConflictError
from src.models.academic import Class, Batch, Subject
from src.models.exam_result import Exam, Result
from src.models.user import Student
from src.schemas.exam_result import (
    CreateExamRequest,
    ExamResponse,
    EnterMarksItem,
    ResultResponse,
    StudentExamSummaryResponse,
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


result_service = ResultService()
