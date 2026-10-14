import uuid
from datetime import datetime, date, timezone
from typing import List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import record_audit_log
from src.core.exceptions import NotFoundError, UnauthorizedError
from src.models.teacher_attendance import (
    BiometricDevice,
    BiometricEvent,
    TeacherAttendance,
    BiometricEventType,
    TeacherAttendanceStatus,
)
from sqlalchemy.orm import selectinload
from src.models.system import InstituteSettings
from src.models.user import Teacher
from src.schemas.teacher_attendance import (
    BiometricEventWebhookPayload,
    IngestBiometricEventsResponse,
    TeacherAttendanceDaySummary,
    TeacherAttendanceOverallSummary,
    TeacherAttendanceRecordResponse,
    TeacherAttendanceReportResponse,
)


class BiometricService:

    @staticmethod
    async def ingest_device_events(
        db: AsyncSession,
        device_secret: str,
        events: List[BiometricEventWebhookPayload],
        request_id: Optional[str] = None,
    ) -> IngestBiometricEventsResponse:
        # Check active device matching secret
        stmt = select(BiometricDevice).where(
            BiometricDevice.secret_reference == device_secret,
            BiometricDevice.status == "ACTIVE",
        )
        res = await db.execute(stmt)
        device = res.scalar_one_or_none()
        if not device:
            raise UnauthorizedError("Invalid device credentials or device inactive")

        device.last_seen_at = datetime.now(timezone.utc)

        # Cache active teachers by employee identifier
        t_stmt = select(Teacher).where(Teacher.status == "ACTIVE")
        t_res = await db.execute(t_stmt)
        teacher_map = {t.biometric_employee_id: t for t in t_res.scalars().all() if t.biometric_employee_id}

        processed = 0
        duplicates_skipped = 0
        unmapped = 0
        now = datetime.now(timezone.utc)

        for ev in events:
            # Check for duplicate event
            dup_stmt = select(BiometricEvent.id).where(
                BiometricEvent.device_id == device.id,
                BiometricEvent.external_event_id == ev.external_event_id,
            )
            dup_res = await db.execute(dup_stmt)
            if dup_res.scalar_one_or_none():
                duplicates_skipped += 1
                continue

            matched_teacher = teacher_map.get(ev.employee_identifier)
            if not matched_teacher:
                unmapped += 1

            new_ev = BiometricEvent(
                device_id=device.id,
                external_event_id=ev.external_event_id,
                employee_identifier=ev.employee_identifier,
                teacher_id=matched_teacher.id if matched_teacher else None,
                event_type=ev.event_type,
                event_at_utc=ev.event_at_utc,
                received_at=now,
            )
            db.add(new_ev)
            processed += 1

        await record_audit_log(
            db=db,
            action="BIOMETRIC_EVENTS_INGESTED",
            resource_type="biometric_events",
            resource_id=str(device.id),
            after_json={"processed": processed, "duplicates": duplicates_skipped, "unmapped": unmapped},
            request_id=request_id,
        )

        await db.commit()

        return IngestBiometricEventsResponse(
            processed=processed,
            duplicates_skipped=duplicates_skipped,
            unmapped_employees=unmapped,
            message=f"Ingested {processed} biometric events ({duplicates_skipped} duplicates skipped)",
        )

    @staticmethod
    async def calculate_teacher_daily(
        db: AsyncSession,
        teacher_id: uuid.UUID,
        target_date: date,
    ) -> TeacherAttendanceDaySummary:
        # Load institute required service hours
        set_res = await db.execute(select(InstituteSettings))
        settings_obj = set_res.scalar_one_or_none()
        req_hours = settings_obj.attendance_required_hours if settings_obj else 8
        required_mins = req_hours * 60

        # Query events for teacher on date
        stmt = (
            select(BiometricEvent)
            .where(
                BiometricEvent.teacher_id == teacher_id,
                func.date(BiometricEvent.event_at_utc) == target_date,
            )
            .order_by(BiometricEvent.event_at_utc.asc())
        )
        res = await db.execute(stmt)
        events = res.scalars().all()

        if not events:
            # Absent record
            attendance = TeacherAttendance(
                teacher_id=teacher_id,
                date=target_date,
                served_minutes=0,
                required_minutes=required_mins,
                status=TeacherAttendanceStatus.ABSENT,
            )
            db.add(attendance)
            await db.commit()
            return TeacherAttendanceDaySummary.model_validate(attendance)

        # In & Out calculation
        in_events = [e for e in events if e.event_type == BiometricEventType.IN]
        out_events = [e for e in events if e.event_type == BiometricEventType.OUT]

        check_in = in_events[0].event_at_utc if in_events else events[0].event_at_utc
        check_out = out_events[-1].event_at_utc if out_events else None

        served_minutes = 0
        if check_in and check_out:
            delta = check_out - check_in
            served_minutes = max(0, int(delta.total_seconds() // 60))

        if not check_out:
            status = TeacherAttendanceStatus.INCOMPLETE
        elif served_minutes >= required_mins:
            status = TeacherAttendanceStatus.PRESENT
        elif served_minutes >= required_mins // 2:
            status = TeacherAttendanceStatus.HALF_DAY
        else:
            status = TeacherAttendanceStatus.REVIEW_REQUIRED

        attendance = TeacherAttendance(
            teacher_id=teacher_id,
            date=target_date,
            check_in_at=check_in,
            check_out_at=check_out,
            served_minutes=served_minutes,
            required_minutes=required_mins,
            status=status,
        )
        db.add(attendance)
        await db.commit()

        return TeacherAttendanceDaySummary.model_validate(attendance)

    @staticmethod
    async def get_teacher_summary(
        db: AsyncSession,
        teacher_id: uuid.UUID,
    ) -> TeacherAttendanceOverallSummary:
        teacher = await db.get(Teacher, teacher_id)
        if not teacher:
            raise NotFoundError("Teacher not found")

        stmt = (
            select(
                TeacherAttendance.status,
                func.count(TeacherAttendance.id),
                func.sum(TeacherAttendance.served_minutes),
            )
            .where(TeacherAttendance.teacher_id == teacher_id)
            .group_by(TeacherAttendance.status)
        )
        res = await db.execute(stmt)
        rows = res.all()

        counts = {}
        total_mins = 0
        for status, count, minutes in rows:
            counts[status] = count
            if minutes:
                total_mins += minutes

        present = counts.get(TeacherAttendanceStatus.PRESENT, 0)
        absent = counts.get(TeacherAttendanceStatus.ABSENT, 0)
        half_day = counts.get(TeacherAttendanceStatus.HALF_DAY, 0)
        incomplete = counts.get(TeacherAttendanceStatus.INCOMPLETE, 0)
        total_days = sum(counts.values())

        return TeacherAttendanceOverallSummary(
            teacher_id=teacher.id,
            teacher_code=teacher.teacher_code,
            total_days=total_days,
            present_days=present,
            absent_days=absent,
            half_days=half_day,
            incomplete_days=incomplete,
            total_served_hours=round(total_mins / 60.0, 2),
        )

    @staticmethod
    async def list_teacher_attendance(
        db: AsyncSession,
        teacher_id: Optional[uuid.UUID] = None,
        target_date: Optional[date] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[TeacherAttendanceStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TeacherAttendanceRecordResponse]:
        query = (
            select(TeacherAttendance)
            .options(
                selectinload(TeacherAttendance.teacher).selectinload(Teacher.user)
            )
            .order_by(TeacherAttendance.date.desc())
            .limit(limit)
            .offset(offset)
        )
        if teacher_id:
            query = query.where(TeacherAttendance.teacher_id == teacher_id)
        if target_date:
            query = query.where(TeacherAttendance.date == target_date)
        if start_date:
            query = query.where(TeacherAttendance.date >= start_date)
        if end_date:
            query = query.where(TeacherAttendance.date <= end_date)
        if status:
            query = query.where(TeacherAttendance.status == status)

        res = await db.execute(query)
        records = res.scalars().all()

        return [
            TeacherAttendanceRecordResponse(
                id=r.id,
                teacher_id=r.teacher_id,
                teacher_name=r.teacher.user.name if r.teacher and r.teacher.user else None,
                teacher_code=r.teacher.teacher_code if r.teacher else None,
                date=r.date,
                check_in_at=r.check_in_at,
                check_out_at=r.check_out_at,
                served_minutes=r.served_minutes,
                required_minutes=r.required_minutes,
                status=r.status,
            )
            for r in records
        ]

    @staticmethod
    async def get_teacher_attendance_report(
        db: AsyncSession,
        start_date: date,
        end_date: date,
    ) -> TeacherAttendanceReportResponse:
        # Aggregated stats across date range
        stmt = (
            select(
                TeacherAttendance.status,
                func.count(TeacherAttendance.id),
                func.sum(TeacherAttendance.served_minutes),
            )
            .where(
                TeacherAttendance.date >= start_date,
                TeacherAttendance.date <= end_date,
            )
            .group_by(TeacherAttendance.status)
        )
        res = await db.execute(stmt)
        rows = res.all()

        counts = {}
        total_mins = 0
        for st, cnt, mins in rows:
            counts[st] = cnt
            if mins:
                total_mins += mins

        present = counts.get(TeacherAttendanceStatus.PRESENT, 0)
        absent = counts.get(TeacherAttendanceStatus.ABSENT, 0)
        half_day = counts.get(TeacherAttendanceStatus.HALF_DAY, 0)
        incomplete = counts.get(TeacherAttendanceStatus.INCOMPLETE, 0)
        total_records = sum(counts.values())

        # Individual teacher summaries within this date range
        t_stmt = select(Teacher).options(selectinload(Teacher.user)).order_by(Teacher.teacher_code.asc())
        teachers_res = await db.execute(t_stmt)
        all_teachers = teachers_res.scalars().all()

        teacher_summaries = []
        for t in all_teachers:
            ind_stmt = (
                select(
                    TeacherAttendance.status,
                    func.count(TeacherAttendance.id),
                    func.sum(TeacherAttendance.served_minutes),
                )
                .where(
                    TeacherAttendance.teacher_id == t.id,
                    TeacherAttendance.date >= start_date,
                    TeacherAttendance.date <= end_date,
                )
                .group_by(TeacherAttendance.status)
            )
            ind_rows = (await db.execute(ind_stmt)).all()
            ind_counts = {}
            ind_mins = 0
            for s, c, m in ind_rows:
                ind_counts[s] = c
                if m:
                    ind_mins += m

            teacher_summaries.append(
                TeacherAttendanceOverallSummary(
                    teacher_id=t.id,
                    teacher_code=t.teacher_code,
                    total_days=sum(ind_counts.values()),
                    present_days=ind_counts.get(TeacherAttendanceStatus.PRESENT, 0),
                    absent_days=ind_counts.get(TeacherAttendanceStatus.ABSENT, 0),
                    half_days=ind_counts.get(TeacherAttendanceStatus.HALF_DAY, 0),
                    incomplete_days=ind_counts.get(TeacherAttendanceStatus.INCOMPLETE, 0),
                    total_served_hours=round(ind_mins / 60.0, 2),
                )
            )

        return TeacherAttendanceReportResponse(
            start_date=start_date,
            end_date=end_date,
            total_records=total_records,
            present_count=present,
            absent_count=absent,
            half_day_count=half_day,
            incomplete_count=incomplete,
            total_hours_served=round(total_mins / 60.0, 2),
            teacher_summaries=teacher_summaries,
        )

    @staticmethod
    async def get_teacher_own_records(
        db: AsyncSession,
        teacher_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TeacherAttendanceRecordResponse]:
        query = (
            select(TeacherAttendance)
            .options(selectinload(TeacherAttendance.teacher).selectinload(Teacher.user))
            .where(TeacherAttendance.teacher_id == teacher_id)
            .order_by(TeacherAttendance.date.desc())
            .limit(limit)
            .offset(offset)
        )
        if start_date:
            query = query.where(TeacherAttendance.date >= start_date)
        if end_date:
            query = query.where(TeacherAttendance.date <= end_date)

        res = await db.execute(query)
        records = res.scalars().all()

        return [
            TeacherAttendanceRecordResponse(
                id=r.id,
                teacher_id=r.teacher_id,
                teacher_name=r.teacher.user.name if r.teacher and r.teacher.user else None,
                teacher_code=r.teacher.teacher_code if r.teacher else None,
                date=r.date,
                check_in_at=r.check_in_at,
                check_out_at=r.check_out_at,
                served_minutes=r.served_minutes,
                required_minutes=r.required_minutes,
                status=r.status,
            )
            for r in records
        ]


biometric_service = BiometricService()
