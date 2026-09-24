from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.gdn import router as gdn_router
from app.api.location import router as location_router
from app.api.run_planner import router as run_planner_router
from app.api.users import router as drivers_router
from app.api.vehicle import router as vehicle_router


api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(drivers_router)
api_router.include_router(location_router)
api_router.include_router(vehicle_router)
api_router.include_router(gdn_router)
api_router.include_router(run_planner_router)


