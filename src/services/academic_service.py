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
            after_json={"code": new_class.code, "name": new_class.name},
            request_id=request_id,
        )
        await db.commit()

        return ClassResponse.model_validate(new_class)

    @staticmethod
    async def list_classes(db: AsyncSession) -> List[ClassResponse]:
        result = await db.execute(select(Class).order_by(Class.code.asc()))
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


academic_service = AcademicService()
