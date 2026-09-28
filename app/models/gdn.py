from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GDN(Base):
	__tablename__ = "gdn"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
	location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("location.id"), nullable=True, index=True)
	created_by_user_id: Mapped[Optional[int]] = mapped_column(
		ForeignKey("users.id"), nullable=True, index=True
	)

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
	run_planner: Mapped[Optional["RunPlanner"]] = relationship("RunPlanner", back_populates="gdns")
	image_groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

	# Goods Delivery Note details
	gdn_reference: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
	loaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
	loading_dock: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
	pallets_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
	transporter_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

	# Site access details the driver needs on arrival.
	gate_passcode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
	site_contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	site_contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
	target_gate: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
	height_restriction: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

	# Stamped by the driver app as the stop progresses.
	arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
	delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

	distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
	eta_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
	)
