import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.dependencies import get_current_user
from src.core.permissions import require_admin
from src.database import get_db
from src.models.user import User
from src.schemas.system import (
    NoticeCreateRequest,
    NoticeUpdateRequest,
    NoticeResponse,
)
from src.services.notice_service import notice_service

admin_notices_router = APIRouter(prefix="/admin", tags=["Admin — Notices & Announcements"])
user_notices_router = APIRouter(tags=["Notices & Announcements"])


# Admin Notice Management Endpoints
@admin_notices_router.post("/notices", response_model=NoticeResponse, status_code=status.HTTP_201_CREATED)
async def create_notice(
    req: NoticeCreateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create and publish a new institute notice or announcement."""
    request_id = getattr(request.state, "request_id", None)
    return await notice_service.create_notice(
        db=db,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_notices_router.get("/notices", response_model=List[NoticeResponse], status_code=status.HTTP_200_OK)
async def list_admin_notices(
    target_audience: Optional[str] = Query(None, description="Filter by audience (ALL, STUDENTS, TEACHERS)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query institute notices registry with filters."""
    return await notice_service.list_admin_notices(
        db=db,
        target_audience=target_audience,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@admin_notices_router.get("/notices/{notice_id}", response_model=NoticeResponse, status_code=status.HTTP_200_OK)
async def get_admin_notice(
    notice_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query notice details."""
    return await notice_service.get_notice(db=db, notice_id=notice_id)


@admin_notices_router.patch("/notices/{notice_id}", response_model=NoticeResponse, status_code=status.HTTP_200_OK)
async def update_notice(
    notice_id: uuid.UUID,
    req: NoticeUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update existing notice attributes, audience, or active flag."""
    request_id = getattr(request.state, "request_id", None)
    return await notice_service.update_notice(
        db=db,
        notice_id=notice_id,
        req=req,
        actor_id=current_admin.id,
        request_id=request_id,
    )


@admin_notices_router.delete("/notices/{notice_id}", status_code=status.HTTP_200_OK)
async def delete_notice(
    notice_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Deactivate / soft-delete notice."""
    request_id = getattr(request.state, "request_id", None)
    success = await notice_service.delete_notice(
        db=db,
        notice_id=notice_id,
        actor_id=current_admin.id,
        request_id=request_id,
    )
    return {"success": success, "message": "Notice deactivated successfully"}


# Authenticated User (Student & Teacher) Notices Feed
@user_notices_router.get("/notices", response_model=List[NoticeResponse], status_code=status.HTTP_200_OK)
async def list_my_notices(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authenticated user: Query active notices and announcements targeted to current user's role and class."""
    return await notice_service.list_active_notices_for_user(
        db=db,
        user=current_user,
        limit=limit,
        offset=offset,
    )
