from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.auth import User
from app.schema.auth import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import auth_service
from app.utils.security import get_current_user

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

