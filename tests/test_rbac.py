import uuid
from datetime import date

import pytest

from src.core.exceptions import ForbiddenError
from src.core.permissions import require_admin, require_teacher, require_student
from src.models.user import User, UserRole, Teacher, Student
def make_user(role: UserRole) -> User:
    user = User(
        role=role,
        name=f"Test {role.value}",
        email=f"{role.value.lower()}-{uuid.uuid4()}@test.local",
        password_hash="test-password-hash",
    )
    if role == UserRole.TEACHER:
        user.teacher = Teacher(
            teacher_code=f"T-{uuid.uuid4().hex[:8]}",
            biometric_employee_id=None,
            status="ACTIVE",
        )

    if role == UserRole.STUDENT:
        user.student = Student(
            student_code=f"S-{uuid.uuid4().hex[:8]}",
            class_id=uuid.uuid4(),
            batch_id=uuid.uuid4(),
            admission_date=date.today(),
            status="ACTIVE",
        )

    return user


def test_admin_allowed():
    user = make_user(UserRole.ADMIN)

    require_admin(user)

    assert True


def test_teacher_allowed():
    user = make_user(UserRole.TEACHER)

    require_teacher(user)

    assert True


def test_student_allowed():
    user = make_user(UserRole.STUDENT)

    require_student(user)

    assert True


def test_teacher_not_allowed_as_admin():
    user = make_user(UserRole.TEACHER)

    with pytest.raises(ForbiddenError):
        require_admin(user)


def test_student_not_allowed_as_admin():
    user = make_user(UserRole.STUDENT)

    with pytest.raises(ForbiddenError):
        require_admin(user)


def test_admin_not_allowed_as_teacher():
    user = make_user(UserRole.ADMIN)

    with pytest.raises(ForbiddenError):
        require_teacher(user)


def test_admin_not_allowed_as_student():
    user = make_user(UserRole.ADMIN)

    with pytest.raises(ForbiddenError):
        require_student(user)


def test_teacher_not_allowed_as_student():
    user = make_user(UserRole.TEACHER)

    with pytest.raises(ForbiddenError):
        require_student(user)


def test_student_not_allowed_as_teacher():
    user = make_user(UserRole.STUDENT)

    with pytest.raises(ForbiddenError):
        require_teacher(user)
