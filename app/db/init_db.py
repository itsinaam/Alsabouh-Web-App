from sqlalchemy.orm import Session
from app.config.settings import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.auth import User
from app.services.auth_service import auth_service
from app.utils.constants import UserRole


def init_db() -> None:
    """
    Creates database schema if not present and seeds the initial Super Admin account
    configured in .env via python-decouple.
    """
    print("[InitDB] Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)

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
