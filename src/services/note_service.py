import hashlib
import os
import uuid
from typing import List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.config import settings
from src.core.audit import record_audit_log
from src.core.exceptions import NotFoundError, ForbiddenError, ValidationError
from src.models.academic import Class, Batch, Subject
from src.models.note_file import FileRecord, Note
from src.models.user import Student
from src.schemas.note_file import NoteCreateRequest, NoteResponse, FileRecordResponse


class NoteService:

    @staticmethod
    async def upload_file(
        db: AsyncSession,
        file: UploadFile,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> FileRecord:
        # Validate storage directory
        os.makedirs(settings.LOCAL_STORAGE_DIR, exist_ok=True)

        content = await file.read()
        size_bytes = len(content)
        checksum = hashlib.sha256(content).hexdigest()

        # Generate unique storage key
        file_ext = os.path.splitext(file.filename or "")[1]
        storage_filename = f"{uuid.uuid4()}{file_ext}"
        storage_path = os.path.join(settings.LOCAL_STORAGE_DIR, storage_filename)

        with open(storage_path, "wb") as f:
            f.write(content)

        file_record = FileRecord(
            storage_key=storage_path,
            original_filename=file.filename or "uploaded_file",
            mime_type=file.content_type or "application/octet-stream",
            size_bytes=size_bytes,
            checksum=checksum,
            visibility="PRIVATE",
            created_by=actor_id,
        )
        db.add(file_record)
        await db.commit()
        return file_record

    @staticmethod
    async def create_note(
        db: AsyncSession,
        req: NoteCreateRequest,
        file_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> NoteResponse:
        file_record = await db.get(FileRecord, file_id)
        if not file_record:
            raise NotFoundError("Attached file record not found")

        subject = await db.get(Subject, req.subject_id)
        if not subject or subject.class_id != req.class_id:
            raise ValidationError("Subject does not belong to the selected class")

        if req.batch_id:
            batch = await db.get(Batch, req.batch_id)
            if not batch or batch.class_id != req.class_id:
                raise ValidationError("Batch does not belong to the selected class")

        note = Note(
            title=req.title.strip(),
            description=req.description,
            class_id=req.class_id,
            batch_id=req.batch_id,
            subject_id=req.subject_id,
            file_id=file_id,
            status="PUBLISHED",
            created_by=actor_id,
        )
        db.add(note)
        await db.flush()

        await record_audit_log(
            db=db,
            action="NOTE_PUBLISHED",
            resource_type="note",
            resource_id=str(note.id),
            actor_id=actor_id,
            after_json={"title": note.title, "class_id": str(note.class_id), "file_id": str(file_id)},
            request_id=request_id,
        )
        await db.commit()

        return NoteResponse(
            id=note.id,
            title=note.title,
            description=note.description,
            class_id=note.class_id,
            batch_id=note.batch_id,
            subject_id=note.subject_id,
            subject_name=subject.name,
            file_id=note.file_id,
            original_filename=file_record.original_filename,
            file_size_bytes=file_record.size_bytes,
            status=note.status,
            created_at=note.created_at,
        )

    @staticmethod
    async def get_student_notes(
        db: AsyncSession,
        student_id: uuid.UUID,
    ) -> List[NoteResponse]:
        student = await db.get(Student, student_id)
        if not student:
            raise NotFoundError("Student not found")

        # Query notes: published, matching student's class, and either batch is null (unrestricted) or matches student's batch
        stmt = (
            select(Note)
            .options(selectinload(Note.subject), selectinload(Note.file_record))
            .where(
                Note.status == "PUBLISHED",
                Note.class_id == student.class_id,
                or_(Note.batch_id.is_(None), Note.batch_id == student.batch_id),
            )
            .order_by(Note.created_at.desc())
        )
        res = await db.execute(stmt)
        notes = res.scalars().all()

        return [
            NoteResponse(
                id=n.id,
                title=n.title,
                description=n.description,
                class_id=n.class_id,
                batch_id=n.batch_id,
                subject_id=n.subject_id,
                subject_name=n.subject.name if n.subject else None,
                file_id=n.file_id,
                original_filename=n.file_record.original_filename if n.file_record else None,
                file_size_bytes=n.file_record.size_bytes if n.file_record else None,
                status=n.status,
                created_at=n.created_at,
            )
            for n in notes
        ]

    @staticmethod
    async def get_authorized_file(
        db: AsyncSession,
        note_id: uuid.UUID,
        student: Student,
    ) -> Tuple[str, str, str]:
        """Validates student authorization and returns (file_path, filename, mime_type)."""
        note = await db.get(Note, note_id)
        if not note or note.status != "PUBLISHED":
            raise NotFoundError("Note material not found")

        if note.class_id != student.class_id:
            raise ForbiddenError("You are not enrolled in the class for this material")

        if note.batch_id is not None and note.batch_id != student.batch_id:
            raise ForbiddenError("This material is restricted to another batch")

        file_rec = await db.get(FileRecord, note.file_id)
        if not file_rec or not os.path.exists(file_rec.storage_key):
            raise NotFoundError("Underlying file content is unavailable")

        return file_rec.storage_key, file_rec.original_filename, file_rec.mime_type


note_service = NoteService()
