import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin
from src.database import get_db
from src.models.user import User
from src.schemas.user import (
    CreateStudentRequest,
    UpdateStudentRequest,
    StudentResponse,
    CreateTeacherRequest,
    UpdateTeacherRequest,
    TeacherResponse,
    PendingRegistrationResponse,
    ApproveRegistrationRequest,
    RejectRegistrationRequest,
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


@router.get("/students/{student_id}", response_model=StudentResponse, status_code=status.HTTP_200_OK)
async def get_student(
    student_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query single student record."""
    return await user_service.get_student(db=db, student_id=student_id)


@router.patch("/students/{student_id}", response_model=StudentResponse, status_code=status.HTTP_200_OK)
async def update_student(
    student_id: uuid.UUID,
    req: UpdateStudentRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update student profile attributes, class/batch assignment, or status."""
    request_id = getattr(request.state, "request_id", None)
    return await user_service.update_student(
        db=db,
        student_id=student_id,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.delete("/students/{student_id}", status_code=status.HTTP_200_OK)
async def delete_student(
    student_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Deactivate student record."""
    request_id = getattr(request.state, "request_id", None)
    success = await user_service.delete_student(
        db=db,
        student_id=student_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": success, "message": "Student record deactivated"}


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


@router.get("/teachers/{teacher_id}", response_model=TeacherResponse, status_code=status.HTTP_200_OK)
async def get_teacher(
    teacher_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query single teacher record."""
    return await user_service.get_teacher(db=db, teacher_id=teacher_id)


@router.patch("/teachers/{teacher_id}", response_model=TeacherResponse, status_code=status.HTTP_200_OK)
async def update_teacher(
    teacher_id: uuid.UUID,
    req: UpdateTeacherRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update teacher details, biometric mapping, or status."""
    request_id = getattr(request.state, "request_id", None)
    return await user_service.update_teacher(
        db=db,
        teacher_id=teacher_id,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@router.delete("/teachers/{teacher_id}", status_code=status.HTTP_200_OK)
async def delete_teacher(
    teacher_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Deactivate teacher record."""
    request_id = getattr(request.state, "request_id", None)
    success = await user_service.delete_teacher(
        db=db,
        teacher_id=teacher_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": success, "message": "Teacher record deactivated"}


# Registration Approval & Workflow
@router.get("/users/pending-registrations", response_model=List[PendingRegistrationResponse], status_code=status.HTTP_200_OK)
async def list_pending_registrations(
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query student registrations awaiting approval."""
    return await user_service.list_pending_registrations(db=db, limit=limit, offset=offset)


@router.post("/users/{user_id}/approve", response_model=StudentResponse, status_code=status.HTTP_200_OK)
async def approve_registration(
    user_id: uuid.UUID,
    req: ApproveRegistrationRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Approve pending student registration, activate account, and notify student."""
    request_id = getattr(request.state, "request_id", None)
    return await user_service.approve_registration(
        db=db,
        user_id=user_id,
        actor_id=current_admin.id,
        remarks=req.remarks,
        request_id=request_id,
    )


@router.post("/users/{user_id}/reject", status_code=status.HTTP_200_OK)
async def reject_registration(
    user_id: uuid.UUID,
    req: RejectRegistrationRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Reject pending student registration with reason and notify applicant."""
    request_id = getattr(request.state, "request_id", None)
    success = await user_service.reject_registration(
        db=db,
        user_id=user_id,
        actor_id=current_admin.id,
        reason=req.reason,
        request_id=request_id,
    )
    return {"success": success, "message": "Registration rejected"}
