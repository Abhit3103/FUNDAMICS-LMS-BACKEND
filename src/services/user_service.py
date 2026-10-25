import secrets
import uuid
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.audit import record_audit_log
from src.core.exceptions import ConflictError, NotFoundError, ValidationError, ServiceUnavailableError
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
    PendingRegistrationResponse,
    ApproveRegistrationRequest,
    RejectRegistrationRequest,
)
from src.services.notification_service import notification_service


class UserService:

    @staticmethod
    async def create_student(
        db: AsyncSession,
        req: CreateStudentRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> StudentResponse:
        clean_email = req.email.lower().strip()
        # Check email uniqueness
        existing_email = await db.execute(select(User).where(func.lower(func.trim(User.email)) == clean_email))
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
            email=clean_email,
            phone=req.phone.strip() if req.phone else None,
            password_hash=pwd_hash,
            role=UserRole.STUDENT,
            status=UserStatus.ACTIVE if req.password else UserStatus.PENDING_VERIFICATION,
        )

        try:
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
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError("A user or student with this email address or code already exists")
        except (SQLAlchemyError, Exception) as exc:
            await db.rollback()
            raise ServiceUnavailableError("Failed to create student. Please try again later.")

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
        clean_email = req.email.lower().strip()
        # Check email uniqueness
        existing_email = await db.execute(select(User).where(func.lower(func.trim(User.email)) == clean_email))
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
            email=clean_email,
            phone=req.phone.strip() if req.phone else None,
            password_hash=pwd_hash,
            role=UserRole.TEACHER,
            status=UserStatus.ACTIVE if req.password else UserStatus.PENDING_VERIFICATION,
        )

        try:
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
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError("A user or teacher with this email address or code already exists")
        except (SQLAlchemyError, Exception) as exc:
            await db.rollback()
            raise ServiceUnavailableError("Failed to create teacher. Please try again later.")

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

    @staticmethod
    async def get_student(
        db: AsyncSession,
        student_id: uuid.UUID,
    ) -> StudentResponse:
        stmt = (
            select(Student)
            .options(
                selectinload(Student.user),
                selectinload(Student.current_class),
                selectinload(Student.current_batch),
            )
            .where(Student.id == student_id)
        )
        res = await db.execute(stmt)
        s = res.scalar_one_or_none()
        if not s:
            raise NotFoundError("Student not found")

        return StudentResponse(
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

    @staticmethod
    async def update_student(
        db: AsyncSession,
        student_id: uuid.UUID,
        req: UpdateStudentRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> StudentResponse:
        stmt = (
            select(Student)
            .options(
                selectinload(Student.user),
                selectinload(Student.current_class),
                selectinload(Student.current_batch),
            )
            .where(Student.id == student_id)
        )
        res = await db.execute(stmt)
        student = res.scalar_one_or_none()
        if not student:
            raise NotFoundError("Student not found")

        updated_fields = {}

        if req.name is not None and req.name.strip():
            student.user.name = req.name.strip()
            updated_fields["name"] = student.user.name

        if req.phone is not None:
            student.user.phone = req.phone.strip() if req.phone.strip() else None
            updated_fields["phone"] = student.user.phone

        if req.class_id is not None:
            class_obj = await db.get(Class, req.class_id)
            if not class_obj:
                raise NotFoundError("Referenced class does not exist")
            student.class_id = req.class_id
            updated_fields["class_id"] = str(req.class_id)

        if req.batch_id is not None:
            batch_obj = await db.get(Batch, req.batch_id)
            if not batch_obj:
                raise NotFoundError("Referenced batch does not exist")
            if batch_obj.class_id != student.class_id:
                raise ValidationError("Batch does not belong to the student's class")
            student.batch_id = req.batch_id
            updated_fields["batch_id"] = str(req.batch_id)

        if req.status is not None:
            student.status = req.status.strip()
            updated_fields["status"] = student.status

        await record_audit_log(
            db=db,
            action="STUDENT_UPDATED",
            resource_type="student",
            resource_id=str(student.id),
            actor_id=actor_id,
            after_json=updated_fields,
            request_id=request_id,
        )
        await db.commit()

        # Reload relationships
        return await UserService.get_student(db, student.id)

    @staticmethod
    async def delete_student(
        db: AsyncSession,
        student_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> bool:
        stmt = select(Student).options(selectinload(Student.user)).where(Student.id == student_id)
        res = await db.execute(stmt)
        student = res.scalar_one_or_none()
        if not student:
            raise NotFoundError("Student not found")

        student.status = "INACTIVE"
        student.user.status = UserStatus.INACTIVE

        await record_audit_log(
            db=db,
            action="STUDENT_DEACTIVATED",
            resource_type="student",
            resource_id=str(student.id),
            actor_id=actor_id,
            request_id=request_id,
        )
        await db.commit()
        return True

    @staticmethod
    async def get_teacher(
        db: AsyncSession,
        teacher_id: uuid.UUID,
    ) -> TeacherResponse:
        stmt = (
            select(Teacher)
            .options(selectinload(Teacher.user))
            .where(Teacher.id == teacher_id)
        )
        res = await db.execute(stmt)
        t = res.scalar_one_or_none()
        if not t:
            raise NotFoundError("Teacher not found")

        return TeacherResponse(
            id=t.id,
            user_id=t.user.id,
            name=t.user.name,
            email=t.user.email,
            phone=t.user.phone,
            teacher_code=t.teacher_code,
            biometric_employee_id=t.biometric_employee_id,
            status=t.status,
        )

    @staticmethod
    async def update_teacher(
        db: AsyncSession,
        teacher_id: uuid.UUID,
        req: UpdateTeacherRequest,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> TeacherResponse:
        stmt = (
            select(Teacher)
            .options(selectinload(Teacher.user))
            .where(Teacher.id == teacher_id)
        )
        res = await db.execute(stmt)
        teacher = res.scalar_one_or_none()
        if not teacher:
            raise NotFoundError("Teacher not found")

        updated_fields = {}

        if req.name is not None and req.name.strip():
            teacher.user.name = req.name.strip()
            updated_fields["name"] = teacher.user.name

        if req.phone is not None:
            teacher.user.phone = req.phone.strip() if req.phone.strip() else None
            updated_fields["phone"] = teacher.user.phone

        if req.biometric_employee_id is not None:
            bio_id = req.biometric_employee_id.strip() if req.biometric_employee_id.strip() else None
            if bio_id and bio_id != teacher.biometric_employee_id:
                # Check uniqueness
                existing_bio = await db.execute(
                    select(Teacher).where(Teacher.biometric_employee_id == bio_id, Teacher.id != teacher.id)
                )
                if existing_bio.scalar_one_or_none():
                    raise ConflictError("A teacher with this biometric ID already exists")
            teacher.biometric_employee_id = bio_id
            updated_fields["biometric_employee_id"] = bio_id

        if req.status is not None:
            teacher.status = req.status.strip()
            updated_fields["status"] = teacher.status

        await record_audit_log(
            db=db,
            action="TEACHER_UPDATED",
            resource_type="teacher",
            resource_id=str(teacher.id),
            actor_id=actor_id,
            after_json=updated_fields,
            request_id=request_id,
        )
        await db.commit()
        return await UserService.get_teacher(db, teacher.id)

    @staticmethod
    async def delete_teacher(
        db: AsyncSession,
        teacher_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: Optional[str] = None,
    ) -> bool:
        stmt = select(Teacher).options(selectinload(Teacher.user)).where(Teacher.id == teacher_id)
        res = await db.execute(stmt)
        teacher = res.scalar_one_or_none()
        if not teacher:
            raise NotFoundError("Teacher not found")

        teacher.status = "INACTIVE"
        teacher.user.status = UserStatus.INACTIVE

        await record_audit_log(
            db=db,
            action="TEACHER_DEACTIVATED",
            resource_type="teacher",
            resource_id=str(teacher.id),
            actor_id=actor_id,
            request_id=request_id,
        )
        await db.commit()
        return True

    @staticmethod
    async def list_pending_registrations(
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PendingRegistrationResponse]:
        stmt = (
            select(User)
            .options(
                selectinload(User.student).selectinload(Student.current_class),
                selectinload(User.student).selectinload(Student.current_batch),
            )
            .where(
                User.role == UserRole.STUDENT,
                User.status.in_([UserStatus.PENDING_APPROVAL, UserStatus.PENDING_VERIFICATION]),
            )
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await db.execute(stmt)
        users = res.scalars().all()

        return [
            PendingRegistrationResponse(
                user_id=u.id,
                student_id=u.student.id if u.student else None,
                name=u.name,
                email=u.email,
                phone=u.phone,
                student_code=u.student.student_code if u.student else None,
                class_id=u.student.class_id if u.student else None,
                class_name=u.student.current_class.name if u.student and u.student.current_class else None,
                batch_id=u.student.batch_id if u.student else None,
                batch_name=u.student.current_batch.name if u.student and u.student.current_batch else None,
                status=u.status,
                email_verified=u.email_verified_at is not None,
                created_at=u.created_at.date(),
            )
            for u in users
        ]

    @staticmethod
    async def approve_registration(
        db: AsyncSession,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        remarks: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> StudentResponse:
        stmt = select(User).options(selectinload(User.student)).where(User.id == user_id)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user or not user.student:
            raise NotFoundError("Student user registration not found")

        already_active = (user.status == UserStatus.ACTIVE and user.student.status == "ACTIVE")
        if already_active:
            logger.info("Student user %s is already ACTIVE. Verifying student records and re-sending notification.", user.id)

        user.status = UserStatus.ACTIVE
        user.student.status = "ACTIVE"

        # Also activate student enrollment
        enr_stmt = select(Enrollment).where(Enrollment.student_id == user.student.id)
        enrollments = (await db.execute(enr_stmt)).scalars().all()
        for enr in enrollments:
            enr.status = "ACTIVE"

        await record_audit_log(
            db=db,
            action="REGISTRATION_APPROVED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor_id,
            after_json={"remarks": remarks, "reapproval": already_active},
            request_id=request_id,
        )

        try:
            await notification_service.send_approval_notification(
                db=db,
                to_email=user.email,
                user_name=user.name,
                approved=True,
                to_phone=user.phone,
            )
        except Exception as exc:
            logger.error(
                "Student user %s was activated, but approval notification dispatch encountered an error: %s",
                user.id,
                exc,
            )

        await db.commit()

        return await UserService.get_student(db, user.student.id)

    @staticmethod
    async def reject_registration(
        db: AsyncSession,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        reason: str,
        request_id: Optional[str] = None,
    ) -> bool:
        stmt = select(User).options(selectinload(User.student)).where(User.id == user_id)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user or not user.student:
            raise NotFoundError("Student user registration not found")

        user.status = UserStatus.REJECTED
        user.student.status = "REJECTED"

        await record_audit_log(
            db=db,
            action="REGISTRATION_REJECTED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor_id,
            after_json={"reason": reason},
            request_id=request_id,
        )

        try:
            await notification_service.send_approval_notification(
                db=db,
                to_email=user.email,
                user_name=user.name,
                approved=False,
                rejection_reason=reason,
                to_phone=user.phone,
            )
        except Exception as exc:
            logger.error(
                "Student user %s was rejected, but rejection notification dispatch encountered an error: %s",
                user.id,
                exc,
            )

        await db.commit()
        return True


user_service = UserService()
