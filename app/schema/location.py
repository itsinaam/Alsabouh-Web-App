from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class HubBase(BaseModel):
    hub_name: str
    emirate_jurisdiction: str
    hub_classification: Optional[str] = None
    street_address: Optional[str] = None
    industrial_plot: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    loading_bays_count: int = 0
    infrastructure_notes: Optional[str] = None
    direct_contact_phone: Optional[str] = None
    status: Optional[str] = "Active"


class HubCreate(HubBase):
    model_config = {
        "json_schema_extra": {
            "example": {
                "hub_name": "Dubai Central Logistics Hub",
                "emirate_jurisdiction": "Dubai",
                "hub_classification": "Central Distribution Center",
                "street_address": "Street 18, Al Quoz Industrial Area 3",
                "industrial_plot": "Plot 368-452",
                "gps_latitude": 25.1384,
                "gps_longitude": 55.2346,
                "loading_bays_count": 8,
                "infrastructure_notes": "Equipped with temperature-controlled storage and 24/7 security",
                "direct_contact_phone": "+97143214567",
                "status": "Active",
            }
        }
    }


class HubUpdate(BaseModel):
    hub_name: Optional[str] = None
    emirate_jurisdiction: Optional[str] = None
    hub_classification: Optional[str] = None
    street_address: Optional[str] = None
    industrial_plot: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    loading_bays_count: Optional[int] = None
    infrastructure_notes: Optional[str] = None
    direct_contact_phone: Optional[str] = None
    status: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "hub_name": "Dubai Central Logistics Hub",
                "emirate_jurisdiction": "Dubai",
                "hub_classification": "Central Distribution Center",
                "street_address": "Street 18, Al Quoz Industrial Area 3",
                "industrial_plot": "Plot 368-452",
                "gps_latitude": 25.1384,
                "gps_longitude": 55.2346,
                "loading_bays_count": 8,
                "infrastructure_notes": "Equipped with temperature-controlled storage and 24/7 security",
                "direct_contact_phone": "+97143214567",
                "status": "Active",
            }
        }
    }



class HubResponse(HubBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HubListResponse(BaseModel):
    total: int
    total_active: int = 0
    total_draft: int = 0
    assigned_fleet_units: int = 0
    today_dispatched_volume: int = 0
    skip: int
    limit: int
    items: List[HubResponse]

    class Config:
        from_attributes = True


class HubDropdownResponse(BaseModel):
    id: int
    hub_name: str

    class Config:
        from_attributes = True

