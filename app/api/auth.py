from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.db.session import get_db
from app.models.auth import User
from app.models.location import Location
from app.schema.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import auth_service
from app.services.email_service import email_service
from app.utils.constants import UserRole
from app.utils.security import get_current_user, require_roles

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse, summary="Login and retrieve Bearer token")
def login(login_data: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == login_data.email).first()

    if not user or not auth_service.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/phone number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact your administrator.",
        )

    token = auth_service.create_access_token(
        data={
            "sub": str(user.id),
            "user_id": user.id,
            "role": user.role.value,
            "email": user.email,
        }
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role.value,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
    )


from app.utils.location_helper import resolve_user_location


def _build_user_response(user: User, db: Session) -> UserResponse:
    is_admin = user.role == UserRole.ADMIN
    loc = (
        db.query(Location).filter(Location.id == user.location_id).first()
        if user.location_id
        else resolve_user_location(user, db)
    )
    loc_name = loc.hub_name if loc else (user.assigned_warehouse or user.primary_hub)
    loc_id = loc.id if loc else None

    return UserResponse(
        id=user.id,
        email=user.email,
        phone_number=user.phone_number,
        full_name=user.full_name,
        profile_photo=user.profile_photo,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_active=user.is_active,
        status=user.status,
        assigned_warehouse=user.assigned_warehouse,
        primary_hub=user.primary_hub,
        location_id=loc_id,
        location_name=loc_name,
        location=loc,
        location_scope=("ALL" if user.location_id is None else "LOCATION") if is_admin else None,
        can_view_all_locations=is_admin,
        available_locations=(
            db.query(Location).order_by(Location.hub_name.asc()).all()
            if is_admin
            else []
        ),
        created_at=user.created_at,
    )


@router.get("/me", response_model=UserResponse, summary="Get current logged in user details")
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the authenticated user's profile, active role, and assigned location/hub details."""
    return _build_user_response(current_user, db)


@router.patch("/me", response_model=UserResponse, summary="Update current user profile")
def update_current_user_profile(
    profile_in: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = profile_in.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="At least one profile field is required")

    if "location_scope" in updates:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can change location scope")
        requested_scope = updates.pop("location_scope")
        if requested_scope == "ALL":
            updates["location_id"] = None
        elif updates.get("location_id", current_user.location_id) is None:
            raise HTTPException(
                status_code=422,
                detail="location_id is required when selecting a specific location",
            )

    if "location_id" in updates:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can update their location")
        location_id = updates.pop("location_id")
        if location_id is not None and not db.query(Location.id).filter(Location.id == location_id).first():
            raise HTTPException(status_code=404, detail="Location not found")
        current_user.location_id = location_id

    for field, value in updates.items():
        setattr(current_user, field, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
        db.refresh(current_user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A user with these details already exists") from exc
    return _build_user_response(current_user, db)


@router.post(
    "/change-password",
    response_model=dict,
    summary="Change current driver or store manager password",
)
def change_password(
    password_in: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles([UserRole.DRIVER, UserRole.STORE_MANAGER])
    ),
):
    if not auth_service.verify_password(password_in.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if password_in.new_password != password_in.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New passwords do not match")
    if auth_service.verify_password(password_in.new_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different")

    current_user.hashed_password = auth_service.hash_password(password_in.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@router.post(
    "/forgot-password",
    response_model=dict,
    summary="Request a password reset for a driver or store manager",
)
def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.email.ilike(request.email),
        User.role.in_([UserRole.DRIVER, UserRole.STORE_MANAGER]),
        User.is_active.is_(True),
    ).first()
    if user:
        token = auth_service.create_access_token(
            {"sub": str(user.id), "purpose": "password_reset"},
            expires_delta=timedelta(minutes=30),
        )
        reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        background_tasks.add_task(
            email_service.send_password_reset_email,
            to_email=user.email,
            full_name=user.full_name,
            reset_url=reset_url,
        )
    return {"message": "If an active driver or store manager account exists, a password reset link has been sent."}

