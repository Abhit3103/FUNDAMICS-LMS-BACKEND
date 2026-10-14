import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import record_audit_log
from src.core.exceptions import ConflictError, NotFoundError
from src.models.academic import Class, Batch, Subject
from src.schemas.academic import (
    CreateClassRequest,
    UpdateClassRequest,
    ClassResponse,
    CreateBatchRequest,
    UpdateBatchRequest,
    BatchResponse,
    CreateSubjectRequest,
    UpdateSubjectRequest,
    SubjectResponse,
)


class AcademicService:

    @staticmethod
    async def create_class(
        db: AsyncSession,
        req: CreateClassRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> ClassResponse:
        existing = await db.execute(select(Class).where(Class.code == req.code.strip()))
        if existing.scalar_one_or_none():
            raise ConflictError("A class with this code already exists")

        new_class = Class(
            name=req.name.strip(),
            code=req.code.strip(),
            board=req.board.strip() if req.board else "CBSE",
            academic_year=req.academic_year.strip(),
            status="ACTIVE",
        )
        db.add(new_class)
        await db.flush()

        await record_audit_log(
            db=db,
            action="CLASS_CREATED",
            resource_type="class",
            resource_id=str(new_class.id),
            actor_id=actor_id,
            after_json={"code": new_class.code, "name": new_class.name, "board": new_class.board},
            request_id=request_id,
        )
        await db.commit()

        return ClassResponse.model_validate(new_class)

    @staticmethod
    async def list_classes(
        db: AsyncSession,
        board: Optional[str] = None,
    ) -> List[ClassResponse]:
        query = select(Class).order_by(Class.code.asc())
        if board:
            query = query.where(Class.board.ilike(board.strip()))
        result = await db.execute(query)
        return [ClassResponse.model_validate(c) for c in result.scalars().all()]

    @staticmethod
    async def create_batch(
        db: AsyncSession,
        req: CreateBatchRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> BatchResponse:
        class_obj = await db.get(Class, req.class_id)
        if not class_obj:
            raise NotFoundError("Referenced class does not exist")

        existing = await db.execute(
            select(Batch).where(Batch.class_id == req.class_id, Batch.code == req.code.strip())
        )
        if existing.scalar_one_or_none():
            raise ConflictError("A batch with this code already exists in this class")

        new_batch = Batch(
            class_id=req.class_id,
            name=req.name.strip(),
            code=req.code.strip(),
            start_time=req.start_time,
            end_time=req.end_time,
            status="ACTIVE",
        )
        db.add(new_batch)
        await db.flush()

        await record_audit_log(
            db=db,
            action="BATCH_CREATED",
            resource_type="batch",
            resource_id=str(new_batch.id),
            actor_id=actor_id,
            after_json={"class_id": str(req.class_id), "code": new_batch.code, "name": new_batch.name},
            request_id=request_id,
        )
        await db.commit()

        return BatchResponse.model_validate(new_batch)

    @staticmethod
    async def list_batches(db: AsyncSession, class_id: Optional[uuid.UUID] = None) -> List[BatchResponse]:
        query = select(Batch).order_by(Batch.code.asc())
        if class_id:
            query = query.where(Batch.class_id == class_id)
        result = await db.execute(query)
        return [BatchResponse.model_validate(b) for b in result.scalars().all()]

    @staticmethod
    async def create_subject(
        db: AsyncSession,
        req: CreateSubjectRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> SubjectResponse:
        class_obj = await db.get(Class, req.class_id)
        if not class_obj:
            raise NotFoundError("Referenced class does not exist")

        existing = await db.execute(
            select(Subject).where(Subject.class_id == req.class_id, Subject.code == req.code.strip())
        )
        if existing.scalar_one_or_none():
            raise ConflictError("A subject with this code already exists in this class")

        new_subject = Subject(
            class_id=req.class_id,
            name=req.name.strip(),
            code=req.code.strip(),
            status="ACTIVE",
        )
        db.add(new_subject)
        await db.flush()

        await record_audit_log(
            db=db,
            action="SUBJECT_CREATED",
            resource_type="subject",
            resource_id=str(new_subject.id),
            actor_id=actor_id,
            after_json={"class_id": str(req.class_id), "code": new_subject.code, "name": new_subject.name},
            request_id=request_id,
        )
        await db.commit()

        return SubjectResponse.model_validate(new_subject)

    @staticmethod
    async def list_subjects(db: AsyncSession, class_id: Optional[uuid.UUID] = None) -> List[SubjectResponse]:
        query = select(Subject).order_by(Subject.code.asc())
        if class_id:
            query = query.where(Subject.class_id == class_id)
        result = await db.execute(query)
        return [SubjectResponse.model_validate(s) for s in result.scalars().all()]

    @staticmethod
    async def update_class(
        db: AsyncSession,
        class_id: uuid.UUID,
        req: UpdateClassRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> ClassResponse:
        class_obj = await db.get(Class, class_id)
        if not class_obj:
            raise NotFoundError("Class not found")

        updated = {}
        if req.name is not None and req.name.strip():
            class_obj.name = req.name.strip()
            updated["name"] = class_obj.name
        if req.board is not None and req.board.strip():
            class_obj.board = req.board.strip()
            updated["board"] = class_obj.board
        if req.academic_year is not None and req.academic_year.strip():
            class_obj.academic_year = req.academic_year.strip()
            updated["academic_year"] = class_obj.academic_year
        if req.status is not None:
            class_obj.status = req.status.strip()
            updated["status"] = class_obj.status

        await record_audit_log(
            db=db,
            action="CLASS_UPDATED",
            resource_type="class",
            resource_id=str(class_id),
            actor_id=actor_id,
            after_json=updated,
            request_id=request_id,
        )
        await db.commit()
        await db.refresh(class_obj)
        return ClassResponse.model_validate(class_obj)

    @staticmethod
    async def delete_class(
        db: AsyncSession,
        class_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> bool:
        class_obj = await db.get(Class, class_id)
        if not class_obj:
            raise NotFoundError("Class not found")

        class_obj.status = "INACTIVE"
        await record_audit_log(
            db=db,
            action="CLASS_DEACTIVATED",
            resource_type="class",
            resource_id=str(class_id),
            actor_id=actor_id,
            request_id=request_id,
        )
        await db.commit()
        return True

    @staticmethod
    async def update_batch(
        db: AsyncSession,
        batch_id: uuid.UUID,
        req: UpdateBatchRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> BatchResponse:
        batch_obj = await db.get(Batch, batch_id)
        if not batch_obj:
            raise NotFoundError("Batch not found")

        updated = {}
        if req.name is not None and req.name.strip():
            batch_obj.name = req.name.strip()
            updated["name"] = batch_obj.name
        if req.start_time is not None:
            batch_obj.start_time = req.start_time
            updated["start_time"] = str(batch_obj.start_time)
        if req.end_time is not None:
            batch_obj.end_time = req.end_time
            updated["end_time"] = str(batch_obj.end_time)
        if req.status is not None:
            batch_obj.status = req.status.strip()
            updated["status"] = batch_obj.status

        await record_audit_log(
            db=db,
            action="BATCH_UPDATED",
            resource_type="batch",
            resource_id=str(batch_id),
            actor_id=actor_id,
            after_json=updated,
            request_id=request_id,
        )
        await db.commit()
        await db.refresh(batch_obj)
        return BatchResponse.model_validate(batch_obj)

    @staticmethod
    async def delete_batch(
        db: AsyncSession,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> bool:
        batch_obj = await db.get(Batch, batch_id)
        if not batch_obj:
            raise NotFoundError("Batch not found")

        batch_obj.status = "INACTIVE"
        await record_audit_log(
            db=db,
            action="BATCH_DEACTIVATED",
            resource_type="batch",
            resource_id=str(batch_id),
            actor_id=actor_id,
            request_id=request_id,
        )
        await db.commit()
        return True

    @staticmethod
    async def update_subject(
        db: AsyncSession,
        subject_id: uuid.UUID,
        req: UpdateSubjectRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> SubjectResponse:
        subject_obj = await db.get(Subject, subject_id)
        if not subject_obj:
            raise NotFoundError("Subject not found")

        updated = {}
        if req.name is not None and req.name.strip():
            subject_obj.name = req.name.strip()
            updated["name"] = subject_obj.name
        if req.status is not None:
            subject_obj.status = req.status.strip()
            updated["status"] = subject_obj.status

        await record_audit_log(
            db=db,
            action="SUBJECT_UPDATED",
            resource_type="subject",
            resource_id=str(subject_id),
            actor_id=actor_id,
            after_json=updated,
            request_id=request_id,
        )
        await db.commit()
        await db.refresh(subject_obj)
        return SubjectResponse.model_validate(subject_obj)

    @staticmethod
    async def delete_subject(
        db: AsyncSession,
        subject_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> bool:
        subject_obj = await db.get(Subject, subject_id)
        if not subject_obj:
            raise NotFoundError("Subject not found")

        subject_obj.status = "INACTIVE"
        await record_audit_log(
            db=db,
            action="SUBJECT_DEACTIVATED",
            resource_type="subject",
            resource_id=str(subject_id),
            actor_id=actor_id,
            request_id=request_id,
        )
        await db.commit()
        return True


academic_service = AcademicService()
