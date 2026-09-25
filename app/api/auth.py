from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.db.session import get_db
from app.models.auth import User
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


@router.get("/me", response_model=UserResponse, summary="Get current logged in user details")
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user's profile and active role."""
    return current_user


@router.patch("/me", response_model=UserResponse, summary="Update current user profile")
def update_current_user_profile(
    profile_in: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not profile_in.model_dump(exclude_unset=True):
        raise HTTPException(status_code=422, detail="At least one profile field is required")
    if profile_in.phone_number is not None:
        existing_user = db.query(User).filter(
            User.phone_number == profile_in.phone_number,
            User.id != current_user.id,
        ).first()
        if existing_user:
            raise HTTPException(status_code=409, detail="Phone number is already in use")

    for field, value in profile_in.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
        db.refresh(current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Phone number is already in use")
    return current_user


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

