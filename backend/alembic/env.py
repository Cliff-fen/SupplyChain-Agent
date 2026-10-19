import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

target_metadata = Base.metadata

if database_url := os.environ.get("SUPPLYMIND_DATABASE_URL"):
    context.config.set_main_option(
        "sqlalchemy.url", database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("sqlite+aiosqlite://", "sqlite://").replace("%", "%%")
    )

# The deployment uses a synchronous psycopg URL for Alembic.  The
# application itself remains async and uses the same metadata contract.


def run_migrations_offline() -> None:
    context.configure(url=context.config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def include_object(obj, name, type_, reflected, compare_to):
    # These are owned by the vector migration and LangGraph's own setup, not
    # application ORM tables. Do not suggest dropping them during drift checks.
    runtime_tables = {
        "checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations",
        "store", "store_migrations", "store_vectors",
    }
    if reflected and compare_to is None:
        if type_ == "table" and name in runtime_tables:
            return False
        if type_ == "index" and name == "ix_document_chunks_embedding_hnsw":
            return False
    return True


def run_migrations_online() -> None:
    connectable = engine_from_config(context.config.get_section(context.config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            # Existing databases may predate the first long revision identifier.
            # Expand the bookkeeping column before Alembic writes that revision.
            from sqlalchemy import inspect, text

            if inspect(connection).has_table("alembic_version"):
                connection.execute(text(
                    "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
                ))
            # has_table() itself autobegins a SQLAlchemy transaction even on
            # an empty database. End it before Alembic opens its transaction,
            # otherwise a successful first upgrade is rolled back on close.
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
