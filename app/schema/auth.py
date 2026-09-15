from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.utils.constants import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    full_name: str
    email: Optional[str] = None


class UserCreate(BaseModel):
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    full_name: str
    password: str
    role: UserRole = UserRole.DRIVER


class UserResponse(BaseModel):
    id: int
    email: Optional[str] = None
    phone_number: Optional[str] = None
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
