import uuid
from typing import List
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin, require_student
from src.database import get_db
from src.models.user import User
from src.schemas.note_file import NoteCreateRequest, NoteResponse, FileRecordResponse
from src.services.note_service import note_service

admin_notes_router = APIRouter(prefix="/admin", tags=["Admin — Study Materials & Notes"])
student_notes_router = APIRouter(prefix="/student", tags=["Student — My Notes"])


@admin_notes_router.post("/files/upload", response_model=FileRecordResponse, status_code=status.HTTP_201_CREATED)
async def upload_material_file(
    file: UploadFile = File(...),
    request: Request = None,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Securely upload file to private storage."""
    request_id = getattr(request.state, "request_id", None) if request else None
    record = await note_service.upload_file(
        db=db,
        file=file,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return FileRecordResponse.model_validate(record)


@admin_notes_router.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    req: NoteCreateRequest,
    file_id: uuid.UUID = Form(...),
    request: Request = None,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create note metadata and associate with uploaded file record."""
    request_id = getattr(request.state, "request_id", None) if request else None
    return await note_service.create_note(
        db=db,
        req=req,
        file_id=file_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@student_notes_router.get("/me/notes", response_model=List[NoteResponse], status_code=status.HTTP_200_OK)
async def get_my_notes(
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Student-only: Query notes strictly authorized for the student's current class/batch."""
    return await note_service.get_student_notes(
        db=db,
        student_id=current_user.student.id,
    )


@student_notes_router.get("/me/notes/{note_id}/download")
async def download_note_file(
    note_id: uuid.UUID,
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Student-only: Stream authorized note attachment after verifying class/batch access."""
    file_path, filename, mime = await note_service.get_authorized_file(
        db=db,
        note_id=note_id,
        student=current_user.student,
    )
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=mime,
    )
