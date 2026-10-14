import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin
from src.database import get_db
from src.models.user import User
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
from src.services.academic_service import academic_service

router = APIRouter(prefix="/admin", tags=["Admin — Academics (Classes, Batches, Subjects)"])


# Classes
@router.post("/classes", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
async def create_class(
    req: CreateClassRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create a new academic class with board designation."""
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.create_class(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.get("/classes", response_model=List[ClassResponse], status_code=status.HTTP_200_OK)
async def list_classes(
    board: Optional[str] = Query(None, description="Filter classes by board (e.g. CBSE, ICSE, STATE_BOARD)"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query academic classes with optional board filter."""
    return await academic_service.list_classes(db=db, board=board)


@router.patch("/classes/{class_id}", response_model=ClassResponse, status_code=status.HTTP_200_OK)
async def update_class(
    class_id: uuid.UUID,
    req: UpdateClassRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update class name, board, academic year, or status."""
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.update_class(
        db=db,
        class_id=class_id,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.delete("/classes/{class_id}", status_code=status.HTTP_200_OK)
async def delete_class(
    class_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Deactivate class."""
    request_id = getattr(request.state, "request_id", None)
    success = await academic_service.delete_class(
        db=db,
        class_id=class_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": success, "message": "Class deactivated"}


# Batches
@router.post("/batches", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    req: CreateBatchRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create a batch linked to an academic class."""
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.create_batch(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.get("/batches", response_model=List[BatchResponse], status_code=status.HTTP_200_OK)
async def list_batches(
    class_id: Optional[uuid.UUID] = Query(None, description="Filter by class ID"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query batches with optional class filter."""
    return await academic_service.list_batches(db=db, class_id=class_id)


@router.patch("/batches/{batch_id}", response_model=BatchResponse, status_code=status.HTTP_200_OK)
async def update_batch(
    batch_id: uuid.UUID,
    req: UpdateBatchRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update batch name, timings, or status."""
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.update_batch(
        db=db,
        batch_id=batch_id,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.delete("/batches/{batch_id}", status_code=status.HTTP_200_OK)
async def delete_batch(
    batch_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Deactivate batch."""
    request_id = getattr(request.state, "request_id", None)
    success = await academic_service.delete_batch(
        db=db,
        batch_id=batch_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": success, "message": "Batch deactivated"}


# Subjects
@router.post("/subjects", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    req: CreateSubjectRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create a curriculum subject for a class."""
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.create_subject(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.get("/subjects", response_model=List[SubjectResponse], status_code=status.HTTP_200_OK)
async def list_subjects(
    class_id: Optional[uuid.UUID] = Query(None, description="Filter by class ID"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query subjects with optional class filter."""
    return await academic_service.list_subjects(db=db, class_id=class_id)


@router.patch("/subjects/{subject_id}", response_model=SubjectResponse, status_code=status.HTTP_200_OK)
async def update_subject(
    subject_id: uuid.UUID,
    req: UpdateSubjectRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update subject name or status."""
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.update_subject(
        db=db,
        subject_id=subject_id,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_200_OK)
async def delete_subject(
    subject_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Deactivate subject."""
    request_id = getattr(request.state, "request_id", None)
    success = await academic_service.delete_subject(
        db=db,
        subject_id=subject_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": success, "message": "Subject deactivated"}
