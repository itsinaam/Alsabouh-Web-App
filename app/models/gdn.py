from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GDN(Base):
	__tablename__ = "gdn"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)

	# Invoice details
	customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
	site_name: Mapped[str] = mapped_column(String(255), nullable=False)
	materials_description_summary: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
	invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
	line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
	payment_status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending")
	status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="Pending", index=True)

	# Goods Delivery Note details
	gdn_reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
	loaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
	loading_dock: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
	pallets_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
	transporter_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
	)
