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
from src.models.system import InstituteSettings
from src.models.user import Teacher
from src.schemas.teacher_attendance import (
    BiometricEventWebhookPayload,
    IngestBiometricEventsResponse,
    TeacherAttendanceDaySummary,
    TeacherAttendanceOverallSummary,
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


biometric_service = BiometricService()
