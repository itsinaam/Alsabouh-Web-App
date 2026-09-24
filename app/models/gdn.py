from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GDN(Base):
	__tablename__ = "gdn"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)

	# Invoice details
	customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	site_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
	longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
	materials_description_summary: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
	invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
	line_items: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True, default=list)
	payment_status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending")
	status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="Pending", index=True)
	weight: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
	assign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
	run_planner_id: Mapped[Optional[int]] = mapped_column(
		ForeignKey("run_planners.id"), nullable=True, index=True
	)
	image_groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

	# Goods Delivery Note details
	gdn_reference: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
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
