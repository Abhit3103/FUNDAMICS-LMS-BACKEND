import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin
from src.database import get_db
from src.models.user import User
from src.schemas.user import (
    CreateStudentRequest,
    StudentResponse,
    CreateTeacherRequest,
    TeacherResponse,
)
from src.services.user_service import user_service

router = APIRouter(prefix="/admin", tags=["Admin — Users Management"])


# Students Management
@router.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(
    req: CreateStudentRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create a student, user account, and initial enrollment in one atomic transaction."""
    request_id = getattr(request.state, "request_id", None)
    return await user_service.create_student(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.get("/students", response_model=List[StudentResponse], status_code=status.HTTP_200_OK)
async def list_students(
    class_id: Optional[uuid.UUID] = Query(None, description="Filter by class ID"),
    batch_id: Optional[uuid.UUID] = Query(None, description="Filter by batch ID"),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query list of enrolled students with class & batch details."""
    return await user_service.list_students(
        db=db,
        class_id=class_id,
        batch_id=batch_id,
        limit=limit,
        offset=offset,
    )


# Teachers Management
@router.post("/teachers", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    req: CreateTeacherRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Register a teacher profile and linked user account."""
    request_id = getattr(request.state, "request_id", None)
    return await user_service.create_teacher(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.get("/teachers", response_model=List[TeacherResponse], status_code=status.HTTP_200_OK)
async def list_teachers(
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query registered teachers roster."""
    return await user_service.list_teachers(
        db=db,
        limit=limit,
        offset=offset,
    )
