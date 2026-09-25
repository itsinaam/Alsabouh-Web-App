from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.models.auth import User
from app.models.run_planner import RunPlanner, RunPlannerStatus
from app.schema.audit import (
    AuditDriver,
    AuditListResponse,
    AuditLocation,
    AuditRunResponse,
    AuditStats,
    AuditVehicle,
)
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(prefix="/audit-details", tags=["Audit Details"])

READ_ROLES = [UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.DRIVER]


def _date_bounds(
    date_range: str,
    from_date: Optional[date],
    to_date: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date cannot be later than to_date")
    selected_range = date_range.strip().lower().replace("-", "_")
    if selected_range not in {"all", "this_week", "this_month"}:
        raise HTTPException(status_code=400, detail="date_range must be all, this_week, or this_month")
    if from_date or to_date:
        return from_date, to_date
    if selected_range == "this_week":
        today = date.today()
        return today - timedelta(days=today.weekday()), today
    if selected_range == "this_month":
        today = date.today()
        return today.replace(day=1), today
    return None, None


def _run_matches_search(run: RunPlanner, search: Optional[str]) -> bool:
    if not search:
        return True
    term = search.strip().lower()
    vehicle = run.commercial_vehicle
    searchable_values = [
        str(run.id),
        vehicle.internal_fleet_code,
        vehicle.make_chassis_model,
        vehicle.commercial_plate_number,
        *(gdn.site_name for gdn in run.gdns),
        *(gdn.gdn_reference for gdn in run.gdns),
    ]
    return any(term in str(value).lower() for value in searchable_values if value)


def _to_audit_response(run: RunPlanner, driver: Optional[User]) -> AuditRunResponse:
    assigned_gdns = list(run.gdns)
    route_sites = list(dict.fromkeys(gdn.site_name for gdn in assigned_gdns if gdn.site_name))
    payload_dispatched = sum(gdn.weight or 0 for gdn in assigned_gdns)
    capacity = run.commercial_vehicle.gross_payload_capacity
    utilization = round(payload_dispatched / capacity * 100, 2) if capacity else None
    is_completed = run.status == RunPlannerStatus.DISPATCHED

    return AuditRunResponse(
        run_id=run.id,
        dispatch_date=run.dispatch_date,
        planned_departure_time=run.planned_departure_time.isoformat(),
        lifecycle_status="Completed & Sealed" if is_completed else run.status.value,
        vehicle=AuditVehicle.model_validate(run.commercial_vehicle),
        driver=AuditDriver.model_validate(driver) if driver else None,
        dispatch_location=AuditLocation.model_validate(run.dispatch_location) if run.dispatch_location else None,
        route_sites=route_sites,
        stops_completed=len(assigned_gdns) if is_completed else 0,
        total_stops=len(assigned_gdns),
        payload_dispatched=payload_dispatched,
        payload_capacity=capacity,
        payload_utilization_percent=utilization,
        assigned_gdns=assigned_gdns,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _load_runs(db: Session) -> list[RunPlanner]:
    return (
        db.query(RunPlanner)
        .options(
            joinedload(RunPlanner.commercial_vehicle),
            joinedload(RunPlanner.dispatch_location),
            selectinload(RunPlanner.gdns),
        )
        .order_by(RunPlanner.dispatch_date.desc(), RunPlanner.planned_departure_time.desc())
        .all()
    )


def _load_drivers(db: Session, runs: list[RunPlanner]) -> dict[int, User]:
    driver_ids = {run.driver_id for run in runs}
    if not driver_ids:
        return {}
    return {driver.id: driver for driver in db.query(User).filter(User.id.in_(driver_ids)).all()}


@router.get("", response_model=AuditListResponse, summary="List run audit details")
def list_audit_details(
    search: Optional[str] = Query(None, description="Search by run ID, vehicle, driver, GDN, or site."),
    status_filter: Optional[str] = Query(None, alias="status", description="all, completed, pending, or a run status."),
    date_range: str = Query("all", description="all, this_week, or this_month."),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    start_date, end_date = _date_bounds(date_range, from_date, to_date)
    runs = _load_runs(db)
    if start_date:
        runs = [run for run in runs if run.dispatch_date >= start_date]
    if end_date:
        runs = [run for run in runs if run.dispatch_date <= end_date]
    if status_filter and status_filter.lower() not in {"all", ""}:
        selected_status = status_filter.strip().lower()
        if selected_status == "completed":
            runs = [run for run in runs if run.status == RunPlannerStatus.DISPATCHED]
        elif selected_status == "pending":
            runs = [run for run in runs if run.status == RunPlannerStatus.READY_TO_DISPATCH]
        else:
            runs = [run for run in runs if run.status.value.lower() == selected_status]
    runs = [run for run in runs if _run_matches_search(run, search)]

    drivers = _load_drivers(db, runs)
    completed_runs = [run for run in runs if run.status == RunPlannerStatus.DISPATCHED]
    total_payload = sum(gdn.weight or 0 for run in completed_runs for gdn in run.gdns)
    items = [_to_audit_response(run, drivers.get(run.driver_id)) for run in runs[skip : skip + limit]]

    return {
        "total": len(runs),
        "skip": skip,
        "limit": limit,
        "stats": AuditStats(
            total_completed_runs=len(completed_runs),
            on_time_delivery_rate=None,
            total_payload_dispatched=total_payload,
            geotagged_pods_verified=0,
        ),
        "items": items,
    }


@router.get("/{run_id}", response_model=AuditRunResponse, summary="Get run audit details")
def get_audit_details(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    run = (
        db.query(RunPlanner)
        .options(
            joinedload(RunPlanner.commercial_vehicle),
            joinedload(RunPlanner.dispatch_location),
            selectinload(RunPlanner.gdns),
        )
        .filter(RunPlanner.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run audit not found")
    driver = db.query(User).filter(User.id == run.driver_id).first()
    return _to_audit_response(run, driver)
