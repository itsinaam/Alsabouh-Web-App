from enum import Enum


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    STORE_MANAGER = "STORE_MANAGER"
    DRIVER = "DRIVER"


class DriverStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ShiftSchedule(str, Enum):
    MORNING = "Morning"
    EVENING = "Evening"
    NIGHT = "Night"
    FULL_TIME = "Full-Time"
    ROTATING = "Rotating"


class LicenseCategory(str, Enum):
    LIGHT_VEHICLE = "Light Vehicle"
    HEAVY_VEHICLE = "Heavy Vehicle"
    MOTORCYCLE = "Motorcycle"
    BUS = "Bus"
    OTHER = "Other"
