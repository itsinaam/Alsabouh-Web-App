from datetime import date, datetime, timedelta
import csv
import io
import json
import mimetypes
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from app.db.session import get_db
from app.models.auth import User
from app.models.gdn import GDN
from app.schema.gdn import GDNCreate, GDNListResponse, GDNResponse, GDNStats, GDNUpdate
from app.services.storage import storage_service
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(prefix="/gdn", tags=["Invoice & GDN"])

GDN_ROLES = [UserRole.STORE_MANAGER]
geolocator = Nominatim(user_agent="alsabouh_web_app_gdn")


def _geocode_site(site_name: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    if not site_name or not site_name.strip():
        return None, None
    try:
        location = geolocator.geocode(site_name.strip(), timeout=5)
    except (GeocoderServiceError, GeocoderTimedOut, OSError):
        return None, None
    if not location:
        return None, None
    return float(location.latitude), float(location.longitude)


def _commit_gdn(db: Session, gdn: GDN, duplicate_message: str = "GDN reference already exists") -> GDN:
    try:
        db.commit()
        db.refresh(gdn)
        return gdn
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_message)


async def _upload_image_groups(
    image_groups_json: Optional[str],
    images: Optional[list[UploadFile]],
    gdn_reference: Optional[str],
) -> list[dict[str, object]]:
    if not image_groups_json:
        return []
    try:
        groups = json.loads(image_groups_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="image_groups must be valid JSON") from exc
    if not isinstance(groups, list):
        raise HTTPException(status_code=422, detail="image_groups must be a JSON array")

    files_by_name: dict[str, list[UploadFile]] = {}
    for upload in images or []:
        if upload.filename:
            files_by_name.setdefault(upload.filename, []).append(upload)

    result = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("title"), str):
            raise HTTPException(status_code=422, detail="Each image group needs a title")
        file_names = group.get("images")
        if not isinstance(file_names, list):
            raise HTTPException(status_code=422, detail="Each image group needs an images array")

        urls = []
        for file_name in file_names:
            if not isinstance(file_name, str) or not files_by_name.get(file_name):
                raise HTTPException(status_code=422, detail=f"Uploaded image not found: {file_name}")
            upload = files_by_name[file_name].pop(0)
            if upload.content_type and not upload.content_type.startswith("image/"):
                raise HTTPException(status_code=422, detail=f"File is not an image: {file_name}")
            extension = file_name.rsplit(".", 1)[-1] if "." in file_name else "bin"
            path = f"gdns/{gdn_reference or 'unreferenced'}/images/{uuid.uuid4().hex}.{extension}"
            content_type = upload.content_type or mimetypes.guess_type(file_name)[0]
            urls.append(storage_service.upload_file(await upload.read(), path, content_type))
        result.append({"title": group["title"].strip(), "images": urls})

    return result


def _filtered_gdn_query(
    db: Session,
    search: Optional[str],
    payment_status: Optional[str],
    status_filter: Optional[str],
    assign: Optional[bool],
    date_range: Optional[str],
    from_date: Optional[date],
    to_date: Optional[date],
):
    query = db.query(GDN)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            GDN.gdn_reference.ilike(term)
            | GDN.customer_name.ilike(term)
            | GDN.site_name.ilike(term)
        )
    if payment_status and payment_status.lower() != "all":
        query = query.filter(GDN.payment_status.ilike(payment_status.strip()))
    if status_filter and status_filter.lower() != "all":
        query = query.filter(GDN.status.ilike(status_filter.strip()))
    if assign is not None:
        query = query.filter(GDN.assign.is_(assign))

    selected_range = (date_range or "all").strip().lower().replace("-", "_")
    if selected_range not in {"all", "this_week", "this_month"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_range must be all, this_week, or this_month",
        )
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be later than to_date",
        )

    range_start = from_date
    range_end = to_date
    today = date.today()
    if not from_date and not to_date:
        if selected_range == "this_week":
            range_start = today - timedelta(days=today.weekday())
            range_end = today
        elif selected_range == "this_month":
            range_start = today.replace(day=1)
            range_end = today
    if range_start:
        query = query.filter(GDN.invoice_date >= range_start)
    if range_end:
        query = query.filter(GDN.invoice_date <= range_end)
    return query


def _build_gdn_stats(query) -> GDNStats:
    records = query.all()
    return GDNStats(
        total_invoices=len(records),
        gdns_created=len(records),
        pending_invoices=sum(1 for gdn in records if (gdn.payment_status or "").lower() == "pending"),
        delivered_gdns=sum(1 for gdn in records if (gdn.status or "").lower() == "delivered"),
        loaded_gdns=sum(1 for gdn in records if (gdn.status or "").lower() == "gdn loaded"),
    )


@router.post(
    "",
    response_model=GDNResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goods delivery note with grouped images",
)
async def create_gdn(
    customer_name: Optional[str] = Form(None),
    site_name: Optional[str] = Form(None),
    materials_description_summary: Optional[str] = Form(None),
    invoice_date: Optional[date] = Form(None),
    line_items: Optional[str] = Form(None, description="JSON array of line items."),
    payment_status: str = Form("Pending"),
    status_value: Optional[str] = Form("Pending", alias="status"),
    weight: Optional[int] = Form(None, ge=0),
    gdn_reference: Optional[str] = Form(None),
    loaded_at: Optional[datetime] = Form(None),
    loading_dock: Optional[str] = Form(None),
    pallets_count: Optional[int] = Form(None, ge=0),
    transporter_name: Optional[str] = Form(None),
    image_groups: Optional[str] = Form(
        None,
        description='JSON array: [{"title":"Loading Dock Photos","images":["dock_1.jpg"]}]',
    ),
    images: Optional[list[UploadFile]] = File(
        None,
        description="Multiple image files referenced by filename in image_groups.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    try:
        gdn_in = GDNCreate.model_validate({
            "customer_name": customer_name,
            "site_name": site_name,
            "materials_description_summary": materials_description_summary,
            "invoice_date": invoice_date,
            "line_items": json.loads(line_items) if line_items else None,
            "payment_status": payment_status,
            "status": status_value,
            "weight": weight,
            "gdn_reference": gdn_reference,
            "loaded_at": loaded_at,
            "loading_dock": loading_dock,
            "pallets_count": pallets_count,
            "transporter_name": transporter_name,
        })
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="line_items must be valid JSON and all fields must be valid") from exc
    uploaded_groups = await _upload_image_groups(image_groups, images, gdn_in.gdn_reference)
    latitude, longitude = await run_in_threadpool(_geocode_site, gdn_in.site_name)
    gdn = GDN(
        **gdn_in.model_dump(exclude={"image_groups"}),
        image_groups=uploaded_groups,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(gdn)
    return _commit_gdn(db, gdn)


@router.get(
    "",
    response_model=GDNListResponse,
    summary="List goods delivery notes",
)
def list_gdns(
    search: Optional[str] = Query(None, description="Search by GDN reference, customer, or site."),
    payment_status: Optional[str] = Query(None, description="Filter by payment status."),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by operational status, for example Pending, Delivered, or GDN Loaded.",
    ),
    assign: Optional[bool] = Query(None, description="Filter by assignment state: true or false."),
    date_range: Optional[str] = Query(
        "all",
        description="Date preset for invoice_date: all, this_week, or this_month.",
    ),
    from_date: Optional[date] = Query(
        None,
        description="Custom inclusive start date. Use with to_date, format YYYY-MM-DD.",
    ),
    to_date: Optional[date] = Query(
        None,
        description="Custom inclusive end date. Use with from_date, format YYYY-MM-DD.",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    query = _filtered_gdn_query(
        db, search, payment_status, status_filter, assign, date_range, from_date, to_date
    )

    total = query.count()
    items = query.order_by(GDN.id.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "stats": _build_gdn_stats(query),
        "items": items,
    }


@router.get(
    "/export",
    summary="Export filtered goods delivery notes as CSV",
    response_class=Response,
)
def export_gdns(
    search: Optional[str] = Query(None, description="Search by GDN reference, customer, or site."),
    payment_status: Optional[str] = Query(None, description="Filter by payment status."),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by GDN status."),
    assign: Optional[bool] = Query(None, description="Filter by assignment state: true or false."),
    date_range: Optional[str] = Query("all", description="all, this_week, or this_month."),
    from_date: Optional[date] = Query(None, description="Custom start date, YYYY-MM-DD."),
    to_date: Optional[date] = Query(None, description="Custom end date, YYYY-MM-DD."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    query = _filtered_gdn_query(
        db, search, payment_status, status_filter, assign, date_range, from_date, to_date
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "id", "gdn_reference", "customer_name", "site_name",
        "materials_description_summary", "invoice_date", "payment_status", "status",
        "weight", "assign", "loaded_at", "loading_dock", "pallets_count",
        "transporter_name", "line_items", "image_groups",
    ])
    for gdn in query.order_by(GDN.id.desc()).all():
        writer.writerow([
            gdn.id, gdn.gdn_reference, gdn.customer_name, gdn.site_name,
            gdn.materials_description_summary, gdn.invoice_date, gdn.payment_status,
            gdn.status, gdn.weight, gdn.assign, gdn.loaded_at, gdn.loading_dock, gdn.pallets_count,
            gdn.transporter_name, json.dumps(gdn.line_items or [], ensure_ascii=False),
            json.dumps(gdn.image_groups or [], ensure_ascii=False),
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=gdn_export.csv"},
    )


@router.get(
    "/{gdn_id}",
    response_model=GDNResponse,
    summary="Get a goods delivery note",
)
def get_gdn(
    gdn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    gdn = db.query(GDN).filter(GDN.id == gdn_id).first()
    if not gdn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GDN not found")
    return gdn


@router.patch(
    "/{gdn_id}",
    response_model=GDNResponse,
    summary="Partially update a goods delivery note with optional images",
)
async def update_gdn(
    gdn_id: int,
    customer_name: Optional[str] = Form(None),
    site_name: Optional[str] = Form(None),
    materials_description_summary: Optional[str] = Form(None),
    invoice_date: Optional[date] = Form(None),
    line_items: Optional[str] = Form(None, description="JSON array of line items."),
    payment_status: Optional[str] = Form(None),
    status_value: Optional[str] = Form(None, alias="status"),
    weight: Optional[int] = Form(None, ge=0),
    assign: Optional[bool] = Form(None),
    gdn_reference: Optional[str] = Form(None),
    loaded_at: Optional[datetime] = Form(None),
    loading_dock: Optional[str] = Form(None),
    pallets_count: Optional[int] = Form(None, ge=0),
    transporter_name: Optional[str] = Form(None),
    image_groups: Optional[str] = Form(
        None,
        description='JSON array: [{"title":"Loading Dock Photos","images":["dock_1.jpg"]}]',
    ),
    images: Optional[list[UploadFile]] = File(
        None,
        description="Optional replacement images referenced by filename in image_groups.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    gdn = db.query(GDN).filter(GDN.id == gdn_id).first()
    if not gdn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GDN not found")

    try:
        update_data = {
            "customer_name": customer_name,
            "site_name": site_name,
            "materials_description_summary": materials_description_summary,
            "invoice_date": invoice_date,
            "line_items": json.loads(line_items) if line_items else None,
            "payment_status": payment_status,
            "status": status_value,
            "weight": weight,
            "assign": assign,
            "gdn_reference": gdn_reference,
            "loaded_at": loaded_at,
            "loading_dock": loading_dock,
            "pallets_count": pallets_count,
            "transporter_name": transporter_name,
        }
        gdn_in = GDNUpdate.model_validate({
            key: value for key, value in update_data.items() if value is not None
        })
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="line_items must be valid JSON and all fields must be valid") from exc

    for key, value in gdn_in.model_dump(exclude_unset=True).items():
        setattr(gdn, key, value)
    if "site_name" in gdn_in.model_fields_set:
        gdn.latitude, gdn.longitude = await run_in_threadpool(_geocode_site, gdn.site_name)
    if image_groups is not None or images:
        gdn.image_groups = await _upload_image_groups(image_groups, images, gdn.gdn_reference)
    return _commit_gdn(db, gdn)


@router.delete(
    "/{gdn_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a goods delivery note",
)
def delete_gdn(
    gdn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    gdn = db.query(GDN).filter(GDN.id == gdn_id).first()
    if not gdn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GDN not found")

    db.delete(gdn)
    db.commit()
    return {"status": "success", "message": f"GDN {gdn_id} deleted", "deleted_id": gdn_id}
