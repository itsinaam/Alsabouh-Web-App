from datetime import date, datetime, time
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Time, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunPlannerStatus(str, Enum):
	DISPATCHED = "Dispatched"
	READY_TO_DISPATCH = "Ready to Dispatch"


class RunPlanner(Base):
	__tablename__ = "run_planners"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
	commercial_vehicle_id: Mapped[int] = mapped_column(
		ForeignKey("vehicles.id"), nullable=False, index=True
	)
	dispatch_location_id: Mapped[int] = mapped_column(
		ForeignKey("location.id"), nullable=False, index=True
	)
	driver_id: Mapped[int] = mapped_column(
		ForeignKey("users.id"), nullable=False, index=True
	)
	dispatch_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
	planned_departure_time: Mapped[time] = mapped_column(Time, nullable=False)
	status: Mapped[RunPlannerStatus] = mapped_column(
		SQLEnum(RunPlannerStatus, name="run_planner_status_enum", native_enum=False),
		nullable=False,
		default=RunPlannerStatus.READY_TO_DISPATCH,
		index=True,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
	)
