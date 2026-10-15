import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ValidationError
from src.core.permissions import require_admin, require_student
from src.database import get_db
from src.models.user import User
from src.schemas.exam_result import (
    CreateExamRequest,
    ExamResponse,
    ExamDetailResponse,
    BulkEnterMarksRequest,
    PublishExamResultsRequest,
    StudentExamSummaryResponse,
    ResultResponse,
    MapResultDocumentRequest,
    DirectStudentResultDocumentMappingRequest,
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


@admin_results_router.get("/exams", response_model=List[ExamResponse], status_code=status.HTTP_200_OK)
async def list_exams(
    class_id: Optional[uuid.UUID] = Query(None, description="Filter by class ID"),
    batch_id: Optional[uuid.UUID] = Query(None, description="Filter by batch ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (SCHEDULED, COMPLETED, CANCELLED)"),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query list of exams with optional class/batch/status filters."""
    return await result_service.list_exams(
        db=db,
        class_id=class_id,
        batch_id=batch_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@admin_results_router.get("/exams/{exam_id}", response_model=ExamDetailResponse, status_code=status.HTTP_200_OK)
async def get_exam_detail(
    exam_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query detailed exam container and all recorded student marks."""
    return await result_service.get_exam_detail(db=db, exam_id=exam_id)


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


@admin_results_router.post(
    "/results/{result_id}/document",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_result_document(
    result_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Upload scorecard/result document (PDF/Image) for an individual student result."""
    request_id = getattr(request.state, "request_id", None)
    return await result_service.upload_result_document(
        db=db,
        result_id=result_id,
        file=file,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_results_router.get(
    "/results/{result_id}/document",
    status_code=status.HTTP_200_OK,
)
async def download_result_document_admin(
    result_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Download attached student result document."""
    storage_path, filename, mime_type = await result_service.get_authorized_result_document(
        db=db,
        result_id=result_id,
        user=current_admin,
    )
    return FileResponse(path=storage_path, filename=filename, media_type=mime_type)


@admin_results_router.post(
    "/results/{result_id}/document-mapping",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
)
@admin_results_router.post(
    "/results/{result_id}/map-file",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def map_result_document(
    result_id: uuid.UUID,
    req: MapResultDocumentRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Map an already uploaded file (file_id) to a student result by result ID."""
    file_id = req.file_id or req.document_file_id
    if not file_id:
        raise ValidationError("Either file_id or document_file_id must be provided")
    request_id = getattr(request.state, "request_id", None)
    return await result_service.map_result_document(
        db=db,
        result_id=result_id,
        file_id=file_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_results_router.post(
    "/results/document-mapping",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
)
async def direct_map_result_document(
    req: DirectStudentResultDocumentMappingRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Directly map an uploaded document to a student result by exam and student ID."""
    request_id = getattr(request.state, "request_id", None)
    return await result_service.direct_map_student_result_document(
        db=db,
        exam_id=req.exam_id,
        student_id=req.student_id,
        file_id=req.file_id,
        subject_id=req.subject_id,
        remarks=req.remarks,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_results_router.post(
    "/exams/{exam_id}/students/{student_id}/document-mapping",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
)
async def map_student_exam_document(
    exam_id: uuid.UUID,
    student_id: uuid.UUID,
    req: MapResultDocumentRequest,
    request: Request,
    subject_id: Optional[uuid.UUID] = Query(None, description="Optional subject ID"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Map an uploaded document (file_id) to a student's exam result."""
    file_id = req.file_id or req.document_file_id
    if not file_id:
        raise ValidationError("Either file_id or document_file_id must be provided")
    request_id = getattr(request.state, "request_id", None)
    return await result_service.direct_map_student_result_document(
        db=db,
        exam_id=exam_id,
        student_id=student_id,
        file_id=file_id,
        subject_id=subject_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_results_router.post(
    "/exams/{exam_id}/students/{student_id}/document",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_student_exam_document(
    exam_id: uuid.UUID,
    student_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    subject_id: Optional[uuid.UUID] = Query(None, description="Optional subject ID"),
    remarks: Optional[str] = Query(None, description="Optional remarks"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Directly upload and link a scorecard document for a student in an exam."""
    request_id = getattr(request.state, "request_id", None)
    return await result_service.direct_upload_student_result_document(
        db=db,
        exam_id=exam_id,
        student_id=student_id,
        file=file,
        subject_id=subject_id,
        remarks=remarks,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_results_router.delete(
    "/results/{result_id}/document",
    response_model=ResultResponse,
    status_code=status.HTTP_200_OK,
)
async def unlink_result_document(
    result_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Unlink/remove attached document from a student result."""
    request_id = getattr(request.state, "request_id", None)
    return await result_service.unlink_result_document(
        db=db,
        result_id=result_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )


# Student Results Endpoints
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


@student_results_router.get(
    "/me/results/{result_id}/document",
    status_code=status.HTTP_200_OK,
)
async def download_my_result_document(
    result_id: uuid.UUID,
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Student-only: Securely download student's own published scorecard/result document."""
    storage_path, filename, mime_type = await result_service.get_authorized_result_document(
        db=db,
        result_id=result_id,
        user=current_user,
    )
    return FileResponse(path=storage_path, filename=filename, media_type=mime_type)
