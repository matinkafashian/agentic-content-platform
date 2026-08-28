import pytest
from sqlalchemy.orm import Session

from app.core.database import Base, build_engine, build_session_factory


@pytest.fixture
def db_session(tmp_path) -> Session:
    engine = build_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()
