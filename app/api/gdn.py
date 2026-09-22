from datetime import date, timedelta
import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.gdn import GDN
from app.schema.gdn import GDNCreate, GDNListResponse, GDNResponse, GDNStats, GDNUpdate
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(prefix="/gdn", tags=["Invoice & GDN"])

GDN_ROLES = [UserRole.STORE_MANAGER]


def _commit_gdn(db: Session, gdn: GDN, duplicate_message: str = "GDN reference already exists") -> GDN:
    try:
        db.commit()
        db.refresh(gdn)
        return gdn
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_message)


def _filtered_gdn_query(
    db: Session,
    search: Optional[str],
    payment_status: Optional[str],
    status_filter: Optional[str],
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
    summary="Create a goods delivery note",
)
def create_gdn(
    gdn_in: GDNCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    gdn = GDN(**gdn_in.model_dump())
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
        db, search, payment_status, status_filter, date_range, from_date, to_date
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
    date_range: Optional[str] = Query("all", description="all, this_week, or this_month."),
    from_date: Optional[date] = Query(None, description="Custom start date, YYYY-MM-DD."),
    to_date: Optional[date] = Query(None, description="Custom end date, YYYY-MM-DD."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    query = _filtered_gdn_query(
        db, search, payment_status, status_filter, date_range, from_date, to_date
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "id", "gdn_reference", "customer_name", "site_name",
        "materials_description_summary", "invoice_date", "payment_status", "status",
        "loaded_at", "loading_dock", "pallets_count", "transporter_name", "line_items",
    ])
    for gdn in query.order_by(GDN.id.desc()).all():
        writer.writerow([
            gdn.id, gdn.gdn_reference, gdn.customer_name, gdn.site_name,
            gdn.materials_description_summary, gdn.invoice_date, gdn.payment_status,
            gdn.status, gdn.loaded_at, gdn.loading_dock, gdn.pallets_count,
            gdn.transporter_name, json.dumps(gdn.line_items or [], ensure_ascii=False),
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
    summary="Partially update a goods delivery note",
)
def update_gdn(
    gdn_id: int,
    gdn_in: GDNUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(GDN_ROLES)),
):
    gdn = db.query(GDN).filter(GDN.id == gdn_id).first()
    if not gdn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GDN not found")

    for key, value in gdn_in.model_dump(exclude_unset=True).items():
        setattr(gdn, key, value)
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
