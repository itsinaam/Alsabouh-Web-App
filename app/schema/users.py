from datetime import date, datetime
from typing import Optional
from fastapi import Form
from pydantic import BaseModel, EmailStr


class DriverRegisterRequest(BaseModel):
    """
    Structured Request Model for registering a new Driver via Form-Data.
    Excludes employee_id, profile_photo, and password (password is auto-generated).
    """
    full_name: str
    email: EmailStr
    phone_number: str
    role: str 
    emirates_id: Optional[str] = None
    nationality: Optional[str] = None
    alternate_emergency_contact: Optional[str] = None
    licence_number: Optional[str] = None
    rta_permit_number: Optional[str] = None
    licence_category: Optional[str] = "Light Vehicle"
    licence_expiry_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    medical_fitness: Optional[str] = "Fit to Drive"
    primary_hub: Optional[str] = None
    shift_schedule: Optional[str] = "Morning"
    initial_vehicle_assignment: Optional[str] = None
    active_duty: bool = True
    status: Optional[str] 

    @classmethod
    def as_form(
        cls,
        full_name: str = Form(..., description="Full Legal Name as per National ID"),
        email: EmailStr = Form(..., description="Driver Email (credentials will be sent here)"),
        phone_number: str = Form(..., description="Primary Mobile / WhatsApp Number"),
        role: str = Form(..., description="Roles: Driver, Store Team, Sales Team"),
        emirates_id: Optional[str] = Form(None, description="National ID / Emirates ID"),
        nationality: Optional[str] = Form(None),
        alternate_emergency_contact: Optional[str] = Form(None),
        licence_number: Optional[str] = Form(None, description="Driving License Number"),
        rta_permit_number: Optional[str] = Form(None, description="RTA Permit / Traffic File Number"),
        licence_category: Optional[str] = Form("Light Vehicle"),
        licence_expiry_date: Optional[date] = Form(None),
        issuing_authority: Optional[str] = Form(None),
        medical_fitness: Optional[str] = Form("Fit to Drive"),
        primary_hub: Optional[str] = Form(None, description="Assigned Store / Hub"),
        shift_schedule: Optional[str] = Form("Morning"),
        initial_vehicle_assignment: Optional[str] = Form(None),
        active_duty: bool = Form(True),
        status: Optional[str] = Form("Available", description="Status: Available, On Route, Off Duty, etc."),
    ) -> "DriverRegisterRequest":
        return cls(
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            role=role,
            emirates_id=emirates_id,
            nationality=nationality,
            alternate_emergency_contact=alternate_emergency_contact,
            licence_number=licence_number,
            rta_permit_number=rta_permit_number,
            licence_category=licence_category,
            licence_expiry_date=licence_expiry_date,
            issuing_authority=issuing_authority,
            medical_fitness=medical_fitness,
            primary_hub=primary_hub,
            shift_schedule=shift_schedule,
            initial_vehicle_assignment=initial_vehicle_assignment,
            active_duty=active_duty,
            status=status,
        )


class StoreManagerRegisterRequest(BaseModel):
    """
    Request model for registering a Store & Warehouse Manager.
    Accepts full name, employee id, mobile/whatsapp, email, warehouse, responsibility, status, and role.
    """
    full_name: str
    employee_id: Optional[str] = None
    phone_number: str
    email: EmailStr
    assigned_warehouse: Optional[str] = None
    responsibility: Optional[str] = None
    status: Optional[str] = "active"
    role: str = "STORE_MANAGER"


class StoreManagerResponse(BaseModel):
    id: int
    full_name: str
    employee_id: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    is_active: bool
    assigned_warehouse: Optional[str] = None
    responsibility: Optional[str] = None
    status: Optional[str] = None
    profile_photo: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StoreManagerUpdate(BaseModel):
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    assigned_warehouse: Optional[str] = None
    responsibility: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class DriverResponse(BaseModel):
    id: int
    full_name: str
    employee_id: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    is_active: bool
    status: Optional[str] = None
    profile_photo: Optional[str] = None

    # Driver Specific Fields
    emirates_id: Optional[str] = None
    nationality: Optional[str] = None
    alternate_emergency_contact: Optional[str] = None
    licence_number: Optional[str] = None
    rta_permit_number: Optional[str] = None
    licence_category: Optional[str] = None
    licence_expiry_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    medical_fitness: Optional[str] = None

    # Attachment URLs
    license_front_copy: Optional[str] = None
    license_back_copy: Optional[str] = None
    medical_fitness_card: Optional[str] = None

    # Operational fields
    primary_hub: Optional[str] = None
    shift_schedule: Optional[str] = None
    initial_vehicle_assignment: Optional[str] = None
    active_duty: Optional[bool] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProfilePictureResponse(BaseModel):
    status: str = "success"
    message: str
    user_id: int
    role: str
    profile_photo: Optional[str] = None


class DriverUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    role: Optional[str] = None
    emirates_id: Optional[str] = None
    nationality: Optional[str] = None
    alternate_emergency_contact: Optional[str] = None
    licence_number: Optional[str] = None
    rta_permit_number: Optional[str] = None
    licence_category: Optional[str] = None
    licence_expiry_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    medical_fitness: Optional[str] = None
    primary_hub: Optional[str] = None
    shift_schedule: Optional[str] = None
    initial_vehicle_assignment: Optional[str] = None
    active_duty: Optional[bool] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None

    @classmethod
    def as_form(
        cls,
        full_name: Optional[str] = Form(None),
        email: Optional[EmailStr] = Form(None),
        phone_number: Optional[str] = Form(None),
        role: Optional[str] = Form(None),
        emirates_id: Optional[str] = Form(None),
        nationality: Optional[str] = Form(None),
        alternate_emergency_contact: Optional[str] = Form(None),
        licence_number: Optional[str] = Form(None),
        rta_permit_number: Optional[str] = Form(None),
        licence_category: Optional[str] = Form(None),
        licence_expiry_date: Optional[date] = Form(None),
        issuing_authority: Optional[str] = Form(None),
        medical_fitness: Optional[str] = Form(None),
        primary_hub: Optional[str] = Form(None),
        shift_schedule: Optional[str] = Form(None),
        initial_vehicle_assignment: Optional[str] = Form(None),
        active_duty: Optional[bool] = Form(None),
        status: Optional[str] = Form(None),
        is_active: Optional[bool] = Form(None),
    ) -> "DriverUpdate":
        def clean(val):
            if isinstance(val, str) and not val.strip():
                return None
            return val

        return cls(
            full_name=clean(full_name),
            email=email,
            phone_number=clean(phone_number),
            role=clean(role),
            emirates_id=clean(emirates_id),
            nationality=clean(nationality),
            alternate_emergency_contact=clean(alternate_emergency_contact),
            licence_number=clean(licence_number),
            rta_permit_number=clean(rta_permit_number),
            licence_category=clean(licence_category),
            licence_expiry_date=licence_expiry_date,
            issuing_authority=clean(issuing_authority),
            medical_fitness=clean(medical_fitness),
            primary_hub=clean(primary_hub),
            shift_schedule=clean(shift_schedule),
            initial_vehicle_assignment=clean(initial_vehicle_assignment),
            active_duty=active_duty,
            status=clean(status),
            is_active=is_active,
        )


class UserDetailResponse(BaseModel):
    """Unified user response returning all available fields."""
    id: int
    full_name: str
    employee_id: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    is_active: bool
    status: Optional[str] = None

    # Profile photo
    profile_photo: Optional[str] = None
    emirates_id: Optional[str] = None
    nationality: Optional[str] = None
    alternate_emergency_contact: Optional[str] = None
    licence_number: Optional[str] = None
    rta_permit_number: Optional[str] = None
    licence_category: Optional[str] = None
    licence_expiry_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    medical_fitness: Optional[str] = None
    license_front_copy: Optional[str] = None
    license_back_copy: Optional[str] = None
    medical_fitness_card: Optional[str] = None
    primary_hub: Optional[str] = None
    shift_schedule: Optional[str] = None
    initial_vehicle_assignment: Optional[str] = None
    active_duty: Optional[bool] = None

    # Store manager specific
    assigned_warehouse: Optional[str] = None
    responsibility: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
