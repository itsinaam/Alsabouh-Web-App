from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Hub(Base):
    __tablename__ = "hubs"


    id: Mapped[int] = mapped_column(primary_key=True,index=True,autoincrement=True)
    hub_name: Mapped[str] = mapped_column(String(255), nullable=False)
    emirate_jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False)
    hub_classification: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    street_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    industrial_plot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gps_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    loading_bays_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    infrastructure_notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    direct_contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)