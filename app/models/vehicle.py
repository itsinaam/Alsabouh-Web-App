from datetime import date, datetime
from typing import Optional
from sqlalchemy import String, Integer, Date, DateTime, func, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)

    # Vehicle Specifications
    internal_fleet_code: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    make_chassis_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    truck_type_asset_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gross_payload_capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # UAE Mulkiya & Insurance Compliance
    commercial_plate_number: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    mulkiya_expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    insurance_expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    mulkiya_inspection_document: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    # Depot & Driver Assignment
    assigned_home_depot: Mapped[Optional[int]] = mapped_column(ForeignKey("location.id"), nullable=True, index=True)
    designated_primary_driver: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    initial_operational_status:  Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)