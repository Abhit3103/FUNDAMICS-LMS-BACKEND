import uuid
from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin, require_student
from src.database import get_db
from src.models.user import User
from src.schemas.exam_result import (
    CreateExamRequest,
    ExamResponse,
    BulkEnterMarksRequest,
    PublishExamResultsRequest,
    StudentExamSummaryResponse,
)
from src.services.result_service import result_service

admin_results_router = APIRouter(prefix="/admin", tags=["Admin — Exams & Results"])
student_results_router = APIRouter(prefix="/student", tags=["Student — My Results"])


@admin_results_router.post("/exams", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    req: CreateExamRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create an exam container."""
    request_id = getattr(request.state, "request_id", None)
    return await result_service.create_exam(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_results_router.post("/exams/marks", status_code=status.HTTP_200_OK)
async def record_bulk_marks(
    req: BulkEnterMarksRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Record or update marks for an exam."""
    request_id = getattr(request.state, "request_id", None)
    count = await result_service.record_bulk_marks(
        db=db,
        exam_id=req.exam_id,
        entries=req.marks_entries,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": True, "records_processed": count}


@admin_results_router.post("/exams/publish", status_code=status.HTTP_200_OK)
async def publish_results(
    req: PublishExamResultsRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Publish or unpublish results for an exam."""
    request_id = getattr(request.state, "request_id", None)
    count = await result_service.toggle_publication(
        db=db,
        exam_id=req.exam_id,
        publish=req.publish,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": True, "published": req.publish, "affected_records": count}


@student_results_router.get("/me/results", response_model=List[StudentExamSummaryResponse], status_code=status.HTTP_200_OK)
async def get_my_results(
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Student-only: Query authenticated student's published results."""
    return await result_service.get_student_results(
        db=db,
        student_id=current_user.student.id,
    )
