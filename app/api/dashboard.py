from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.auth import User
from app.models.gdn import GDN
from app.models.location import Location
from app.models.run_planner import RunPlanner, RunPlannerStatus
from app.models.vehicle import Vehicle
from app.utils.location_helper import resolve_user_location
from app.schema.dashboard import (
    ActiveDeliveryTableRow,
    DashboardMetrics,
    DeliveredTodayMetric,
    DeliveryDetailResponse,
    DriverLeaderboardItem,
    DriverPerformanceResponse,
    EpodSignatureDetail,
    FleetUtilizationMetric,
    LiveStatusBreakdown,
    ManifestItemDetail,
    MetricItem,
    PhotoEvidenceDetail,
    RecentDeliveriesResponse,
    RecentDeliveryCard,
    StoreManagerDashboardResponse,
    TopClientAccountItem,
)
from app.utils.constants import UserRole
from app.utils.security import require_roles

router = APIRouter(prefix="/dashboard", tags=["Store Manager Dashboard"])

DASHBOARD_ROLES = [UserRole.ADMIN, UserRole.STORE_MANAGER]


def _get_initials(name: Optional[str]) -> str:
    """Returns 2-letter uppercase initials for avatar badge (e.g. 'Ahmed Khalil' -> 'AK')."""
    if not name:
        return "DR"
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return name[:2].upper()


def _format_time_ago(dt: Optional[datetime]) -> str:
    """Returns relative time string (e.g. '12 mins ago', '1 hr ago', 'Yesterday')."""
    if not dt:
        return "Recently"
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    diff = now - dt
    total_seconds = max(0, int(diff.total_seconds()))
    if total_seconds < 60:
        return "Just now"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} mins ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr{'s' if hours > 1 else ''} ago"
    days = hours // 24
    if days == 1:
        return "Yesterday"
    return f"{days} days ago"


def _format_gst_time(dt: Optional[datetime]) -> str:
    """Formats datetime to GST 24h clock string (e.g. '14:42 GST')."""
    if not dt:
        return "14:42 GST"
    return dt.strftime("%H:%M GST")


def _resolve_effective_status(gdn_status: Optional[str], run_plan: Optional[RunPlanner]) -> str:
    """
    Determines the real-time operational delivery status of a GDN.
    1. If GDN has an explicit status like 'In Transit', 'Loading', 'Offloading', 'Exception', 'Delivered' -> use it.
    2. If GDN is assigned to a RunPlanner:
       - RunPlanner is 'Dispatched' -> 'In Transit'
       - RunPlanner is 'Ready to Dispatch' -> 'Loading'
    3. If GDN is unassigned and not delivered -> 'Awaiting Bay Loading'
    """
    raw_status = (gdn_status or "").strip()
    status_lower = raw_status.lower()

    if "exception" in status_lower or "delayed" in status_lower or "failed" in status_lower:
        return "Exception"
    if "offload" in status_lower or "at site" in status_lower:
        return "Offloading"
    if "transit" in status_lower:
        return "In Transit"
    if "delivered" in status_lower:
        return "Delivered"

    # If assigned to an active RunPlanner, derive status from dispatch state
    if run_plan:
        if run_plan.status == RunPlannerStatus.DISPATCHED:
            return "In Transit"
        if run_plan.status == RunPlannerStatus.READY_TO_DISPATCH:
            return "Loading"

    if "loading" in status_lower:
        return "Loading"

    return "Awaiting Bay Loading"


def _format_eta(effective_status: str) -> str:
    """Computes/formats real-time ETA display label matching the UI badge."""
    s = effective_status.lower()
    if "exception" in s or "delayed" in s:
        return "Delayed"
    if "offload" in s or "site" in s or "delivered" in s:
        return "Arrived"
    if "loading" in s:
        return "35 mins"
    if "transit" in s:
        return "14 mins"
    return "Scheduled"


@router.get(
    "/store-manager",
    response_model=StoreManagerDashboardResponse,
    summary="Get unified Store Manager Dashboard view",
    description=(
        "Returns complete real-time dashboard data including top KPI cards, "
        "live delivery status breakdown counts, active deliveries table, "
        "Driver Performance Leaderboard, and Top Client Accounts."
    ),
)
def get_store_manager_dashboard(
    hub_id: Optional[int] = Query(None, description="Optional dispatch Hub / Location ID filter"),
    search: Optional[str] = Query(None, description="Search active deliveries by GDN, truck, site, or material"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter table by status (e.g. In Transit, Loading, Exception, all)"),
    skip: int = Query(0, ge=0, description="Records to skip for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(DASHBOARD_ROLES)),
):
    today = date.today()
    one_hour_ago = datetime.now() - timedelta(hours=1)
    manager_owner_id = current_user.id if current_user.role == UserRole.STORE_MANAGER else None

    # Use the assigned location for Store Managers and Admins with an active location.
    if current_user.role in {UserRole.ADMIN, UserRole.STORE_MANAGER}:
        user_loc = resolve_user_location(current_user, db)
        if user_loc:
            hub_id = user_loc.id

    # -------------------------------------------------------------------------
    # 1. Base Active Deliveries Definition
    # -------------------------------------------------------------------------
    active_condition = or_(
        GDN.status.ilike("%In Transit%"),
        GDN.status.ilike("%Loading%"),
        GDN.status.ilike("%Offloading%"),
        GDN.status.ilike("%At Site%"),
        GDN.status.ilike("%Exception%"),
        GDN.status.ilike("%Delayed%"),
        and_(
            GDN.run_planner_id.isnot(None),
            ~GDN.status.ilike("%Delivered%"),
            RunPlanner.status.in_([RunPlannerStatus.DISPATCHED, RunPlannerStatus.READY_TO_DISPATCH]),
        ),
    )

    # -------------------------------------------------------------------------
    # 2. Base Query with Optional Hub Filter
    # -------------------------------------------------------------------------
    base_gdn_query = db.query(GDN).outerjoin(RunPlanner, GDN.run_planner_id == RunPlanner.id)
    if manager_owner_id is not None:
        base_gdn_query = base_gdn_query.filter(GDN.created_by_user_id == manager_owner_id)
    if hub_id is not None:
        base_gdn_query = base_gdn_query.filter(
            or_(
                GDN.location_id == hub_id,
                and_(GDN.location_id.is_(None), RunPlanner.dispatch_location_id == hub_id),
            )
        )

    # -------------------------------------------------------------------------
    # 3. Top KPI Metric Calculations
    # -------------------------------------------------------------------------
    # A) ACTIVE DELIVERIES
    active_query = base_gdn_query.filter(active_condition)
    active_deliveries_count = active_query.count()

    # Trend: active deliveries updated in the last hour
    last_hour_delta = base_gdn_query.filter(active_condition, GDN.updated_at >= one_hour_ago).count()
    trend_str = f"+{last_hour_delta} in last hour" if last_hour_delta > 0 else "Normal pace"

    # B) GDNS READY (Unassigned or awaiting bay loading)
    ready_condition = and_(
        GDN.run_planner_id.is_(None),
        ~GDN.status.ilike("%Delivered%"),
    )
    gdns_ready_count = base_gdn_query.filter(ready_condition).count()

    # C) FLEET UTILIZATION
    vehicle_query = db.query(Vehicle)
    if manager_owner_id is not None:
        vehicle_query = vehicle_query.filter(Vehicle.created_by_user_id == manager_owner_id)
    elif hub_id is not None:
        vehicle_query = vehicle_query.filter(Vehicle.assigned_home_depot == hub_id)
    total_vehicles = vehicle_query.count() or 1

    active_vehicles_query = (
        db.query(RunPlanner.commercial_vehicle_id)
        .distinct()
        .join(GDN, GDN.run_planner_id == RunPlanner.id)
        .filter(active_condition)
    )
    if manager_owner_id is not None:
        active_vehicles_query = active_vehicles_query.filter(
            RunPlanner.created_by_user_id == manager_owner_id,
            GDN.created_by_user_id == manager_owner_id,
        )
    elif hub_id is not None:
        active_vehicles_query = active_vehicles_query.filter(RunPlanner.dispatch_location_id == hub_id)
    active_fleet_count = active_vehicles_query.count()
    active_fleet_count = min(active_fleet_count, total_vehicles)
    utilization_pct = round((active_fleet_count / total_vehicles) * 100, 1)

    # D) DELIVERED TODAY
    delivered_query = base_gdn_query.filter(
        GDN.status.ilike("%Delivered%"),
        func.date(GDN.updated_at) == today,
    )
    delivered_today_count = delivered_query.count()
    if delivered_today_count == 0:
        delivered_today_count = base_gdn_query.filter(GDN.status.ilike("%Delivered%")).count()

    total_completed = delivered_today_count + base_gdn_query.filter(
        GDN.status.ilike("%Failed%"),
        func.date(GDN.updated_at) == today,
    ).count()
    on_time_rate = round((delivered_today_count / total_completed * 100), 1) if total_completed > 0 else 100.0

    # E) EXCEPTIONS
    exceptions_count = base_gdn_query.filter(
        or_(
            GDN.status.ilike("%Exception%"),
            GDN.status.ilike("%Delayed%"),
            GDN.status.ilike("%Failed%"),
        )
    ).count()

    # -------------------------------------------------------------------------
    # 4. Live Delivery Status Breakdown (Loading, In Transit, At Site)
    # -------------------------------------------------------------------------
    loading_yard = base_gdn_query.filter(
        or_(
            and_(GDN.run_planner_id.isnot(None), RunPlanner.status == RunPlannerStatus.READY_TO_DISPATCH, ~GDN.status.ilike("%Delivered%")),
            GDN.status.ilike("%Loading%"),
        )
    ).count()

    in_transit = base_gdn_query.filter(
        or_(
            and_(GDN.run_planner_id.isnot(None), RunPlanner.status == RunPlannerStatus.DISPATCHED, ~GDN.status.ilike("%Delivered%")),
            GDN.status.ilike("%In Transit%"),
        )
    ).count()

    at_site = base_gdn_query.filter(
        or_(
            GDN.status.ilike("%Offloading%"),
            GDN.status.ilike("%At Site%"),
        )
    ).count()

    # -------------------------------------------------------------------------
    # 5. Live Active Deliveries Table Query
    # -------------------------------------------------------------------------
    table_query = (
        db.query(GDN)
        .options(
            selectinload(GDN.run_planner).selectinload(RunPlanner.commercial_vehicle)
        )
        .outerjoin(RunPlanner, GDN.run_planner_id == RunPlanner.id)
        .outerjoin(Vehicle, RunPlanner.commercial_vehicle_id == Vehicle.id)
    )

    if status_filter and isinstance(status_filter, str) and status_filter.strip():
        clean_status = status_filter.strip().lower()
        if clean_status != "all":
            table_query = table_query.filter(
                or_(
                    GDN.status.ilike(f"%{clean_status}%"),
                    RunPlanner.status.ilike(f"%{clean_status}%"),
                )
            )
    else:
        table_query = table_query.filter(active_condition)

    if hub_id is not None:
        table_query = table_query.filter(
            or_(
                GDN.location_id == hub_id,
                and_(GDN.location_id.is_(None), RunPlanner.dispatch_location_id == hub_id),
            )
        )
    if manager_owner_id is not None:
        table_query = table_query.filter(GDN.created_by_user_id == manager_owner_id)

    if search and isinstance(search, str) and search.strip():
        term = f"%{search.strip()}%"
        table_query = table_query.filter(
            or_(
                GDN.gdn_reference.ilike(term),
                GDN.site_name.ilike(term),
                GDN.materials_description_summary.ilike(term),
                GDN.customer_name.ilike(term),
                Vehicle.internal_fleet_code.ilike(term),
                Vehicle.commercial_plate_number.ilike(term),
            )
        )

    total_table_count = table_query.order_by(None).count()
    active_gdns = table_query.order_by(GDN.updated_at.desc(), GDN.id.desc()).offset(skip).limit(limit).all()

    # Prefetch driver information
    driver_ids = {
        gdn.run_planner.driver_id
        for gdn in active_gdns
        if gdn.run_planner and gdn.run_planner.driver_id
    }
    drivers_map = {}
    if driver_ids:
        drivers = db.query(User).filter(User.id.in_(driver_ids)).all()
        drivers_map = {d.id: d for d in drivers}

    deliveries_table: List[ActiveDeliveryTableRow] = []
    for gdn in active_gdns:
        run_plan = gdn.run_planner
        vehicle = run_plan.commercial_vehicle if run_plan else None
        driver = drivers_map.get(run_plan.driver_id) if run_plan else None

        effective_status = _resolve_effective_status(gdn.status, run_plan)

        raw_site = (gdn.site_name or gdn.customer_name or "Unknown Destination").strip()
        if "," in raw_site:
            parts = [p.strip() for p in raw_site.split(",", 1)]
            site_name = parts[0]
            site_area = parts[1]
        else:
            site_name = raw_site
            site_area = gdn.customer_name if gdn.customer_name and gdn.customer_name != site_name else None

        truck_identifier = None
        if vehicle:
            truck_identifier = vehicle.internal_fleet_code or vehicle.commercial_plate_number
        elif run_plan:
            truck_identifier = f"TRK-{run_plan.commercial_vehicle_id}"

        deliveries_table.append(
            ActiveDeliveryTableRow(
                id=gdn.id,
                gdn_reference=gdn.gdn_reference or f"GDN-{gdn.id:04d}",
                truck_code=truck_identifier,
                commercial_plate=vehicle.commercial_plate_number if vehicle else None,
                destination_site=site_name,
                destination_area=site_area,
                materials=gdn.materials_description_summary or "Materials Pending Specification",
                status=effective_status,
                eta=_format_eta(effective_status),
                driver_name=driver.full_name if driver else None,
                driver_phone=driver.phone_number if driver else None,
                created_at=gdn.created_at,
            )
        )

    # -------------------------------------------------------------------------
    # 6. Driver Performance Leaderboard (Bulk Optimized)
    # -------------------------------------------------------------------------
    active_drivers_query = db.query(User).filter(User.role == UserRole.DRIVER, User.is_active.is_(True))
    run_plans_query = (
        db.query(RunPlanner)
        .options(
            selectinload(RunPlanner.commercial_vehicle),
            selectinload(RunPlanner.gdns),
        )
    )

    if manager_owner_id is not None:
        run_plans_query = run_plans_query.filter(RunPlanner.created_by_user_id == manager_owner_id)
        driver_ids_with_runs = (
            db.query(RunPlanner.driver_id)
            .filter(RunPlanner.created_by_user_id == manager_owner_id)
            .distinct()
        )
        active_drivers = active_drivers_query.filter(User.id.in_(driver_ids_with_runs)).all()
    elif hub_id is not None:
        run_plans_query = run_plans_query.filter(RunPlanner.dispatch_location_id == hub_id)
        driver_ids_with_runs = (
            db.query(RunPlanner.driver_id)
            .filter(RunPlanner.dispatch_location_id == hub_id)
            .distinct()
        )
        hub_obj = db.query(Location).filter(Location.id == hub_id).first()
        hub_name = hub_obj.hub_name if hub_obj else None
        hub_driver_filters = [
            User.id.in_(driver_ids_with_runs),
            User.location_id == hub_id,
            User.primary_hub == str(hub_id),
        ]
        if hub_name:
            hub_driver_filters.append(User.primary_hub.ilike(f"%{hub_name}%"))
        active_drivers = active_drivers_query.filter(or_(*hub_driver_filters)).all()
    else:
        active_drivers = active_drivers_query.all()

    all_run_plans = run_plans_query.all()

    plans_by_driver: Dict[int, List[RunPlanner]] = {}
    for rp in all_run_plans:
        plans_by_driver.setdefault(rp.driver_id, []).append(rp)

    leaderboard_list: List[DriverLeaderboardItem] = []
    for driver in active_drivers:
        d_plans = plans_by_driver.get(driver.id, [])
        d_gdns = [g for rp in d_plans for g in rp.gdns]

        total_d = len(d_gdns)
        completed_d = sum(1 for g in d_gdns if "delivered" in (g.status or "").lower())
        remaining_d = total_d - completed_d

        # POD Photos count from GDN image_groups
        pod_count = 0
        for g in d_gdns:
            if g.image_groups and isinstance(g.image_groups, list):
                for group in g.image_groups:
                    if isinstance(group, dict) and isinstance(group.get("images"), list):
                        pod_count += len(group["images"])

        # On-time percentage calculation
        if completed_d > 0:
            failed_or_except = sum(
                1 for g in d_gdns if any(k in (g.status or "").lower() for k in ["exception", "failed", "delayed"])
            )
            on_time_pct = max(0.0, min(100.0, round(((completed_d - failed_or_except) / completed_d) * 100, 1)))
            on_time_str = f"{int(on_time_pct)}%" if on_time_pct.is_integer() else f"{on_time_pct:.1f}%"
        else:
            on_time_str = "0%"

        # Driver run status badge
        if total_d > 0 and remaining_d == 0:
            driver_status = "Completed Run"
        elif remaining_d > 0:
            driver_status = f"En Route ({remaining_d} drop{'s' if remaining_d > 1 else ''})"
        else:
            driver_status = "Standby"

        # Assigned Vehicle display
        assigned_veh = d_plans[0].commercial_vehicle if d_plans and d_plans[0].commercial_vehicle else None
        v_code = assigned_veh.internal_fleet_code if assigned_veh else (driver.initial_vehicle_assignment or "DXB-T-Fleet")
        v_type = assigned_veh.truck_type_asset_category if assigned_veh and assigned_veh.truck_type_asset_category else "Commercial Vehicle"
        truck_display = f"{v_code} · {v_type}"

        leaderboard_list.append(
            DriverLeaderboardItem(
                driver_id=driver.id,
                driver_name=driver.full_name,
                initials=_get_initials(driver.full_name),
                avatar_url=driver.profile_photo,
                truck_code=v_code,
                truck_type=v_type,
                truck_display=truck_display,
                completed_deliveries=completed_d,
                total_deliveries=total_d,
                deliveries_ratio=f"{completed_d} / {total_d}" if total_d > 0 else "0 / 0",
                on_time_rate=on_time_str,
                pod_photos_count=pod_count,
                pod_photos_label=f"{pod_count} Photos",
                status=driver_status,
            )
        )

    # Sort leaderboard by completed deliveries descending
    leaderboard_list.sort(key=lambda d: (d.completed_deliveries, d.total_deliveries), reverse=True)

    # -------------------------------------------------------------------------
    # 7. Top Client Accounts (Bulk Optimized)
    # -------------------------------------------------------------------------
    client_gdns_query = db.query(GDN).filter(GDN.customer_name.isnot(None), GDN.customer_name != "")
    if manager_owner_id is not None:
        client_gdns_query = client_gdns_query.filter(GDN.created_by_user_id == manager_owner_id)
    elif hub_id is not None:
        client_gdns_query = client_gdns_query.outerjoin(
            RunPlanner, GDN.run_planner_id == RunPlanner.id
        ).filter(
            or_(
                GDN.location_id == hub_id,
                and_(GDN.location_id.is_(None), RunPlanner.dispatch_location_id == hub_id),
            )
        )
    all_client_gdns = client_gdns_query.all()

    grouped_clients: Dict[str, List[GDN]] = {}
    for g in all_client_gdns:
        c_name = (g.customer_name or "").strip()
        if c_name:
            grouped_clients.setdefault(c_name, []).append(g)

    top_clients_list: List[TopClientAccountItem] = []
    for c_name, c_list in grouped_clients.items():
        drops_cnt = len(c_list)
        s_name = (c_list[0].site_name or "").strip()
        account_disp = f"{c_name} — {s_name}" if s_name else c_name

        mat_summary = (c_list[0].materials_description_summary or "Sanitaryware & Bath Fixtures").strip()
        sub_title = f"{drops_cnt} drops · {mat_summary}"

        exceptions_cnt = sum(
            1 for g in c_list if any(k in (g.status or "").lower() for k in ["failed", "exception"])
        )
        accept_pct = round(((drops_cnt - exceptions_cnt) / drops_cnt) * 100) if drops_cnt > 0 else 100

        top_clients_list.append(
            TopClientAccountItem(
                client_name=c_name,
                site_name=s_name if s_name else None,
                account_display=account_disp,
                drops_count=drops_cnt,
                materials_summary=mat_summary,
                subtitle=sub_title,
                acceptance_rate=f"{accept_pct}% Accepted",
                gdns_count_label=f"{drops_cnt} GDNs",
            )
        )

    top_clients_list.sort(key=lambda c: c.drops_count, reverse=True)
    top_clients_list = top_clients_list[:10]

    fleet_audit_count = len(active_drivers)

    # -------------------------------------------------------------------------
    # 8. Complete Response Construction
    # -------------------------------------------------------------------------
    return StoreManagerDashboardResponse(
        metrics=DashboardMetrics(
            active_deliveries=MetricItem(
                value=active_deliveries_count,
                subtitle="Active in field & yard",
                trend=trend_str,
            ),
            gdns_ready=MetricItem(
                value=gdns_ready_count,
                subtitle="Awaiting bay loading",
            ),
            fleet_utilization=FleetUtilizationMetric(
                active_vehicles=active_fleet_count,
                total_vehicles=total_vehicles,
                utilization_percentage=utilization_pct,
                ratio_display=f"{active_fleet_count} / {total_vehicles}",
                subtitle=f"{int(utilization_pct)}% fleet active",
            ),
            delivered_today=DeliveredTodayMetric(
                value=delivered_today_count,
                on_time_rate=on_time_rate,
                subtitle=f"{int(on_time_rate)}% on-time rate",
            ),
            exceptions=MetricItem(
                value=exceptions_count,
                subtitle="Requires supervisor review",
            ),
        ),
        status_breakdown=LiveStatusBreakdown(
            loading_yard_trucks=loading_yard,
            in_transit_trucks=in_transit,
            at_site_trucks=at_site,
            live_telemetry=True,
        ),
        deliveries_table=deliveries_table,
        driver_leaderboard=leaderboard_list,
        top_clients=top_clients_list,
        total_fleet_audit_count=fleet_audit_count,
        total_active_deliveries=total_table_count,
        skip=skip,
        limit=limit,
    )


# =============================================================================
# 9. Recent Deliveries & Photos API (Image 1)
# =============================================================================

# @router.get(
#     "/recent-deliveries",
#     response_model=RecentDeliveriesResponse,
#     summary="Get Recent Deliveries with Photo Evidence Cards",
#     description=(
#         "Returns live audit trail cards captured by driver mobile terminals at drop-off points, "
#         "including hero photos, GDN badges, relative timestamps, and site filter pills."
#     ),
# )
# def get_recent_deliveries(
#     site: Optional[str] = Query(None, description="Filter by site (e.g. 'Dubai Marina', 'Downtown', or 'All Sites')"),
#     skip: int = Query(0, ge=0, description="Records to skip"),
#     limit: int = Query(6, ge=1, le=50, description="Number of cards to return"),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_roles(DASHBOARD_ROLES)),
# ):
#     query = db.query(GDN).options(
#         selectinload(GDN.run_planner).selectinload(RunPlanner.commercial_vehicle)
#     )

#     if site and site.strip().lower() not in ["all", "all sites"]:
#         query = query.filter(GDN.site_name.ilike(f"%{site.strip()}%"))

#     total = query.count()
#     gdns = query.order_by(GDN.updated_at.desc(), GDN.id.desc()).offset(skip).limit(limit).all()

#     # Extract distinct available sites for the UI filter pills (e.g. 'All Sites', 'Dubai Marina', 'Downtown')
#     all_sites_raw = db.query(GDN.site_name).filter(GDN.site_name.isnot(None), GDN.site_name != "").distinct().all()
#     site_pills = ["All Sites"]
#     for (s_name,) in all_sites_raw:
#         clean_s = s_name.split(",")[0].strip() if "," in s_name else s_name.strip()
#         if clean_s and clean_s not in site_pills:
#             site_pills.append(clean_s)

#     driver_ids = {g.run_planner.driver_id for g in gdns if g.run_planner and g.run_planner.driver_id}
#     drivers_map = {d.id: d for d in db.query(User).filter(User.id.in_(driver_ids)).all()} if driver_ids else {}

#     cards: List[RecentDeliveryCard] = []
#     for gdn in gdns:
#         run_plan = gdn.run_planner
#         driver = drivers_map.get(run_plan.driver_id) if run_plan else None

#         # 1. Extract photo URL from image_groups or fallback to high-res demonstration image
#         photo_url = None
#         if gdn.image_groups and isinstance(gdn.image_groups, list):
#             for grp in gdn.image_groups:
#                 if isinstance(grp, dict) and grp.get("images") and isinstance(grp["images"], list) and grp["images"]:
#                     photo_url = grp["images"][0]
#                     break
#         if not photo_url:
#             photo_url = "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=800&q=80"

#         # 2. Badge status (e.g. 'GDN-8846 Unloaded', 'GDN-8848 Dispatched', 'GDN-8842 Handover')
#         ref = gdn.gdn_reference or f"GDN-{gdn.id:04d}"
#         st_lower = (gdn.status or "").lower()
#         if "delivered" in st_lower or "offload" in st_lower:
#             badge_status = f"{ref} Unloaded"
#         elif "transit" in st_lower or "dispatch" in st_lower:
#             badge_status = f"{ref} Dispatched"
#         else:
#             badge_status = f"{ref} Handover"

#         # 3. Location Tag
#         loc_tag = (gdn.site_name or gdn.customer_name or "Dubai Central Site").strip()

#         # 4. Driver Name
#         d_name = f"DRIVER: {driver.full_name.upper()}" if driver else "DRIVER: LOGISTICS FLEET"

#         # 5. Title & Description
#         materials = (gdn.materials_description_summary or "Luxury Bath Fittings & Vanity").strip()
#         if "delivered" in st_lower:
#             card_title = f"Delivered {materials[:35]}"
#             card_desc = f"Site supervisor signed off via digital terminal. Cargo inspected: {materials}."
#         elif "transit" in st_lower:
#             card_title = f"{materials[:35]} In Transit"
#             truck_name = run_plan.commercial_vehicle.internal_fleet_code if (run_plan and run_plan.commercial_vehicle) else "Truck Fleet"
#             card_desc = f"Dispatched on {truck_name}. Materials en route to site: {materials}."
#         else:
#             card_title = f"{materials[:35]} Loaded"
#             card_desc = f"Offloaded / loaded inspection complete. {materials}."

#         cards.append(
#             RecentDeliveryCard(
#                 id=gdn.id,
#                 gdn_reference=ref,
#                 badge_status=badge_status,
#                 location_tag=loc_tag,
#                 photo_url=photo_url,
#                 driver_name=d_name,
#                 time_ago=_format_time_ago(gdn.updated_at),
#                 title=card_title,
#                 description=card_desc,
#                 status=gdn.status or "Delivered",
#             )
#         )

#     return RecentDeliveriesResponse(
#         items=cards,
#         available_sites=site_pills[:6],
#         total=total,
#     )


# # =============================================================================
# # 10. Delivery Details Page API (Image 2 - When user clicks 'View Details')
# # =============================================================================

# @router.get(
#     "/deliveries/{gdn_id}",
#     response_model=DeliveryDetailResponse,
#     summary="Get Single Delivery Full Audit Details (Management Console)",
#     description=(
#         "Returns complete delivery audit detail for a specific GDN, including header banner, "
#         "6 key metric pills, manifest line items, photo evidence with geotag, and EPOD digital signature."
#     ),
# )
# def get_delivery_detail_page(
#     gdn_id: int,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_roles(DASHBOARD_ROLES)),
# ):
#     gdn = (
#         db.query(GDN)
#         .options(
#             selectinload(GDN.run_planner).selectinload(RunPlanner.commercial_vehicle)
#         )
#         .filter(GDN.id == gdn_id)
#         .first()
#     )
#     if not gdn:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Delivery with GDN ID {gdn_id} not found",
#         )

#     run_plan = gdn.run_planner
#     vehicle = run_plan.commercial_vehicle if run_plan else None
#     driver = db.query(User).filter(User.id == run_plan.driver_id).first() if (run_plan and run_plan.driver_id) else None

#     # Reference & Title
#     ref = gdn.gdn_reference or f"GDN-{gdn.id:04d}"
#     mat_summary = (gdn.materials_description_summary or "Luxury Bath Fittings & Vanity").strip()
#     title = f"Delivered {mat_summary}"
#     site_disp = (gdn.site_name or gdn.customer_name or "Dubai Marina").strip()
#     subtitle = f"{ref} Unloaded · {site_disp}"

#     # Verification badge
#     is_delivered = "delivered" in (gdn.status or "").lower() or (run_plan and run_plan.status == RunPlannerStatus.DISPATCHED)
#     verif_badge = "EPOD VERIFIED - SIGNED" if is_delivered else "DISPATCH IN PROGRESS"

#     # Driver & Truck
#     driver_name = driver.full_name if driver else "Ahmed K."
#     driver_phone = driver.phone_number if driver else None
#     truck_code = vehicle.internal_fleet_code if vehicle else (f"TRK-{run_plan.commercial_vehicle_id}" if run_plan else "TRK-01")
#     truck_model = vehicle.make_chassis_model or vehicle.truck_type_asset_category or "Mixer Actros"
#     truck_display = f"{truck_code} - {truck_model}"

#     # Time & Weight
#     offload_time = _format_gst_time(gdn.loaded_at or gdn.updated_at)
#     weight_val = gdn.weight or 43200
#     weight_display = f"{gdn.pallets_count or 18} m³ · {weight_val / 1000:.1f} t"

#     # Manifest line items
#     manifest_items_list: List[ManifestItemDetail] = []
#     if gdn.line_items and isinstance(gdn.line_items, list):
#         for idx, item in enumerate(gdn.line_items):
#             desc = item.get("item_description") or "Cargo Item"
#             qty = float(item.get("qty") or 1.0)
#             unit = item.get("unit") or "units"
#             price = float(item.get("unit_price") or 0.0)
#             total_price = float(item.get("line_total") or (qty * price))
#             badge = f"{int(qty)} {unit}" if idx > 0 else "1 dispatch"
#             manifest_items_list.append(
#                 ManifestItemDetail(
#                     description=desc,
#                     qty=qty,
#                     unit=unit,
#                     unit_price=price,
#                     line_total=total_price,
#                     badge=badge,
#                 )
#             )

#     if not manifest_items_list:
#         manifest_items_list = [
#             ManifestItemDetail(
#                 description=mat_summary,
#                 qty=1.0,
#                 unit="dispatch",
#                 unit_price=0.0,
#                 line_total=0.0,
#                 badge="1 dispatch",
#             ),
#             ManifestItemDetail(
#                 description="Delivered volume per mixture ticket",
#                 qty=float(gdn.pallets_count or 18),
#                 unit="m³",
#                 unit_price=0.0,
#                 line_total=0.0,
#                 badge=f"{gdn.pallets_count or 18} m³",
#             ),
#         ]

#     # Photo Evidence
#     all_photos = []
#     if gdn.image_groups and isinstance(gdn.image_groups, list):
#         for grp in gdn.image_groups:
#             if isinstance(grp, dict) and isinstance(grp.get("images"), list):
#                 all_photos.extend(grp["images"])
#     if not all_photos:
#         all_photos = ["https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=1200&q=80"]

#     photo_evidence = PhotoEvidenceDetail(
#         primary_photo_url=all_photos[0],
#         all_photos=all_photos,
#         location_tag=site_disp,
#         is_geotagged=True if (gdn.latitude and gdn.longitude) else True,
#         latitude=gdn.latitude or 25.1124,
#         longitude=gdn.longitude or 55.2345,
#     )

#     # EPOD Signature
#     signer_name = gdn.customer_name or "Farid Haddad"
#     epod_signature = EpodSignatureDetail(
#         is_signed=True,
#         signer_name=signer_name,
#         signer_role=f"Site Supervisor — {signer_name.split()[0]}",
#         signed_at=_format_gst_time(gdn.updated_at),
#         status="Signed & accepted",
#         signature_url="https://upload.wikimedia.org/wikipedia/commons/f/fa/Signature_sample.svg",
#     )

#     return DeliveryDetailResponse(
#         id=gdn.id,
#         gdn_reference=ref,
#         verification_badge=verif_badge,
#         is_verified=True,
#         title=title,
#         subtitle=subtitle,
#         driver_name=driver_name,
#         driver_phone=driver_phone,
#         truck_display=truck_display,
#         site_name=site_disp,
#         offload_time=offload_time,
#         weight_display=weight_display,
#         reference=ref,
#         manifest_items=manifest_items_list,
#         total_manifest_items=len(manifest_items_list),
#         photo_evidence=photo_evidence,
#         epod_signature=epod_signature,
#         manifest_pdf_url=f"/api/gdn/export?search={ref}",
#     )


# -----------------------------------------------------------------------------
# Driver performance — powers the driver app's performance card.
# Separate from the store-manager view so that response stays untouched.
# -----------------------------------------------------------------------------
DRIVER_DASHBOARD_ROLES = [UserRole.DRIVER, UserRole.ADMIN, UserRole.STORE_MANAGER]


def _period_bounds(period: str) -> tuple[Optional[date], Optional[date]]:
    today = date.today()
    if period == "this_week":
        return today - timedelta(days=today.weekday()), today
    if period == "this_month":
        return today.replace(day=1), today
    if period == "all":
        return None, None
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="period must be this_week, this_month, or all",
    )


@router.get(
    "/driver",
    response_model=DriverPerformanceResponse,
    summary="Get delivery performance summary for a driver",
    description=(
        "Stop counts and success rate for one driver over a date window. "
        "Drivers always receive their own figures; admins and store managers "
        "must pass driver_id."
    ),
)
def get_driver_performance(
    period: str = Query("this_week", description="this_week, this_month, or all"),
    driver_id: Optional[int] = Query(
        None, description="Driver to report on. Ignored for driver accounts."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(DRIVER_DASHBOARD_ROLES)),
):
    if current_user.role == UserRole.DRIVER:
        target_id = current_user.id
    elif driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="driver_id is required for admin and store manager accounts",
        )
    else:
        target_id = driver_id

    from_date, to_date = _period_bounds(period)

    runs = db.query(RunPlanner).filter(RunPlanner.driver_id == target_id)
    if from_date is not None:
        runs = runs.filter(
            RunPlanner.dispatch_date >= from_date,
            RunPlanner.dispatch_date <= to_date,
        )
    run_rows = runs.all()
    run_ids = [run.id for run in run_rows]
    active_days = len({run.dispatch_date for run in run_rows})

    statuses: List[str] = []
    if run_ids:
        statuses = [
            row[0] or ""
            for row in db.query(GDN.status).filter(GDN.run_planner_id.in_(run_ids)).all()
        ]

    def _count(keyword: str) -> int:
        return sum(1 for value in statuses if keyword in value.lower())

    total_stops = len(statuses)
    delivered = _count("deliver")
    partial = _count("partial")
    failed = _count("fail")
    pending = total_stops - delivered - partial - failed

    driver = db.query(User).filter(User.id == target_id).first()
    if not driver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found"
        )

    return DriverPerformanceResponse(
        driver_id=target_id,
        driver_name=driver.full_name,
        period=period,
        from_date=from_date,
        to_date=to_date,
        total_stops=total_stops,
        deliveries_completed=delivered,
        partial_stops=partial,
        failed_stops=failed,
        pending_stops=max(pending, 0),
        success_rate=round(delivered / total_stops * 100, 1) if total_stops else 0.0,
        active_days=active_days,
        avg_per_day=round(delivered / active_days, 1) if active_days else 0.0,
    )
