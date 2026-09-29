import io
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.audit import record_audit_log
from src.core.exceptions import ValidationError, NotFoundError, ConflictError
from src.models.academic import Class, Batch
from src.models.student_attendance import StudentAttendance, AttendanceImport, AttendanceStatus, ImportStatus
from src.models.user import Student
from src.schemas.student_attendance import (
    AttendanceImportPreviewResponse,
    AttendanceImportPreviewRow,
    ConfirmAttendanceImportResponse,
    StudentAttendanceSummary,
)


class StudentAttendanceService:

    @staticmethod
    async def get_student_summary(
        db: AsyncSession,
        student_id: uuid.UUID,
    ) -> StudentAttendanceSummary:
        student = await db.get(Student, student_id)
        if not student:
            raise NotFoundError("Student not found")

        # Aggregate counts
        stmt = (
            select(
                StudentAttendance.status,
                func.count(StudentAttendance.id),
            )
            .where(StudentAttendance.student_id == student_id)
            .group_by(StudentAttendance.status)
        )
        result = await db.execute(stmt)
        status_counts = dict(result.all())

        present = status_counts.get(AttendanceStatus.PRESENT, 0)
        absent = status_counts.get(AttendanceStatus.ABSENT, 0)
        late = status_counts.get(AttendanceStatus.LATE, 0)
        excused = status_counts.get(AttendanceStatus.EXCUSED, 0)

        total_days = present + absent + late + excused
        pct = round((present + late) / total_days * 100, 2) if total_days > 0 else 0.0

        return StudentAttendanceSummary(
            student_id=student.id,
            student_code=student.student_code,
            total_working_days=total_days,
            present_days=present,
            absent_days=absent,
            late_days=late,
            excused_days=excused,
            attendance_percentage=pct,
        )

    @staticmethod
    async def parse_and_validate_records(
        db: AsyncSession,
        class_id: uuid.UUID,
        batch_id: uuid.UUID,
        attendance_date: date,
        records: List[Dict[str, Any]],
        uploaded_by: uuid.UUID,
        filename: str,
        request_id: Optional[str] = None,
    ) -> AttendanceImportPreviewResponse:
        # Verify class & batch
        batch = await db.get(Batch, batch_id)
        if not batch or batch.class_id != class_id:
            raise ValidationError("Batch does not belong to the selected class")

        # Fetch enrolled students
        stmt = (
            select(Student)
            .options(selectinload(Student.user))
            .where(Student.class_id == class_id, Student.batch_id == batch_id, Student.status == "ACTIVE")
        )
        res = await db.execute(stmt)
        active_students = {s.student_code: s for s in res.scalars().all()}

        # Check existing attendance for this batch/date
        existing_stmt = (
            select(StudentAttendance.student_id)
            .where(
                StudentAttendance.class_id == class_id,
                StudentAttendance.batch_id == batch_id,
                StudentAttendance.date == attendance_date,
            )
        )
        existing_res = await db.execute(existing_stmt)
        existing_student_ids = set(existing_res.scalars().all())

        preview_rows: List[AttendanceImportPreviewRow] = []
        valid_count = 0
        error_count = 0
        seen_codes = set()

        for idx, item in enumerate(records, start=1):
            code = str(item.get("student_code", "")).strip()
            raw_status = str(item.get("status", "")).strip().upper()

            student = active_students.get(code)
            is_valid = True
            error_msg = None

            if not code:
                is_valid = False
                error_msg = "Student code is missing"
            elif code in seen_codes:
                is_valid = False
                error_msg = "Duplicate student code in submission"
            elif not student:
                is_valid = False
                error_msg = f"Student code '{code}' not enrolled in this class/batch"
            elif student.id in existing_student_ids:
                is_valid = False
                error_msg = f"Attendance already recorded for this student on {attendance_date}"
            elif raw_status not in AttendanceStatus.__members__:
                is_valid = False
                error_msg = f"Invalid status '{raw_status}'. Allowed: {', '.join(AttendanceStatus.__members__.keys())}"

            seen_codes.add(code)
            if is_valid:
                valid_count += 1
            else:
                error_count += 1

            status_val = AttendanceStatus[raw_status] if raw_status in AttendanceStatus.__members__ else AttendanceStatus.ABSENT

            preview_rows.append(
                AttendanceImportPreviewRow(
                    row_number=idx,
                    student_code=code,
                    student_name=student.user.name if student else None,
                    status=status_val,
                    is_valid=is_valid,
                    error_message=error_msg,
                )
            )

        # Stage import record
        import_record = AttendanceImport(
            uploaded_by=uploaded_by,
            class_id=class_id,
            batch_id=batch_id,
            from_date=attendance_date,
            to_date=attendance_date,
            filename=filename,
            status=ImportStatus.VALIDATED if error_count == 0 else ImportStatus.FAILED,
            total_rows=len(records),
            valid_rows=valid_count,
            error_rows=error_count,
        )
        db.add(import_record)
        await db.commit()

        return AttendanceImportPreviewResponse(
            import_id=import_record.id,
            filename=filename,
            class_id=class_id,
            batch_id=batch_id,
            attendance_date=attendance_date,
            total_rows=len(records),
            valid_rows=valid_count,
            error_rows=error_count,
            preview_data=preview_rows,
        )

    @staticmethod
    async def commit_import(
        db: AsyncSession,
        import_id: uuid.UUID,
        validated_rows: List[Dict[str, Any]],
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> ConfirmAttendanceImportResponse:
        import_record = await db.get(AttendanceImport, import_id)
        if not import_record:
            raise NotFoundError("Import session not found")

        if import_record.status == ImportStatus.COMPLETED:
            raise ConflictError("Import session already completed")

        # Atomic commit
        attendance_entries: List[StudentAttendance] = []
        for r in validated_rows:
            student_stmt = select(Student).where(Student.student_code == r["student_code"])
            s_res = await db.execute(student_stmt)
            student = s_res.scalar_one_or_none()
            if not student:
                continue

            entry = StudentAttendance(
                student_id=student.id,
                class_id=import_record.class_id,
                batch_id=import_record.batch_id,
                date=import_record.from_date,
                status=AttendanceStatus(r["status"]),
                remarks=r.get("remarks"),
                source="EXCEL_IMPORT",
                import_id=import_record.id,
            )
            attendance_entries.append(entry)

        db.add_all(attendance_entries)
        import_record.status = ImportStatus.COMPLETED
        import_record.completed_at = datetime.now(timezone.utc)

        await record_audit_log(
            db=db,
            action="ATTENDANCE_IMPORTED",
            resource_type="attendance_import",
            resource_id=str(import_record.id),
            actor_id=actor_id,
            after_json={"records_count": len(attendance_entries), "date": str(import_record.from_date)},
            request_id=request_id,
        )

        await db.commit()

        return ConfirmAttendanceImportResponse(
            import_id=import_record.id,
            status=ImportStatus.COMPLETED,
            committed_rows=len(attendance_entries),
            message=f"Successfully committed {len(attendance_entries)} student attendance records",
        )


student_attendance_service = StudentAttendanceService()
