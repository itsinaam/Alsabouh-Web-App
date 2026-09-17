import mimetypes
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.location import Location
from app.models.vehicle import Vehicle
from app.schema.vehicle import VehicleCreate, VehicleListResponse, VehicleResponse, VehicleUpdate
from app.services.storage import storage_service
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(prefix="/vehicle", tags=["Vehicles"])


def _validate_assignments(db: Session, depot_id: Optional[int], driver_id: Optional[int]) -> None:
	if depot_id is not None and not db.query(Location.id).filter(Location.id == depot_id).first():
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned home depot not found")
	if driver_id is not None and not db.query(User.id).filter(
		User.id == driver_id, User.role == UserRole.DRIVER, User.is_active.is_(True)
	).first():
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active driver not found")


async def _upload_documents(files: Optional[List[UploadFile]], vehicle_ref: str) -> List[str]:
	urls: List[str] = []
	for upload in files or []:
		if not upload.filename:
			continue
		content = await upload.read()
		extension = upload.filename.rsplit(".", 1)[-1] if "." in upload.filename else "bin"
		path = f"vehicles/{vehicle_ref}/mulkiya/{uuid.uuid4().hex}.{extension}"
		content_type = upload.content_type or mimetypes.guess_type(upload.filename)[0]
		urls.append(storage_service.upload_file(content, path, content_type))
	return urls


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED, summary="Create vehicle")
async def create_vehicle(
	vehicle_in: VehicleCreate = Depends(VehicleCreate.as_form),
	mulkiya_inspection_documents: Optional[List[UploadFile]] = File(None),
	db: Session = Depends(get_db),
	current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
	_validate_assignments(db, vehicle_in.assigned_home_depot, vehicle_in.designated_primary_driver)
	vehicle = Vehicle(**vehicle_in.model_dump())
	db.add(vehicle)
	try:
		db.flush()
		vehicle.mulkiya_inspection_document = await _upload_documents(mulkiya_inspection_documents, str(vehicle.id))
		db.commit()
		db.refresh(vehicle)
		return vehicle
	except IntegrityError:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Fleet code or commercial plate already exists")


@router.get(
	"",
	response_model=VehicleListResponse,
	summary="List vehicles",
	description=(
		"List vehicles with pagination, search, vehicle type, and status filters. "
		"Examples: `?vehicle_type=10-Ton%20Flatbed%20Truck`, "
		"`?status=Maintenance`, or combine both filters."
	),
)
def list_vehicles(
	search: Optional[str] = Query(None, description="Search by fleet code, vehicle model, or plate number."),
	vehicle_type: Optional[str] = Query(
		None,
		description="Filter by truck type, for example `10-Ton Flatbed Truck`.",
	),
	status_filter: Optional[str] = Query(
		None,
		alias="status",
		description="Filter by status, for example `Available`, `In Use`, or `Maintenance`.",
	),
	skip: int = Query(0, ge=0, description="Number of records to skip."),
	limit: int = Query(50, ge=1, le=200, description="Number of records to return (maximum 200)."),
	db: Session = Depends(get_db),
	current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.DRIVER])),
):
	all_vehicles = db.query(Vehicle)
	counts = {
		"total": all_vehicles.count(),
		"assigned": all_vehicles.filter(
			or_(Vehicle.assigned_home_depot.is_not(None), Vehicle.designated_primary_driver.is_not(None))
		).count(),
		"unassigned": all_vehicles.filter(
			Vehicle.assigned_home_depot.is_(None), Vehicle.designated_primary_driver.is_(None)
		).count(),
		"under_maintenance": all_vehicles.filter(Vehicle.status.ilike("%maintenance%")).count(),
	}

	query = db.query(Vehicle)
	if search:
		term = f"%{search.strip()}%"
		query = query.filter(
			Vehicle.internal_fleet_code.ilike(term)
			| Vehicle.make_chassis_model.ilike(term)
			| Vehicle.commercial_plate_number.ilike(term)
		)
	if vehicle_type and vehicle_type.lower() != "all":
		query = query.filter(Vehicle.truck_type_asset_category.ilike(vehicle_type.strip()))
	if status_filter and status_filter.lower() != "all":
		query = query.filter(Vehicle.status.ilike(status_filter.strip()))
	total = query.count()
	items = query.order_by(Vehicle.id.desc()).offset(skip).limit(limit).all()
	return {"total": total, "skip": skip, "limit": limit, "counts": counts, "items": items}


@router.get("/{vehicle_id}", response_model=VehicleResponse, summary="Get vehicle")
def get_vehicle(
	vehicle_id: int,
	db: Session = Depends(get_db),
	current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.STORE_MANAGER, UserRole.DRIVER])),
):
	vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
	if not vehicle:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
	return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleResponse, summary="Update vehicle")
async def update_vehicle(
	vehicle_id: int,
	vehicle_in: VehicleUpdate = Depends(VehicleUpdate.as_form),
	mulkiya_inspection_documents: Optional[List[UploadFile]] = File(None),
	db: Session = Depends(get_db),
	current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
	vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
	if not vehicle:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
	data = vehicle_in.model_dump(exclude_unset=True)
	_validate_assignments(
		db,
		data.get("assigned_home_depot", vehicle.assigned_home_depot),
		data.get("designated_primary_driver", vehicle.designated_primary_driver),
	)
	for key, value in data.items():
		setattr(vehicle, key, value)
	if mulkiya_inspection_documents:
		vehicle.mulkiya_inspection_document = await _upload_documents(mulkiya_inspection_documents, str(vehicle.id))
	try:
		db.commit()
		db.refresh(vehicle)
		return vehicle
	except IntegrityError:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Fleet code or commercial plate already exists")


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete vehicle")
def delete_vehicle(
	vehicle_id: int,
	db: Session = Depends(get_db),
	current_user: User = Depends(require_roles([UserRole.ADMIN])),
):
	vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
	if not vehicle:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
	db.delete(vehicle)
	db.commit()
