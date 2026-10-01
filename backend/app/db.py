from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import DATA_DIR

engine = create_engine(
    f'sqlite:///{DATA_DIR / "qa.sqlite"}', connect_args={'check_same_thread': False}
)

# Columns added after the first release: (table, column, DDL type)
_MIGRATIONS = [('run', 'flow_run_id', 'INTEGER')]


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in _MIGRATIONS:
            if column not in {c['name'] for c in insp.get_columns(table)}:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
