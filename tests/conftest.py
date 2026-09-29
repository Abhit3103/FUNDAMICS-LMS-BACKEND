import os
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",
)

engine = create_async_engine(
    TEST_DATABASE_URL,
    future=True,
)

TestingSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()