import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin
from src.database import get_db
from src.models.user import User
from src.schemas.academic import (
    CreateClassRequest,
    ClassResponse,
    CreateBatchRequest,
    BatchResponse,
    CreateSubjectRequest,
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
    request_id = getattr(request.state, "request_id", None)
    return await academic_service.create_class(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.get("/classes", response_model=List[ClassResponse], status_code=status.HTTP_200_OK)
async def list_classes(
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await academic_service.list_classes(db=db)


# Batches
@router.post("/batches", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    req: CreateBatchRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
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
    return await academic_service.list_batches(db=db, class_id=class_id)


# Subjects
@router.post("/subjects", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    req: CreateSubjectRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
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
    return await academic_service.list_subjects(db=db, class_id=class_id)
