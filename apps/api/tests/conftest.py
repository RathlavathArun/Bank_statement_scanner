import os
import sys
import tempfile
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
db_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_file.name}")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("CLAMAV_ENABLED", "false")

from db.database import Base, get_db  # noqa: E402
from db.models import User  # noqa: E402
from auth.dependencies import get_current_user  # noqa: E402
from main import app  # noqa: E402

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture
async def auth_user():
    return User(
        id=TEST_USER_ID,
        email="test@example.com",
        password_hash="test",
        full_name="Test User",
        email_verified=True,
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db, auth_user):
    async def override_get_db():
        yield db

    async def override_get_current_user():
        return auth_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
