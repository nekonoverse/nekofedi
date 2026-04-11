from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.sql import func

from . import config as _config_paths


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    host = Column(String, nullable=False)
    username = Column(String)
    token = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    software = Column(String)
    scheme = Column(String)
    default_visibility = Column(String, nullable=False, default="public", server_default="public")
    default_timeline = Column(String, nullable=False, default="home", server_default="home")
    created_at = Column(DateTime, server_default=func.now())


class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String, primary_key=True)
    value = Column(String)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _config_paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{_config_paths.DB_PATH}")
    return _engine


def get_session():
    return Session(get_engine())
