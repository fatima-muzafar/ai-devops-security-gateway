"""
Shared SQLAlchemy 2.0 declarative base + engine + session.

Imported by both the FastAPI app and Alembic's env.py so there is exactly
one source of truth for table metadata. Do not create a second Base
anywhere else in the project.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL not set. Check backend/.env exists and matches "
        "backend/.env.example / docker-compose.yml credentials."
    )

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the project."""
    pass


def get_db():
    """FastAPI dependency — yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
