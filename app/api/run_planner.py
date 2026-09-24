from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.auth import User
from app.models.gdn import GDN
from app.models.location import Location
from app.models.run_planner import RunPlanner, RunPlannerStatus
from app.models.vehicle import Vehicle
from app.schema.run_planner import (
    RunPlannerCreate,
    RunPlannerListResponse,
    RunPlannerResponse,
    RunPlannerStats,
    RunPlannerUpdate,
)
from app.schema.gdn import GDNResponse
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(prefix="/run-planner", tags=["Run Planner"])

MANAGER_ROLES = [UserRole.ADMIN, UserRole.STORE_MANAGER]
READ_ROLES = [UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.DRIVER]


def _validate_assignments(
    db: Session,
    commercial_vehicle_id: int,
    dispatch_location_id: int,
    driver_id: int,
) -> None:
    if not db.query(Vehicle.id).filter(Vehicle.id == commercial_vehicle_id).first():
        raise HTTPException(status_code=400, detail="Commercial vehicle not found")
    if not db.query(Location.id).filter(Location.id == dispatch_location_id).first():
        raise HTTPException(status_code=400, detail="Dispatch location not found")
    if not db.query(User.id).filter(
        User.id == driver_id, User.role == UserRole.DRIVER, User.is_active.is_(True)
    ).first():
        raise HTTPException(status_code=400, detail="Active driver not found")


@router.post(
    "",
    response_model=RunPlannerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a run plan",
)
def create_run_plan(
    run_in: RunPlannerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(MANAGER_ROLES)),
):
    _validate_assignments(db, **run_in.model_dump(exclude={"dispatch_date", "planned_departure_time", "status"}))
    run_plan = RunPlanner(**run_in.model_dump())
    db.add(run_plan)
    db.commit()
    db.refresh(run_plan)
    return run_plan


@router.get("", response_model=RunPlannerListResponse, summary="List run plans")
def list_run_plans(
    status_filter: Optional[str] = Query(None, alias="status"),
    dispatch_date: Optional[date] = Query(None, description="Filter by dispatch date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    query = db.query(RunPlanner).options(
        selectinload(RunPlanner.commercial_vehicle),
        selectinload(RunPlanner.gdns),
    )
    if status_filter:
        query = query.filter(RunPlanner.status == status_filter)
    if dispatch_date:
        query = query.filter(RunPlanner.dispatch_date == dispatch_date)
    total = query.count()
    items = query.order_by(RunPlanner.dispatch_date, RunPlanner.planned_departure_time).offset(skip).limit(limit).all()
    today = date.today()
    stats = RunPlannerStats(
        active_runs=db.query(RunPlanner.id).count(),
        on_route=db.query(RunPlanner.id).filter(RunPlanner.status == RunPlannerStatus.DISPATCHED).count(),
        awaiting_dispatch=db.query(RunPlanner.id).filter(
            RunPlanner.status == RunPlannerStatus.READY_TO_DISPATCH
        ).count(),
        completed_today=db.query(RunPlanner.id).filter(
            RunPlanner.status == RunPlannerStatus.DISPATCHED,
            RunPlanner.dispatch_date == today,
        ).count(),
    )
    return {"total": total, "skip": skip, "limit": limit, "stats": stats, "items": items}


@router.post(
    "/{run_plan_id}/gdns/{gdn_id}",
    response_model=GDNResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign a GDN to a run plan",
)
def assign_gdn(
    run_plan_id: int,
    gdn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(MANAGER_ROLES)),
):
    run_plan = db.query(RunPlanner).filter(RunPlanner.id == run_plan_id).first()
    if not run_plan:
        raise HTTPException(status_code=404, detail="Run plan not found")
    gdn = db.query(GDN).filter(GDN.id == gdn_id).first()
    if not gdn:
        raise HTTPException(status_code=404, detail="GDN not found")
    if gdn.run_planner_id:
        raise HTTPException(status_code=409, detail="GDN is already assigned to a run plan")

    vehicle = db.query(Vehicle).filter(Vehicle.id == run_plan.commercial_vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=400, detail="Commercial vehicle not found")
    if vehicle.gross_payload_capacity is None:
        raise HTTPException(status_code=400, detail="Vehicle payload capacity is not configured")

    current_weight = db.query(func.coalesce(func.sum(GDN.weight), 0)).filter(
        GDN.run_planner_id == run_plan_id
    ).scalar() or 0
    requested_weight = gdn.weight or 0
    total_weight = current_weight + requested_weight
    if total_weight > vehicle.gross_payload_capacity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"GDN weight exceeds vehicle capacity: assigned {current_weight}, "
                f"requested {requested_weight}, capacity {vehicle.gross_payload_capacity}"
            ),
        )

    gdn.assign = True
    gdn.run_planner_id = run_plan_id
    db.commit()
    db.refresh(gdn)
    return gdn


@router.delete(
    "/gdns/{gdn_id}",
    response_model=GDNResponse,
    summary="Unassign a GDN",
)
def remove_gdn(
    gdn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(MANAGER_ROLES)),
):
    gdn = db.query(GDN).filter(GDN.id == gdn_id).first()
    if not gdn:
        raise HTTPException(status_code=404, detail="GDN not found")
    gdn.assign = False
    gdn.run_planner_id = None
    db.commit()
    db.refresh(gdn)
    return gdn


@router.get("/{run_plan_id}", response_model=RunPlannerResponse, summary="Get a run plan")
def get_run_plan(
    run_plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    run_plan = db.query(RunPlanner).filter(RunPlanner.id == run_plan_id).first()
    if not run_plan:
        raise HTTPException(status_code=404, detail="Run plan not found")
    return run_plan


@router.patch("/{run_plan_id}", response_model=RunPlannerResponse, summary="Update a run plan")
def update_run_plan(
    run_plan_id: int,
    run_in: RunPlannerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(MANAGER_ROLES)),
):
    run_plan = db.query(RunPlanner).filter(RunPlanner.id == run_plan_id).first()
    if not run_plan:
        raise HTTPException(status_code=404, detail="Run plan not found")

    data = run_in.model_dump(exclude_unset=True)
    _validate_assignments(
        db,
        data.get("commercial_vehicle_id", run_plan.commercial_vehicle_id),
        data.get("dispatch_location_id", run_plan.dispatch_location_id),
        data.get("driver_id", run_plan.driver_id),
    )
    for key, value in data.items():
        setattr(run_plan, key, value)
    db.commit()
    db.refresh(run_plan)
    return run_plan


@router.delete("/{run_plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a run plan")
def delete_run_plan(
    run_plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(MANAGER_ROLES)),
):
    run_plan = db.query(RunPlanner).filter(RunPlanner.id == run_plan_id).first()
    if not run_plan:
        raise HTTPException(status_code=404, detail="Run plan not found")
    db.delete(run_plan)
    db.commit()