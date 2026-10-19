"""Keep unit/API tests isolated from local databases and other test cases."""

import asyncio
import os
import tempfile

import pytest

_database_directory = tempfile.TemporaryDirectory(prefix="supplymind-pytest-")
os.environ["SUPPLYMIND_DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{_database_directory.name}/tests.db"
)


@pytest.fixture(autouse=True)
def isolated_database():
    # Some modules import the shared session factory during collection. Clear
    # its dedicated test database instead of relying on import order or on
    # changing an environment variable after the engine already exists.
    from app.db import engine
    from app.models import Base

    assert engine.url.get_backend_name() == "sqlite"
    assert str(engine.url.database).startswith(_database_directory.name)

    async def reset():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())
    yield
