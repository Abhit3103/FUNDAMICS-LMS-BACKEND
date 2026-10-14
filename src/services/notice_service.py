import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import record_audit_log
from src.core.exceptions import NotFoundError, ValidationError
from src.models.academic import Class, Batch
from src.models.system import Notice
from src.models.user import User, UserRole
from src.schemas.system import NoticeCreateRequest, NoticeUpdateRequest, NoticeResponse


class NoticeService:

    @staticmethod
    async def create_notice(
        db: AsyncSession,
        req: NoticeCreateRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> NoticeResponse:
        if req.class_id:
            class_obj = await db.get(Class, req.class_id)
            if not class_obj:
                raise NotFoundError("Referenced class does not exist")

        if req.batch_id:
            batch_obj = await db.get(Batch, req.batch_id)
            if not batch_obj:
                raise NotFoundError("Referenced batch does not exist")
            if req.class_id and batch_obj.class_id != req.class_id:
                raise ValidationError("Batch does not belong to the selected class")

        now = datetime.now(timezone.utc)
        notice = Notice(
            title=req.title.strip(),
            content=req.content.strip(),
            target_audience=req.target_audience.strip().upper(),
            class_id=req.class_id,
            batch_id=req.batch_id,
            priority=req.priority.strip().upper(),
            attachment_file_id=req.attachment_file_id,
            is_active=True,
            published_at=now,
            expires_at=req.expires_at,
            created_by=actor_id,
        )
        db.add(notice)
        await db.flush()

        await record_audit_log(
            db=db,
            action="NOTICE_CREATED",
            resource_type="notice",
            resource_id=str(notice.id),
            actor_id=actor_id,
            after_json={"title": notice.title, "target_audience": notice.target_audience},
            request_id=request_id,
        )
        await db.commit()
        await db.refresh(notice)

        return NoticeResponse.model_validate(notice)

    @staticmethod
    async def list_admin_notices(
        db: AsyncSession,
        target_audience: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[NoticeResponse]:
        query = select(Notice).order_by(Notice.published_at.desc()).limit(limit).offset(offset)
        if target_audience:
            query = query.where(Notice.target_audience == target_audience.strip().upper())
        if is_active is not None:
            query = query.where(Notice.is_active == is_active)

        res = await db.execute(query)
        notices = res.scalars().all()
        return [NoticeResponse.model_validate(n) for n in notices]

    @staticmethod
    async def get_notice(
        db: AsyncSession,
        notice_id: uuid.UUID,
    ) -> NoticeResponse:
        notice = await db.get(Notice, notice_id)
        if not notice:
            raise NotFoundError("Notice not found")
        return NoticeResponse.model_validate(notice)

    @staticmethod
    async def update_notice(
        db: AsyncSession,
        notice_id: uuid.UUID,
        req: NoticeUpdateRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> NoticeResponse:
        notice = await db.get(Notice, notice_id)
        if not notice:
            raise NotFoundError("Notice not found")

        updated = {}
        if req.title is not None and req.title.strip():
            notice.title = req.title.strip()
            updated["title"] = notice.title
        if req.content is not None and req.content.strip():
            notice.content = req.content.strip()
            updated["content"] = notice.content
        if req.target_audience is not None:
            notice.target_audience = req.target_audience.strip().upper()
            updated["target_audience"] = notice.target_audience
        if req.class_id is not None:
            notice.class_id = req.class_id
            updated["class_id"] = str(req.class_id)
        if req.batch_id is not None:
            notice.batch_id = req.batch_id
            updated["batch_id"] = str(req.batch_id)
        if req.priority is not None:
            notice.priority = req.priority.strip().upper()
            updated["priority"] = notice.priority
        if req.attachment_file_id is not None:
            notice.attachment_file_id = req.attachment_file_id
            updated["attachment_file_id"] = str(req.attachment_file_id)
        if req.is_active is not None:
            notice.is_active = req.is_active
            updated["is_active"] = notice.is_active
        if req.expires_at is not None:
            notice.expires_at = req.expires_at
            updated["expires_at"] = str(req.expires_at)

        await record_audit_log(
            db=db,
            action="NOTICE_UPDATED",
            resource_type="notice",
            resource_id=str(notice.id),
            actor_id=actor_id,
            after_json=updated,
            request_id=request_id,
        )
        await db.commit()
        await db.refresh(notice)
        return NoticeResponse.model_validate(notice)

    @staticmethod
    async def delete_notice(
        db: AsyncSession,
        notice_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> bool:
        notice = await db.get(Notice, notice_id)
        if not notice:
            raise NotFoundError("Notice not found")

        notice.is_active = False
        await record_audit_log(
            db=db,
            action="NOTICE_DEACTIVATED",
            resource_type="notice",
            resource_id=str(notice.id),
            actor_id=actor_id,
            request_id=request_id,
        )
        await db.commit()
        return True

    @staticmethod
    async def list_active_notices_for_user(
        db: AsyncSession,
        user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> List[NoticeResponse]:
        now = datetime.now(timezone.utc)
        conditions = [
            Notice.is_active == True,
            Notice.published_at <= now,
            or_(Notice.expires_at.is_(None), Notice.expires_at > now),
        ]

        if user.role == UserRole.STUDENT:
            student = user.student
            audience_filter = Notice.target_audience.in_(["ALL", "STUDENTS"])
            if student:
                class_filter = or_(Notice.class_id.is_(None), Notice.class_id == student.class_id)
                batch_filter = or_(Notice.batch_id.is_(None), Notice.batch_id == student.batch_id)
                conditions.append(and_(audience_filter, class_filter, batch_filter))
            else:
                conditions.append(audience_filter)
        elif user.role == UserRole.TEACHER:
            conditions.append(Notice.target_audience.in_(["ALL", "TEACHERS"]))

        query = select(Notice).where(and_(*conditions)).order_by(Notice.published_at.desc()).limit(limit).offset(offset)
        res = await db.execute(query)
        notices = res.scalars().all()
        return [NoticeResponse.model_validate(n) for n in notices]


notice_service = NoticeService()
