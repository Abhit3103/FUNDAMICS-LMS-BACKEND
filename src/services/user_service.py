import secrets
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.audit import record_audit_log
from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.security import hash_password
from src.models.academic import Class, Batch, Enrollment
from src.models.user import User, Student, Teacher, UserRole, UserStatus
from src.schemas.user import (
    CreateStudentRequest,
    UpdateStudentRequest,
    StudentResponse,
    CreateTeacherRequest,
    UpdateTeacherRequest,
    TeacherResponse,
)


class UserService:

    @staticmethod
    async def create_student(
        db: AsyncSession,
        req: CreateStudentRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> StudentResponse:
        # Check email uniqueness
        existing_email = await db.execute(select(User).where(User.email == req.email.lower().strip()))
        if existing_email.scalar_one_or_none():
            raise ConflictError("A user with this email address already exists")

        # Check student_code uniqueness
        existing_code = await db.execute(select(Student).where(Student.student_code == req.student_code.strip()))
        if existing_code.scalar_one_or_none():
            raise ConflictError("A student with this code already exists")

        # Verify class and batch
        class_obj = await db.get(Class, req.class_id)
        if not class_obj:
            raise NotFoundError("Assigned class does not exist")

        batch_obj = await db.get(Batch, req.batch_id)
        if not batch_obj or batch_obj.class_id != req.class_id:
            raise ValidationError("Assigned batch does not belong to the selected class")

        # Initial password setup (Admin provided or random temp password)
        initial_password = req.password or secrets.token_urlsafe(12)
        pwd_hash = hash_password(initial_password)

        # Atomic User + Student + Initial Enrollment creation
        new_user = User(
            name=req.name.strip(),
            email=req.email.lower().strip(),
            phone=req.phone.strip() if req.phone else None,
            password_hash=pwd_hash,
            role=UserRole.STUDENT,
            status=UserStatus.ACTIVE if req.password else UserStatus.PENDING_VERIFICATION,
        )
        db.add(new_user)
        await db.flush()

        new_student = Student(
            user_id=new_user.id,
            student_code=req.student_code.strip(),
            class_id=req.class_id,
            batch_id=req.batch_id,
            admission_date=req.admission_date,
            status="ACTIVE",
        )
        db.add(new_student)
        await db.flush()

        new_enrollment = Enrollment(
            student_id=new_student.id,
            class_id=req.class_id,
            batch_id=req.batch_id,
            start_date=req.admission_date,
            status="ACTIVE",
        )
        db.add(new_enrollment)

        await record_audit_log(
            db=db,
            action="STUDENT_CREATED",
            resource_type="student",
            resource_id=str(new_student.id),
            actor_id=actor_id,
            after_json={
                "student_code": new_student.student_code,
                "class_id": str(req.class_id),
                "batch_id": str(req.batch_id),
                "admission_date": str(req.admission_date),
            },
            request_id=request_id,
        )

        await db.commit()

        return StudentResponse(
            id=new_student.id,
            user_id=new_user.id,
            name=new_user.name,
            email=new_user.email,
            phone=new_user.phone,
            student_code=new_student.student_code,
            class_id=new_student.class_id,
            class_name=class_obj.name,
            batch_id=new_student.batch_id,
            batch_name=batch_obj.name,
            admission_date=new_student.admission_date,
            status=new_student.status,
        )

    @staticmethod
    async def list_students(
        db: AsyncSession,
        class_id: Optional[uuid.UUID] = None,
        batch_id: Optional[uuid.UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[StudentResponse]:
        query = (
            select(Student)
            .options(
                selectinload(Student.user),
                selectinload(Student.current_class),
                selectinload(Student.current_batch),
            )
            .order_by(Student.student_code.asc())
            .limit(limit)
            .offset(offset)
        )
        if class_id:
            query = query.where(Student.class_id == class_id)
        if batch_id:
            query = query.where(Student.batch_id == batch_id)

        result = await db.execute(query)
        students = result.scalars().all()

        return [
            StudentResponse(
                id=s.id,
                user_id=s.user.id,
                name=s.user.name,
                email=s.user.email,
                phone=s.user.phone,
                student_code=s.student_code,
                class_id=s.class_id,
                class_name=s.current_class.name if s.current_class else None,
                batch_id=s.batch_id,
                batch_name=s.current_batch.name if s.current_batch else None,
                admission_date=s.admission_date,
                status=s.status,
            )
            for s in students
        ]

    @staticmethod
    async def create_teacher(
        db: AsyncSession,
        req: CreateTeacherRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> TeacherResponse:
        # Check email uniqueness
        existing_email = await db.execute(select(User).where(User.email == req.email.lower().strip()))
        if existing_email.scalar_one_or_none():
            raise ConflictError("A user with this email address already exists")

        # Check teacher_code uniqueness
        existing_code = await db.execute(select(Teacher).where(Teacher.teacher_code == req.teacher_code.strip()))
        if existing_code.scalar_one_or_none():
            raise ConflictError("A teacher with this code already exists")

        # Check biometric_employee_id uniqueness if provided
        if req.biometric_employee_id:
            existing_bio = await db.execute(
                select(Teacher).where(Teacher.biometric_employee_id == req.biometric_employee_id.strip())
            )
            if existing_bio.scalar_one_or_none():
                raise ConflictError("A teacher with this biometric employee ID already exists")

        initial_password = req.password or secrets.token_urlsafe(12)
        pwd_hash = hash_password(initial_password)

        new_user = User(
            name=req.name.strip(),
            email=req.email.lower().strip(),
            phone=req.phone.strip() if req.phone else None,
            password_hash=pwd_hash,
            role=UserRole.TEACHER,
            status=UserStatus.ACTIVE if req.password else UserStatus.PENDING_VERIFICATION,
        )
        db.add(new_user)
        await db.flush()

        new_teacher = Teacher(
            user_id=new_user.id,
            teacher_code=req.teacher_code.strip(),
            biometric_employee_id=req.biometric_employee_id.strip() if req.biometric_employee_id else None,
            status="ACTIVE",
        )
        db.add(new_teacher)

        await record_audit_log(
            db=db,
            action="TEACHER_CREATED",
            resource_type="teacher",
            resource_id=str(new_teacher.id),
            actor_id=actor_id,
            after_json={
                "teacher_code": new_teacher.teacher_code,
                "biometric_employee_id": new_teacher.biometric_employee_id,
            },
            request_id=request_id,
        )

        await db.commit()

        return TeacherResponse(
            id=new_teacher.id,
            user_id=new_user.id,
            name=new_user.name,
            email=new_user.email,
            phone=new_user.phone,
            teacher_code=new_teacher.teacher_code,
            biometric_employee_id=new_teacher.biometric_employee_id,
            status=new_teacher.status,
        )

    @staticmethod
    async def list_teachers(
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TeacherResponse]:
        query = (
            select(Teacher)
            .options(selectinload(Teacher.user))
            .order_by(Teacher.teacher_code.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(query)
        teachers = result.scalars().all()

        return [
            TeacherResponse(
                id=t.id,
                user_id=t.user.id,
                name=t.user.name,
                email=t.user.email,
                phone=t.user.phone,
                teacher_code=t.teacher_code,
                biometric_employee_id=t.biometric_employee_id,
                status=t.status,
            )
            for t in teachers
        ]


user_service = UserService()
