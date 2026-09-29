import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.main import app
from src.database import get_db

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5433/fundamics_test",
)

# Safety Guardrails: Guarantee tests ONLY run on local Docker fundamics_test and NEVER on Supabase or fundamics_lms
assert "supabase" not in TEST_DATABASE_URL.lower(), "ABORT: TEST_DATABASE_URL points to Supabase!"
assert "fundamics_test" in TEST_DATABASE_URL.lower(), "ABORT: TEST_DATABASE_URL must target fundamics_test!"

engine = create_async_engine(
    TEST_DATABASE_URL,
    future=True,
    echo=False,
)

TestingSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture
async def db_session():
    """Provides an isolated transaction for testing that always rolls back."""
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def async_client(db_session):
    """FastAPI async test client with database dependency override to prevent hitting production/Supabase."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()