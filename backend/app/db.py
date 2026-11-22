import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

class Base(DeclarativeBase):
    pass

@lru_cache(maxsize=1)
def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        if os.getenv("APP_ENV", "development") == "production":
            raise RuntimeError("DATABASE_URL is required in production")
        url = "sqlite:///./glosas_dev.db"
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)

def get_db():
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session

def init_local_database():
    if os.getenv("APP_ENV", "development") == "production":
        return  # Production schema deployment must use a controlled migration.
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=get_engine())
