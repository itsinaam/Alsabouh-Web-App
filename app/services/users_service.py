import secrets
import string
import uuid
from typing import List, Optional, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.auth import User
from app.schema.users import (
    DriverRegisterRequest,
    DriverUpdate,
    StoreManagerRegisterRequest,
    StoreManagerUpdate,
)
from app.services.auth_service import auth_service
from app.services.storage import storage_service
from app.utils.constants import UserRole


def generate_driver_password() -> str:
    """Generates a secure, readable temporary password for new users."""
    chars = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(6))
    return f"Alsabouh@{random_part}"


def parse_user_role(role_input: Optional[str], default_role: UserRole = UserRole.DRIVER) -> UserRole:
    """Safely maps arbitrary role strings to valid UserRole enums."""
    if not role_input:
        return default_role
    clean = str(role_input).upper().replace("-", "_").replace(" ", "_")
    if "DRIVER" in clean:
        return UserRole.DRIVER
    if "STORE" in clean:
        return UserRole.STORE_MANAGER
    if "ADMIN" in clean:
        return UserRole.ADMIN
    try:
        return UserRole[clean]
    except KeyError:
        return default_role


class UsersService:
    """Consolidated business logic for Drivers, Store Managers, and General User operations."""

    # =========================================================================
    # DRIVER OPERATIONS
    # =========================================================================

    @staticmethod
    async def create_driver_with_files(
        db: Session,
        driver_in: DriverRegisterRequest,
        license_front_copy: Optional[UploadFile] = None,
        license_back_copy: Optional[UploadFile] = None,
        medical_fitness_card: Optional[UploadFile] = None,
    ) -> Tuple[User, str]:
        """
        Creates a new driver record in User table.
        Auto-generates a secure password and employee ID, uploads documents to Supabase storage,
        and returns (driver_user, plain_generated_password).
        """
        # 1. Duplicate checks
        conditions = [
            User.email == driver_in.email,
            User.phone_number == driver_in.phone_number,
        ]
        if driver_in.emirates_id:
            conditions.append(User.emirates_id == driver_in.emirates_id)
        if driver_in.licence_number:
            conditions.append(User.licence_number == driver_in.licence_number)

        existing = db.query(User).filter(or_(*conditions)).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this Email, Phone Number, Emirates ID, or License Number already exists.",
            )

        # 2. Auto-generate password and employee ID
        generated_password = generate_driver_password()
        hashed_password = auth_service.hash_password(generated_password)
        auto_employee_id = f"DRV-{uuid.uuid4().hex[:6].upper()}"
        assigned_role = parse_user_role(driver_in.role, default_role=UserRole.DRIVER)

        # 3. Create User record
        driver_user = User(
            full_name=driver_in.full_name,
            employee_id=auto_employee_id,
            email=driver_in.email,
            phone_number=driver_in.phone_number,
            hashed_password=hashed_password,
            role=assigned_role,
            is_active=True,
            emirates_id=driver_in.emirates_id,
            nationality=driver_in.nationality,
            alternate_emergency_contact=driver_in.alternate_emergency_contact,
            licence_number=driver_in.licence_number,
            rta_permit_number=driver_in.rta_permit_number,
            licence_category=driver_in.licence_category,
            licence_expiry_date=driver_in.licence_expiry_date,
            issuing_authority=driver_in.issuing_authority,
            medical_fitness=driver_in.medical_fitness,
            primary_hub=driver_in.primary_hub,
            shift_schedule=driver_in.shift_schedule,
            initial_vehicle_assignment=driver_in.initial_vehicle_assignment,
            active_duty=driver_in.active_duty,
            status=driver_in.status or "Available",
        )
        db.add(driver_user)
        db.flush()  # Populates driver_user.id

        # 4. Upload document files to Supabase Storage and assign public URLs
        driver_ref = str(driver_user.id)

        if license_front_copy and license_front_copy.filename:
            content = await license_front_copy.read()
            driver_user.license_front_copy = storage_service.upload_driver_document(
                file_bytes=content,
                original_filename=license_front_copy.filename,
                category="license_front",
                driver_id_or_ref=driver_ref,
            )

        if license_back_copy and license_back_copy.filename:
            content = await license_back_copy.read()
            driver_user.license_back_copy = storage_service.upload_driver_document(
                file_bytes=content,
                original_filename=license_back_copy.filename,
                category="license_back",
                driver_id_or_ref=driver_ref,
            )

        if medical_fitness_card and medical_fitness_card.filename:
            content = await medical_fitness_card.read()
            driver_user.medical_fitness_card = storage_service.upload_driver_document(
                file_bytes=content,
                original_filename=medical_fitness_card.filename,
                category="medical_cards",
                driver_id_or_ref=driver_ref,
            )

        db.commit()
        db.refresh(driver_user)
        return driver_user, generated_password

    @staticmethod
    async def patch_driver(
        db: Session,
        user_id: int,
        driver_update: DriverUpdate,
        license_front_copy: Optional[UploadFile] = None,
        license_back_copy: Optional[UploadFile] = None,
        medical_fitness_card: Optional[UploadFile] = None,
    ) -> User:
        """Partially update driver profile attributes and documents via Form-Data."""
        driver = db.query(User).filter(User.id == user_id).first()
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

        update_data = {k: v for k, v in driver_update.model_dump().items() if v is not None}
        if "role" in update_data and update_data["role"]:
            update_data["role"] = parse_user_role(update_data["role"], default_role=driver.role)

        for key, value in update_data.items():
            setattr(driver, key, value)

        # Upload replacement documents if provided
        driver_ref = str(driver.id)

        if license_front_copy and license_front_copy.filename:
            content = await license_front_copy.read()
            driver.license_front_copy = storage_service.upload_driver_document(
                file_bytes=content,
                original_filename=license_front_copy.filename,
                category="license_front",
                driver_id_or_ref=driver_ref,
            )

        if license_back_copy and license_back_copy.filename:
            content = await license_back_copy.read()
            driver.license_back_copy = storage_service.upload_driver_document(
                file_bytes=content,
                original_filename=license_back_copy.filename,
                category="license_back",
                driver_id_or_ref=driver_ref,
            )

        if medical_fitness_card and medical_fitness_card.filename:
            content = await medical_fitness_card.read()
            driver.medical_fitness_card = storage_service.upload_driver_document(
                file_bytes=content,
                original_filename=medical_fitness_card.filename,
                category="medical_cards",
                driver_id_or_ref=driver_ref,
            )

        db.commit()
        db.refresh(driver)
        return driver

    # =========================================================================
    # STORE MANAGER OPERATIONS
    # =========================================================================

    @staticmethod
    def create_store_manager(
        db: Session,
        manager_in: StoreManagerRegisterRequest,
    ) -> Tuple[User, str]:
        """
        Registers a new Store & Warehouse Manager, auto-generates a secure password,
        and returns (manager_user, generated_password).
        """
        # 1. Duplicate checks
        conditions = [
            User.email == manager_in.email,
            User.phone_number == manager_in.phone_number,
        ]
        if manager_in.employee_id:
            conditions.append(User.employee_id == manager_in.employee_id)

        existing = db.query(User).filter(or_(*conditions)).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this Email, Phone Number, or Employee ID already exists.",
            )

        # 2. Auto-generate password
        generated_password = generate_driver_password()
        hashed_password = auth_service.hash_password(generated_password)
        assigned_role = parse_user_role(manager_in.role, default_role=UserRole.STORE_MANAGER)

        # 3. Status to is_active mapping
        is_active = True
        if manager_in.status and manager_in.status.lower() in ["inactive", "suspended", "disabled", "off duty"]:
            is_active = False

        # 4. Create User record
        manager_user = User(
            full_name=manager_in.full_name,
            employee_id=manager_in.employee_id or f"STM-{uuid.uuid4().hex[:4].upper()}",
            email=manager_in.email,
            phone_number=manager_in.phone_number,
            hashed_password=hashed_password,
            role=assigned_role,
            is_active=is_active,
            assigned_warehouse=manager_in.assigned_warehouse,
            responsibility=manager_in.responsibility,
            status=manager_in.status or "Available",
        )
        db.add(manager_user)
        db.commit()
        db.refresh(manager_user)
        return manager_user, generated_password

    @staticmethod
    def patch_store_manager(db: Session, user_id: int, manager_update: StoreManagerUpdate) -> User:
        """Partially update store manager profile attributes."""
        manager = db.query(User).filter(User.id == user_id).first()
        if not manager:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store Manager not found")

        update_data = manager_update.model_dump(exclude_unset=True)
        if "role" in update_data and update_data["role"]:
            update_data["role"] = parse_user_role(update_data["role"], default_role=manager.role)

        for key, value in update_data.items():
            setattr(manager, key, value)

        db.commit()
        db.refresh(manager)
        return manager

    # =========================================================================
    # UNIFIED USER OPERATIONS (List with Filters, Search, Delete)
    # =========================================================================

    @staticmethod
    def list_users(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        role_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        """
        Unified listing of users supporting:
        - Role filter: 'all', 'driver', 'store-manager'/'store_manager', 'admin'
        - Status filter: 'On Route', 'Available', 'Off Duty', or any status string
        - Search query across name, email, phone, employee_id, etc.
        """
        query = db.query(User)

        # Role filtering
        if role_filter and role_filter.lower() not in ["all", "all roles", ""]:
            role_clean = role_filter.lower().strip().replace("-", "_").replace(" ", "_")
            if "driver" in role_clean:
                query = query.filter(User.role == UserRole.DRIVER)
            elif "store" in role_clean:
                query = query.filter(User.role == UserRole.STORE_MANAGER)
            elif "admin" in role_clean:
                query = query.filter(User.role == UserRole.ADMIN)

        # Status filtering
        if status_filter and status_filter.lower() not in ["all", "all statuses", ""]:
            query = query.filter(User.status.ilike(f"%{status_filter.strip()}%"))

        # Search query
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.phone_number.ilike(pattern),
                    User.employee_id.ilike(pattern),
                    User.emirates_id.ilike(pattern),
                    User.licence_number.ilike(pattern),
                    User.assigned_warehouse.ilike(pattern),
                    User.primary_hub.ilike(pattern),
                    User.responsibility.ilike(pattern),
                )
            )

        total = query.count()
        users = query.order_by(User.id.desc()).offset(skip).limit(limit).all()
        return users, total

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def delete_user(db: Session, user_id: int) -> User:
        """Deletes user by user ID."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        db.delete(user)
        db.commit()
        return user

    @staticmethod
    async def update_profile_picture(
        db: Session,
        user_id: int,
        file: UploadFile,
        role: Optional[str] = None,
    ) -> User:
        """
        Uploads an image file to Supabase storage and updates user's profile_photo column.
        Optionally verifies that the user matches the requested role.
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found")

        if role:
            expected_role = parse_user_role(role)
            if user.role != expected_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User {user_id} role mismatch. Expected '{role}', but user role is '{user.role.value}'."
                )

        if not file or not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No profile picture file provided.")

        # Validate image format
        valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid image format '{file_ext}'. Allowed formats: JPG, JPEG, PNG, WEBP, GIF."
            )

        # Remove old profile picture from Supabase if exists
        if user.profile_photo:
            storage_service.delete_file_by_url(user.profile_photo)

        # Upload new file to Supabase Storage
        file_bytes = await file.read()
        public_url = storage_service.upload_profile_picture(
            file_bytes=file_bytes,
            original_filename=file.filename,
            role=user.role.value,
            user_id=user.id,
        )

        user.profile_photo = public_url
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def remove_profile_picture(
        db: Session,
        user_id: int,
        role: Optional[str] = None,
    ) -> User:
        """
        Deletes the user's profile picture file from Supabase storage and clears the profile_photo column in DB.
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found")

        if role:
            expected_role = parse_user_role(role)
            if user.role != expected_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User {user_id} role mismatch. Expected '{role}', but user role is '{user.role.value}'."
                )

        if user.profile_photo:
            storage_service.delete_file_by_url(user.profile_photo)
            user.profile_photo = None
            db.commit()
            db.refresh(user)

        return user


users_service = UsersService()
driver_service = users_service
DriverService = UsersService
