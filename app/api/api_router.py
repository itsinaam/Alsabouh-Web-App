from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.users import router as drivers_router


api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(drivers_router)

