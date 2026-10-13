import asyncio
from datetime import date, time, datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from src.config import settings
from src.core.security import hash_password
from src.models.user import User, Student, Teacher, UserRole, UserStatus
from src.models.academic import Class, Batch, Subject, Enrollment

async def seed():
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        # Check if users already exist
        existing_admin = (await session.execute(select(User).where(User.email == "admin@fundamics.com"))).scalar_one_or_none()
        existing_teacher = (await session.execute(select(User).where(User.email == "teacher@fundamics.com"))).scalar_one_or_none()
        existing_student = (await session.execute(select(User).where(User.email == "student@fundamics.com"))).scalar_one_or_none()

        # 1. Academic Class & Batch (if needed)
        class_stmt = select(Class).where(Class.code == "CLS-10-SCI")
        class_obj = (await session.execute(class_stmt)).scalar_one_or_none()
        if not class_obj:
            class_obj = Class(
                name="Class 10 - Science",
                code="CLS-10-SCI",
                academic_year="2026-2027",
                status="ACTIVE",
            )
            session.add(class_obj)
            await session.flush()
            print(f"Created Class: {class_obj.name} ({class_obj.id})")

        batch_stmt = select(Batch).where(Batch.code == "BAT-10-MORN")
        batch_obj = (await session.execute(batch_stmt)).scalar_one_or_none()
        if not batch_obj:
            batch_obj = Batch(
                class_id=class_obj.id,
                name="Morning Batch A",
                code="BAT-10-MORN",
                start_time=time(9, 0),
                end_time=time(11, 0),
                status="ACTIVE",
            )
            session.add(batch_obj)
            await session.flush()
            print(f"Created Batch: {batch_obj.name} ({batch_obj.id})")

        subject_stmt = select(Subject).where(Subject.code == "SUB-10-PHY")
        subject_obj = (await session.execute(subject_stmt)).scalar_one_or_none()
        if not subject_obj:
            subject_obj = Subject(
                class_id=class_obj.id,
                name="Physics",
                code="SUB-10-PHY",
                status="ACTIVE",
            )
            session.add(subject_obj)
            await session.flush()
            print(f"Created Subject: {subject_obj.name} ({subject_obj.id})")

        # 2. Admin User
        if not existing_admin:
            admin_user = User(
                name="System Administrator",
                email="admin@fundamics.com",
                phone="+919876543210",
                password_hash=hash_password("Admin@123"),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(admin_user)
            print("Created Admin: admin@fundamics.com / Admin@123")
        else:
            print("Admin already exists")

        # 3. Teacher User
        if not existing_teacher:
            teacher_user = User(
                name="Dr. Rajesh Verma",
                email="teacher@fundamics.com",
                phone="+919876543211",
                password_hash=hash_password("Teacher@123"),
                role=UserRole.TEACHER,
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(teacher_user)
            await session.flush()

            teacher_profile = Teacher(
                user_id=teacher_user.id,
                teacher_code="TCH-2026-001",
                biometric_employee_id="BIO-EMP-001",
                status="ACTIVE",
            )
            session.add(teacher_profile)
            print("Created Teacher: teacher@fundamics.com / Teacher@123")
        else:
            print("Teacher already exists")

        # 4. Student User
        if not existing_student:
            student_user = User(
                name="Aarav Sharma",
                email="student@fundamics.com",
                phone="+919876543212",
                password_hash=hash_password("Student@123"),
                role=UserRole.STUDENT,
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(student_user)
            await session.flush()

            student_profile = Student(
                user_id=student_user.id,
                student_code="STU-2026-001",
                class_id=class_obj.id,
                batch_id=batch_obj.id,
                admission_date=date.today(),
                status="ACTIVE",
            )
            session.add(student_profile)
            await session.flush()

            enrollment = Enrollment(
                student_id=student_profile.id,
                class_id=class_obj.id,
                batch_id=batch_obj.id,
                start_date=date.today(),
                status="ACTIVE",
            )
            session.add(enrollment)
            print("Created Student: student@fundamics.com / Student@123")
        else:
            print("Student already exists")

        await session.commit()
        print("Seeding completed successfully!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
