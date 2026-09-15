from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config.settings import settings

# Normalizing URL if postgres:// or postgresql:// is provided to use psycopg2 driver
database_url = settings.DATABASE_URL
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif database_url.startswith("postgresql://") and "+psycopg2" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# SQLAlchemy engine configured for reliable connection pooling across local or cloud PostgreSQL (Supabase, Neon, RDS)
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency generator for FastAPI routes that provides an isolated database session
    and guarantees proper closure.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
