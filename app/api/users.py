from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.auth import User
from app.schema.users import (
    DriverRegisterRequest,
    DriverResponse,
    DriverUpdate,
    ProfilePictureResponse,
    StoreManagerRegisterRequest,
    StoreManagerResponse,
    StoreManagerUpdate,
    UserDetailResponse,
)
from app.services.email_service import email_service
from app.services.users_service import users_service
from app.utils.constants import UserRole
from app.utils.location_helper import resolve_user_location
from app.utils.security import get_current_user, require_roles

router = APIRouter(prefix="/user", tags=["Users Management"])


def _ensure_user_location(current_user: User, target_user: User, db: Session) -> None:
    if current_user.role not in {UserRole.ADMIN, UserRole.STORE_MANAGER}:
        return
    user_loc = resolve_user_location(current_user, db)
    if not user_loc:
        return
    target_location_id = target_user.location_id
    if target_location_id is None:
        assignment = (
            target_user.assigned_warehouse
            if target_user.role == UserRole.STORE_MANAGER
            else target_user.primary_hub
        )
        if assignment:
            target_loc = resolve_user_location(target_user, db)
            target_location_id = target_loc.id if target_loc else None
    if target_location_id != user_loc.id:
        raise HTTPException(status_code=404, detail="User not found")


# =====================================================================
# 1. STORE MANAGER REGISTRATION (Admin Only)
# =====================================================================

@router.post(
    "/store-manager/register",
    response_model=StoreManagerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Store Manager (Admin Only)"
)
def register_store_manager(
    background_tasks: BackgroundTasks,
    manager_data: StoreManagerRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    """
    Registers a new Store & Warehouse Manager. Accessible only by Admin.
    - Fields: full_name, employee_id, phone_number, email, assigned_warehouse, responsibility, status, role.
    - Password is auto-generated and hashed.
    - Dispatches unified welcome email with login credentials.
    """
    user_loc = resolve_user_location(current_user, db)
    if user_loc and manager_data.location_id != user_loc.id:
        raise HTTPException(status_code=403, detail="Store managers can only be created in your selected location")
    manager, generated_password = users_service.create_store_manager(
        db=db,
        manager_in=manager_data,
    )

    if manager.email:
        background_tasks.add_task(
            email_service.send_welcome_credentials_email,
            to_email=manager.email,
            full_name=manager.full_name,
            generated_password=generated_password,
            role=manager.role.value,
        )

    return manager


# =====================================================================
# 2. DRIVER REGISTRATION (Admin and Store Manager)
# =====================================================================

@router.post(
    "/driver/register",
    response_model=DriverResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Driver with Document Uploads"
)
async def add_driver(
    background_tasks: BackgroundTasks,
    driver_data: DriverRegisterRequest = Depends(DriverRegisterRequest.as_form),
    license_front_copy: Optional[UploadFile] = File(None, description="Front side of driving license"),
    license_back_copy: Optional[UploadFile] = File(None, description="Back side of driving license"),
    medical_fitness_card: Optional[UploadFile] = File(None, description="Medical fitness certificate/card"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.STORE_MANAGER])),
):
    """
    Registers a new Driver record with file uploads to Supabase storage.
    - Password is auto-generated and hashed.
    - Dispatches unified welcome email with login credentials.
    """
    if current_user.role == UserRole.STORE_MANAGER:
        user_loc = resolve_user_location(current_user, db)
        if not user_loc:
            raise HTTPException(status_code=409, detail="Your assigned location no longer exists")
        if driver_data.primary_hub is not None and driver_data.primary_hub != user_loc.id:
            raise HTTPException(status_code=403, detail="You can only register drivers in your assigned location")
        driver_data.primary_hub = user_loc.id
    else:
        user_loc = resolve_user_location(current_user, db)
        if driver_data.primary_hub is None:
            raise HTTPException(status_code=422, detail="primary_hub Location ID is required")
        if user_loc and driver_data.primary_hub != user_loc.id:
            raise HTTPException(status_code=403, detail="Drivers can only be registered in your selected location")

    driver, generated_password = await users_service.create_driver_with_files(
        db=db,
        driver_in=driver_data,
        created_by_user_id=(
            current_user.id if current_user.role == UserRole.STORE_MANAGER else None
        ),
        license_front_copy=license_front_copy,
        license_back_copy=license_back_copy,
        medical_fitness_card=medical_fitness_card,
    )

    if driver.email:
        background_tasks.add_task(
            email_service.send_welcome_credentials_email,
            to_email=driver.email,
            full_name=driver.full_name,
            generated_password=generated_password,
            role=driver.role.value,
        )

    return driver


# =====================================================================
# 3. UNIFIED USERS LISTING WITH ROLE & STATUS FILTERS (Admin Only)
# =====================================================================

@router.get(
    "",
    response_model=dict,
    summary="List all users with Role, Status filters and Search (Admin and Store Manager)"
)
def list_users(
    role: Optional[str] = Query(None, description="Filter by role: all, driver, store-manager, admin"),
    status: Optional[str] = Query(None, description="Filter by status: On Route, Available, Off Duty, or All Statuses"),
    search: Optional[str] = Query(None, description="Search across name, email, phone, employee ID, warehouse, or hub"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.STORE_MANAGER])),
):
    """
    Unified directory endpoint for Admin to view and filter users:
    - Status filters: 'All Statuses', 'On Route', 'Available', 'Off Duty'
    - Role filters: 'all', 'driver', 'store-manager', 'admin'
    - Search: across all main identity fields
    """
    user_loc = resolve_user_location(current_user, db)
    users, total = users_service.list_users(
        db=db,
        skip=skip,
        limit=limit,
        role_filter=role,
        status_filter=status,
        search=search,
        location_id=user_loc.id if user_loc and current_user.role == UserRole.ADMIN else None,
        created_by_user_id=(
            current_user.id if current_user.role == UserRole.STORE_MANAGER else None
        ),
    )
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [UserDetailResponse.model_validate(u) for u in users],
    }


# =====================================================================
# 4. SINGLE USER DETAILS (Admin & Store Manager)
# =====================================================================

@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
    summary="Get user details by ID"
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.STORE_MANAGER])),
):
    """Retrieve full details of a specific user by ID."""
    user_loc = resolve_user_location(current_user, db)
    user = users_service.get_user_by_id(
        db=db,
        user_id=user_id,
        location_id=user_loc.id if user_loc and current_user.role == UserRole.ADMIN else None,
        created_by_user_id=(
            current_user.id if current_user.role == UserRole.STORE_MANAGER else None
        ),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _ensure_user_location(current_user, user, db)
    return user


# =====================================================================
# 5. PATCH DRIVER API (Admin Only)
# =====================================================================

@router.patch(
    "/driver/{user_id}",
    response_model=DriverResponse,
    summary="Partially update driver profile via Form-Data (Admin Only)"
)
async def patch_driver(
    user_id: int,
    driver_update: DriverUpdate = Depends(DriverUpdate.as_form),
    license_front_copy: Optional[UploadFile] = File(None, description="Optional updated front copy of driving license"),
    license_back_copy: Optional[UploadFile] = File(None, description="Optional updated back copy of driving license"),
    medical_fitness_card: Optional[UploadFile] = File(None, description="Optional updated medical fitness certificate/card"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    """Partially update driver fields, documents, shift schedule, or status via Form-Data."""
    driver = db.query(User).filter(User.id == user_id, User.role == UserRole.DRIVER).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    _ensure_user_location(current_user, driver, db)
    user_loc = resolve_user_location(current_user, db)
    if user_loc and driver_update.primary_hub is not None and driver_update.primary_hub != user_loc.id:
        raise HTTPException(status_code=403, detail="Drivers can only be assigned within your selected location")
    return await users_service.patch_driver(
        db=db,
        user_id=user_id,
        driver_update=driver_update,
        license_front_copy=license_front_copy,
        license_back_copy=license_back_copy,
        medical_fitness_card=medical_fitness_card,
    )


# =====================================================================
# 6. PATCH STORE MANAGER API (Admin Only)
# =====================================================================

@router.patch(
    "/store-manager/{user_id}",
    response_model=StoreManagerResponse,
    summary="Partially update store manager profile (Admin Only)"
)
def patch_store_manager(
    user_id: int,
    manager_update: StoreManagerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    """Partially update store manager warehouse, responsibility, status, or contact details."""
    manager = db.query(User).filter(User.id == user_id, User.role == UserRole.STORE_MANAGER).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Store Manager not found")
    _ensure_user_location(current_user, manager, db)
    user_loc = resolve_user_location(current_user, db)
    if user_loc and manager_update.location_id is not None and manager_update.location_id != user_loc.id:
        raise HTTPException(status_code=403, detail="Store managers can only be assigned within your selected location")
    return users_service.patch_store_manager(db=db, user_id=user_id, manager_update=manager_update)


# =====================================================================
# 7. DELETE USER API (Admin Only)
# =====================================================================

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete user by ID (Admin Only)"
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
    """Deletes a user account and associated profile by ID."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own admin account.",
        )
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_location(current_user, target_user, db)
    users_service.delete_user(db=db, user_id=user_id)
    return {
        "status": "success",
        "message": f"User {user_id} successfully deleted.",
        "deleted_user_id": user_id,
    }


def check_user_profile_permission(current_user: User, target_user_id: int, db: Session):
    """Ensures caller is either an Admin or modifying their own profile picture."""
    if current_user.role != UserRole.ADMIN and current_user.id != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are only authorized to modify your own profile picture.",
        )
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_location(current_user, target_user, db)


# =====================================================================
# 8. UPLOAD / UPDATE PROFILE PICTURE API
# =====================================================================


@router.post("/{role}/{user_id}/profile-picture",response_model=ProfilePictureResponse)
async def upload_profile_picture(
    user_id: int,
    role: Optional[str] = None,
    file: UploadFile = File(..., description="Profile picture image file (JPG, JPEG, PNG, WEBP, GIF)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Uploads a new profile picture to Supabase storage and updates the user's profile_photo in database.
    - Role can be specified via path, query parameter, or form-data.
    - Accessible by Admin for any user, or by the user themselves.
    """
    check_user_profile_permission(current_user, user_id, db)

    user = await users_service.update_profile_picture(
        db=db,
        user_id=user_id,
        file=file,
        role=role,
    )
    return ProfilePictureResponse(
        status="success",
        message="Profile picture updated successfully.",
        user_id=user.id,
        role=user.role.value,
        profile_photo=user.profile_photo,
    )


@router.delete("/{role}/{user_id}/profile-picture", response_model=ProfilePictureResponse)
def remove_profile_picture(
    user_id: int,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes the profile picture from Supabase storage and removes it from the user's database record.
    - Role can be specified via path or query parameter.
    - Accessible by Admin for any user, or by the user themselves.
    """
    check_user_profile_permission(current_user, user_id, db)
    user = users_service.remove_profile_picture(
        db=db,
        user_id=user_id,
        role=role,
    )
    return ProfilePictureResponse(
        status="success",
        message="Profile picture removed successfully.",
        user_id=user.id,
        role=user.role.value,
        profile_photo=None,
    )
