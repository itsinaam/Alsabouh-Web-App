from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schema.gdn import GDNResponse


class AuditVehicle(BaseModel):
    id: int
    internal_fleet_code: Optional[str] = None
    make_chassis_model: Optional[str] = None
    truck_type_asset_category: Optional[str] = None
    gross_payload_capacity: Optional[int] = None
    commercial_plate_number: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditDriver(BaseModel):
    id: int
    full_name: str
    employee_id: Optional[str] = None
    phone_number: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditLocation(BaseModel):
    id: int
    hub_name: str
    emirate_jurisdiction: str
    street_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditRunResponse(BaseModel):
    run_id: int
    dispatch_date: date
    planned_departure_time: str
    lifecycle_status: str
    vehicle: AuditVehicle
    driver: Optional[AuditDriver] = None
    dispatch_location: Optional[AuditLocation] = None
    route_sites: list[str] = Field(default_factory=list)
    stops_completed: int = 0
    total_stops: int = 0
    payload_dispatched: int = 0
    payload_capacity: Optional[int] = None
    payload_utilization_percent: Optional[float] = None
    assigned_gdns: list[GDNResponse] = Field(default_factory=list)
    pod_photos_count: int = 0
    digital_signatures_count: int = 0
    pod_audit_status: str = "Not Available"
    audit_status: str = "Pending Final Sign-off"
    created_at: datetime
    updated_at: datetime


class AuditStats(BaseModel):
    total_completed_runs: int
    on_time_delivery_rate: Optional[float] = None
    total_payload_dispatched: int
    geotagged_pods_verified: int
    pod_disputes_raised: int = 0


class AuditListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    stats: AuditStats
    items: list[AuditRunResponse]
