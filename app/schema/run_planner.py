from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.run_planner import RunPlannerStatus


class RunPlannerBase(BaseModel):
    commercial_vehicle_id: int = Field(..., gt=0)
    dispatch_location_id: int = Field(..., gt=0)
    driver_id: int = Field(..., gt=0)
    dispatch_date: date
    planned_departure_time: time
    status: RunPlannerStatus = RunPlannerStatus.READY_TO_DISPATCH


class RunPlannerCreate(RunPlannerBase):
    pass


class RunPlannerUpdate(BaseModel):
    commercial_vehicle_id: Optional[int] = Field(None, gt=0)
    dispatch_location_id: Optional[int] = Field(None, gt=0)
    driver_id: Optional[int] = Field(None, gt=0)
    dispatch_date: Optional[date] = None
    planned_departure_time: Optional[time] = None
    status: Optional[RunPlannerStatus] = None


class RunPlannerResponse(RunPlannerBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunPlannerStats(BaseModel):
    active_runs: int
    on_route: int
    awaiting_dispatch: int
    completed_today: int


class RunPlannerListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    stats: RunPlannerStats
    items: list[RunPlannerResponse]


class AssignGDNRequest(BaseModel):
    gdn_id: int = Field(..., gt=0)
