from fastapi import Depends
from src.core.dependencies import get_current_user
from src.core.exceptions import ForbiddenError
from src.models.user import User, UserRole, Student, Teacher


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Enforces that the authenticated user possesses the ADMIN role."""
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Administrator access required")
    return current_user


def require_teacher(current_user: User = Depends(get_current_user)) -> User:
    """Enforces that the authenticated user possesses the TEACHER role and teacher profile."""
    if current_user.role != UserRole.TEACHER:
        raise ForbiddenError("Teacher access required")
    if not current_user.teacher:
        raise ForbiddenError("Teacher profile record not found")
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Enforces that the authenticated user possesses the STUDENT role and student profile."""
    if current_user.role != UserRole.STUDENT:
        raise ForbiddenError("Student access required")
    if not current_user.student:
        raise ForbiddenError("Student profile record not found")
    return current_user
