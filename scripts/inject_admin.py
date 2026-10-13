import asyncio
from datetime import datetime, timezone
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from src.config import settings
from src.core.security import hash_password, create_access_token
from src.models.user import User, UserRole, UserStatus


async def inject_admin():
    print("=" * 60)
    print("FUNDAMICS LMS - Temporary Admin User Injection")
    print("=" * 60)

    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        target_email = "admin@fundamics.com"
        target_password = "Admin@123"
        hashed = hash_password(target_password)

        stmt = select(User).where(User.email == target_email)
        result = await session.execute(stmt)
        admin_user = result.scalar_one_or_none()

        if admin_user:
            admin_user.password_hash = hashed
            admin_user.role = UserRole.ADMIN
            admin_user.status = UserStatus.ACTIVE
            if not admin_user.email_verified_at:
                admin_user.email_verified_at = datetime.now(timezone.utc)
            admin_user.updated_at = datetime.now(timezone.utc)
            print(f"[OK] Existing user '{target_email}' updated with role ADMIN and password '{target_password}'.")
        else:
            admin_user = User(
                id=uuid.uuid4(),
                name="System Administrator",
                email=target_email,
                phone="+919876543210",
                password_hash=hashed,
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(admin_user)
            print(f"[OK] Injected new user '{target_email}' with role ADMIN and password '{target_password}'.")

        await session.commit()
        await session.refresh(admin_user)

        # Generate a test access token for quick testing / API calls
        token = create_access_token(
            subject=str(admin_user.id),
            role=admin_user.role.value,
        )

        print("\nAdmin Account Details:")
        print(f"  • ID:            {admin_user.id}")
        print(f"  • Email:         {admin_user.email}")
        print(f"  • Password:      {target_password}")
        print(f"  • Role:          {admin_user.role.value}")
        print(f"  • Status:        {admin_user.status.value}")
        print(f"  • Email Verified: {admin_user.email_verified_at is not None}")
        print(f"\nImmediate Bearer Token (Expires in {settings.ACCESS_TOKEN_EXPIRE_MINUTES} mins):")
        print(f"  {token}\n")
        print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(inject_admin())
