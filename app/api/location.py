from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.location import Hub
from app.schema.location import (
    HubCreate,
    HubDropdownResponse,
    HubListResponse,
    HubResponse,
    HubUpdate,
)
from app.utils.constants import UserRole
from app.utils.security import get_current_user, require_roles

router = APIRouter(prefix="/location", tags=["Location"])


@router.post("",response_model=HubResponse,status_code=status.HTTP_201_CREATED,summary="Create a new Location / Hub (Admin & Store Manager)")
def create_hub(
    hub_in: HubCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.STORE_MANAGER])),
):
    """
    Creates a new operational Hub / Location.
    Requires ADMIN or STORE_MANAGER role.
    """
    hub = Hub(**hub_in.model_dump())
    db.add(hub)
    db.commit()
    db.refresh(hub)
    return hub

@router.get("",response_model=HubListResponse,summary="List Locations with search, filters, pagination, and KPI metrics")
def list_hubs(
    search: Optional[str] = Query(None, description="Search across name, emirate, address, plot, or notes"),
    emirate: Optional[str] = Query(None, description="Filter by emirate jurisdiction"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by hub status (e.g. Active, Inactive, Draft)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max number of records to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists all Hubs / Locations with optional search, filtering, and system-wide KPI summary metrics.
    Accessible to all authenticated users (Admin, Store Manager, Driver).
    """
    query = db.query(Hub)

    if emirate:
        query = query.filter(Hub.emirate_jurisdiction.ilike(f"%{emirate.strip()}%"))

    if status_filter:
        query = query.filter(Hub.status.ilike(f"%{status_filter.strip()}%"))

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Hub.hub_name.ilike(term),
                Hub.emirate_jurisdiction.ilike(term),
                Hub.hub_classification.ilike(term),
                Hub.street_address.ilike(term),
                Hub.industrial_plot.ilike(term),
                Hub.infrastructure_notes.ilike(term),
                Hub.direct_contact_phone.ilike(term),
            )
        )

    total = query.count()
    items = query.order_by(Hub.id.desc()).offset(skip).limit(limit).all()

    # System-wide KPI metrics for UI cards
    total_registered = db.query(Hub).count()
    total_active = db.query(Hub).filter(Hub.status.ilike("active")).count()
    total_draft = db.query(Hub).filter(Hub.status.ilike("draft")).count()

    assigned_drivers_count = db.query(User).filter(
        User.role == UserRole.DRIVER,
        User.initial_vehicle_assignment.isnot(None),
        User.initial_vehicle_assignment != "",
    ).count()
    assigned_fleet_units = assigned_drivers_count 
    dispatched_volume = 0

    return {
        "total": total,
        "total_registered": total_registered,
        "total_active": total_active,
        "total_draft": total_draft,
        "active_hubs": total_active,
        "draft_hubs": total_draft,
        "assigned_fleet_units": assigned_fleet_units,
        "today_dispatched_volume": dispatched_volume,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.patch("/{id}",response_model=HubResponse,summary="Update a Location (Admin Only)")
def patch_hub(id: int, hub_in: HubUpdate,db: Session = Depends(get_db), current_user: User = Depends(require_roles([UserRole.ADMIN]))):
    """Partially updates specified fields of an existing Hub."""
    hub = db.query(Hub).filter(Hub.id == id).first()
    if not hub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub with ID {id} not found",
        )

    update_data = hub_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(hub, key, value)

    db.commit()
    db.refresh(hub)
    return hub

@router.delete("/{id}",status_code=status.HTTP_200_OK, summary="Delete a Location (Admin Only)")
def delete_hub(id: int,db: Session = Depends(get_db),current_user: User = Depends(require_roles([UserRole.ADMIN]))):
    """Deletes a Hub by ID. Restricted to Admin."""
    hub = db.query(Hub).filter(Hub.id == id).first()
    if not hub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub with ID {id} not found",
        )

    db.delete(hub)
    db.commit()
    return {
        "status": "success",
        "message": f"Location {id} successfully deleted",
        "deleted_id": id,
    }
