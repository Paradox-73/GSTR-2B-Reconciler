from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from api.settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        # hide_parameters: DB errors would otherwise print row values (names, amounts) to logs
        _engine = create_engine(url, pool_pre_ping=True, connect_args=args,
                                hide_parameters=True)
        SessionLocal.configure(bind=_engine)
    return _engine


def get_db():
    engine()
    with SessionLocal() as db:
        yield db
