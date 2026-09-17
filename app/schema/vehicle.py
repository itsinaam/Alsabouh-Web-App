from datetime import date, datetime
from typing import List, Optional

from fastapi import Form
from pydantic import BaseModel, ConfigDict, Field


class VehicleBase(BaseModel):
	internal_fleet_code: Optional[str] = Field(None, max_length=100)
	make_chassis_model: Optional[str] = Field(None, max_length=255)
	truck_type_asset_category: Optional[str] = Field(None, max_length=100)
	gross_payload_capacity: Optional[int] = Field(None, ge=0)
	commercial_plate_number: Optional[str] = Field(None, max_length=50)
	mulkiya_expiry_date: Optional[date] = None
	insurance_provider: Optional[str] = Field(None, max_length=255)
	insurance_expiry_date: Optional[date] = None
	assigned_home_depot: Optional[int] = Field(None, gt=0)
	designated_primary_driver: Optional[int] = Field(None, gt=0)
	initial_operational_status: bool = True
	status: Optional[str] = Field(None, max_length=100)


class VehicleCreate(VehicleBase):
	@classmethod
	def as_form(
		cls,
		internal_fleet_code: Optional[str] = Form(None),
		make_chassis_model: Optional[str] = Form(None),
		truck_type_asset_category: Optional[str] = Form(None),
		gross_payload_capacity: Optional[int] = Form(None),
		commercial_plate_number: Optional[str] = Form(None),
		mulkiya_expiry_date: Optional[date] = Form(None),
		insurance_provider: Optional[str] = Form(None),
		insurance_expiry_date: Optional[date] = Form(None),
		assigned_home_depot: Optional[int] = Form(None),
		designated_primary_driver: Optional[int] = Form(None),
		initial_operational_status: Optional[bool] = Form(True),
		status: Optional[str] = Form(None),
	) -> "VehicleCreate":
		return cls(
			internal_fleet_code=internal_fleet_code,
			make_chassis_model=make_chassis_model,
			truck_type_asset_category=truck_type_asset_category,
			gross_payload_capacity=gross_payload_capacity,
			commercial_plate_number=commercial_plate_number,
			mulkiya_expiry_date=mulkiya_expiry_date,
			insurance_provider=insurance_provider,
			insurance_expiry_date=insurance_expiry_date,
			assigned_home_depot=assigned_home_depot,
			designated_primary_driver=designated_primary_driver,
			initial_operational_status=initial_operational_status,
			status=status,
		)


class VehicleUpdate(BaseModel):
	internal_fleet_code: Optional[str] = Field(None, max_length=100)
	make_chassis_model: Optional[str] = Field(None, max_length=255)
	truck_type_asset_category: Optional[str] = Field(None, max_length=100)
	gross_payload_capacity: Optional[int] = Field(None, ge=0)
	commercial_plate_number: Optional[str] = Field(None, max_length=50)
	mulkiya_expiry_date: Optional[date] = None
	insurance_provider: Optional[str] = Field(None, max_length=255)
	insurance_expiry_date: Optional[date] = None
	assigned_home_depot: Optional[int] = Field(None, gt=0)
	designated_primary_driver: Optional[int] = Field(None, gt=0)
	initial_operational_status: Optional[bool] = None
	status: Optional[str] = Field(None, max_length=100)

	@classmethod
	def as_form(
		cls,
		internal_fleet_code: Optional[str] = Form(None),
		make_chassis_model: Optional[str] = Form(None),
		truck_type_asset_category: Optional[str] = Form(None),
		gross_payload_capacity: Optional[int] = Form(None),
		commercial_plate_number: Optional[str] = Form(None),
		mulkiya_expiry_date: Optional[date] = Form(None),
		insurance_provider: Optional[str] = Form(None),
		insurance_expiry_date: Optional[date] = Form(None),
		assigned_home_depot: Optional[int] = Form(None),
		designated_primary_driver: Optional[int] = Form(None),
		initial_operational_status: Optional[bool] = Form(None),
		status: Optional[str] = Form(None),
	) -> "VehicleUpdate":
		values = {
			"internal_fleet_code": internal_fleet_code,
			"make_chassis_model": make_chassis_model,
			"truck_type_asset_category": truck_type_asset_category,
			"gross_payload_capacity": gross_payload_capacity,
			"commercial_plate_number": commercial_plate_number,
			"mulkiya_expiry_date": mulkiya_expiry_date,
			"insurance_provider": insurance_provider,
			"insurance_expiry_date": insurance_expiry_date,
			"assigned_home_depot": assigned_home_depot,
			"designated_primary_driver": designated_primary_driver,
			"initial_operational_status": initial_operational_status,
			"status": status,
		}
		return cls(**{key: value for key, value in values.items() if value not in (None, "")})


class VehicleResponse(VehicleBase):
	id: int
	mulkiya_inspection_document: List[str] = Field(default_factory=list)
	created_at: datetime
	updated_at: datetime

	model_config = ConfigDict(from_attributes=True)


class VehicleListCounts(BaseModel):
	total: int
	assigned: int
	unassigned: int
	under_maintenance: int


class VehicleListResponse(BaseModel):
	total: int
	skip: int
	limit: int
	counts: VehicleListCounts
	items: List[VehicleResponse]
