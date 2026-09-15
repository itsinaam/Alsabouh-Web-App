from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Boolean, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum as SQLEnum

from app.db.base import Base
from app.utils.constants import UserRole


class User(Base):
    __tablename__ = "users"

    # Common Fields
    id: Mapped[int] = mapped_column( primary_key=True, index=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255),nullable=False)
    employee_id: Mapped[Optional[str]] = mapped_column(String(100),unique=True, index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255),unique=True,index=True, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50),unique=True,index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255),nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole,name="user_role_enum",native_enum=False),default=UserRole.DRIVER,nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean,default=True,nullable=False)

  
    # Profile Photo / Avatar (Common across all user roles)
    profile_photo: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    emirates_id: Mapped[Optional[str]] = mapped_column(String(50),nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String(100),nullable=True)
    alternate_emergency_contact: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    licence_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    rta_permit_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    licence_category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    licence_expiry_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )

    issuing_authority: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    medical_fitness: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    license_front_copy: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    license_back_copy: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    medical_fitness_card: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    primary_hub: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    shift_schedule: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    initial_vehicle_assignment: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    active_duty: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    # =========================
    # Store Manager Fields
    # =========================

    assigned_warehouse: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    responsibility: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # =========================
    # Timestamps
    # =========================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )