# Import all models here so Alembic and SQLAlchemy registry can resolve all relationships and table metadata
from src.models.base import TimeStampedUUIDModel, Base
from src.models.user import User, Student, Teacher, UserRole, UserStatus
from src.models.academic import Class, Batch, Subject, Enrollment
from src.models.student_attendance import StudentAttendance, AttendanceImport, AttendanceStatus, ImportStatus
from src.models.teacher_attendance import BiometricDevice, BiometricEvent, TeacherAttendance, BiometricEventType, TeacherAttendanceStatus
from src.models.exam_result import Exam, Result
from src.models.note_file import FileRecord, Note
from src.models.system import AcademicCalendarEvent, NotificationRecord, AuditLog, InstituteSettings, CalendarEventType
from src.models.auth_session import AuthSession, VerificationToken, PasswordResetToken

__all__ = [
    "Base",
    "TimeStampedUUIDModel",
    "User",
    "Student",
    "Teacher",
    "UserRole",
    "UserStatus",
    "Class",
    "Batch",
    "Subject",
    "Enrollment",
    "StudentAttendance",
    "AttendanceImport",
    "AttendanceStatus",
    "ImportStatus",
    "BiometricDevice",
    "BiometricEvent",
    "TeacherAttendance",
    "BiometricEventType",
    "TeacherAttendanceStatus",
    "Exam",
    "Result",
    "FileRecord",
    "Note",
    "AcademicCalendarEvent",
    "NotificationRecord",
    "AuditLog",
    "InstituteSettings",
    "CalendarEventType",
    "AuthSession",
    "VerificationToken",
    "PasswordResetToken",
]
