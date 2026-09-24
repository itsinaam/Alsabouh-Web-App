from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.auth import User
from app.services.auth_service import auth_service
from app.utils.constants import UserRole


def _ensure_gdn_assignment_column() -> None:
    inspector = inspect(engine)
    if "gdn" not in inspector.get_table_names():
        return
    if "run_planner_id" not in {column["name"] for column in inspector.get_columns("gdn")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE gdn ADD COLUMN run_planner_id INTEGER"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_gdn_run_planner_id ON gdn (run_planner_id)"))


def _ensure_gdn_location_columns() -> None:
    inspector = inspect(engine)
    if "gdn" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("gdn")}
    column_type = "REAL" if engine.dialect.name == "sqlite" else "DOUBLE PRECISION"
    missing_columns = [column for column in ("latitude", "longitude") if column not in columns]
    if missing_columns:
        with engine.begin() as connection:
            for column in missing_columns:
                connection.execute(text(f"ALTER TABLE gdn ADD COLUMN {column} {column_type}"))


def init_db() -> None:
    """
    Creates database schema if not present and seeds the initial Super Admin account
    configured in .env via python-decouple.
    """
    print("[InitDB] Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)
    _ensure_gdn_assignment_column()
    _ensure_gdn_location_columns()

    db: Session = SessionLocal()
    try:
        admin_email = settings.ADMIN_EMAIL
        existing_admin = db.query(User).filter(User.email == admin_email).first()

        if not existing_admin:
            print(f"[InitDB] Seeding Super Admin account ({admin_email})...")
            admin_user = User(
                email=admin_email,
                phone_number="+971500000000",
                full_name=settings.ADMIN_NAME,
                hashed_password=auth_service.hash_password(settings.ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin_user)
            db.commit()
            print(f"[InitDB] Admin user seeded successfully! Email: {admin_email}")
        else:
            print(f"[InitDB] Admin user already exists: {admin_email}")
    except Exception as e:
        print(f"[InitDB] Error during admin seeding: {e}")
        db.rollback()
    finally:
        db.close()
