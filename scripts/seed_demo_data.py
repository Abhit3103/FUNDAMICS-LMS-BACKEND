"""
Seed script to insert demo Admin, Teacher, and Student accounts into PostgreSQL.
Usage:
    python scripts/seed_demo_data.py
"""

import asyncio
import uuid
from datetime import date
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.core.security import hash_password
from src.core.demo import DEMO_CREDENTIALS
from src.models.user import User, UserStatus, UserRole, Student, Teacher
from src.models.academic import Class, Batch, Enrollment, EnrollmentStatus


async def seed():
    async with AsyncSessionLocal() as session:
        print("🌱 Seeding demo accounts and academic structures into PostgreSQL...")

        # 1. Create or fetch a demo Class & Batch
        class_stmt = select(Class).where(Class.code == "CLS-12-SCI")
        res_class = await session.execute(class_stmt)
        demo_class = res_class.scalar_one_or_none()

        if not demo_class:
            demo_class = Class(
                id=uuid.uuid4(),
                name="Class XII - Science",
                code="CLS-12-SCI",
                grade_level=12,
                stream="Science",
                board="ISC",
                description="Class XII Science (PCM/PCB) Senior Secondary Batch",
                status="ACTIVE",
            )
            session.add(demo_class)
            await session.flush()

        batch_stmt = select(Batch).where(Batch.code == "BATCH-2025-A")
        res_batch = await session.execute(batch_stmt)
        demo_batch = res_batch.scalar_one_or_none()

        if not demo_batch:
            demo_batch = Batch(
                id=uuid.uuid4(),
                class_id=demo_class.id,
                name="Batch A (Morning Flagship)",
                code="BATCH-2025-A",
                academic_year="2025-2026",
                capacity=40,
                status="ACTIVE",
            )
            session.add(demo_batch)
            await session.flush()

        # 2. Seed Demo Users
        for email, demo in DEMO_CREDENTIALS.items():
            stmt = select(User).where(User.email == email)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()

            if existing:
                print(f"  ✓ User {email} already exists")
                continue

            user = User(
                id=demo["id"],
                name=demo["name"],
                email=demo["email"],
                phone=demo.get("phone"),
                password_hash=hash_password(demo["password"]),
                role=demo["role"],
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.flush()

            if demo["role"] == UserRole.TEACHER:
                teacher = Teacher(
                    user_id=user.id,
                    teacher_code=demo.get("teacher_code", "TCH-001"),
                    status="ACTIVE",
                )
                session.add(teacher)

            elif demo["role"] == UserRole.STUDENT:
                student = Student(
                    user_id=user.id,
                    student_code=demo.get("student_code", "FND-2025-1042"),
                    class_id=demo_class.id,
                    batch_id=demo_batch.id,
                    admission_date=date.today(),
                    status="ACTIVE",
                )
                session.add(student)
                await session.flush()

                enrollment = Enrollment(
                    student_id=student.id,
                    class_id=demo_class.id,
                    batch_id=demo_batch.id,
                    academic_year="2025-2026",
                    status=EnrollmentStatus.ACTIVE,
                )
                session.add(enrollment)

            print(f"  + Created {demo['role'].value}: {email} (passcode: {demo['password']})")

        await session.commit()
        print("✅ Demo accounts seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
