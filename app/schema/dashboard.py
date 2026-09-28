from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MetricItem(BaseModel):
    value: int
    subtitle: str
    trend: Optional[str] = None


class FleetUtilizationMetric(BaseModel):
    active_vehicles: int
    total_vehicles: int
    utilization_percentage: float
    ratio_display: str
    subtitle: str


class DeliveredTodayMetric(BaseModel):
    value: int
    on_time_rate: float
    subtitle: str


class DashboardMetrics(BaseModel):
    active_deliveries: MetricItem
    gdns_ready: MetricItem
    fleet_utilization: FleetUtilizationMetric
    delivered_today: DeliveredTodayMetric
    exceptions: MetricItem


class LiveStatusBreakdown(BaseModel):
    loading_yard_trucks: int
    in_transit_trucks: int
    at_site_trucks: int
    live_telemetry: bool = True


class ActiveDeliveryTableRow(BaseModel):
    id: int
    gdn_reference: str
    truck_code: Optional[str] = None
    commercial_plate: Optional[str] = None
    destination_site: str
    destination_area: Optional[str] = None
    materials: Optional[str] = None
    status: str
    eta: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DriverLeaderboardItem(BaseModel):
    driver_id: int
    driver_name: str
    initials: str
    avatar_url: Optional[str] = None
    truck_code: Optional[str] = None
    truck_type: Optional[str] = None
    truck_display: str
    completed_deliveries: int
    total_deliveries: int
    deliveries_ratio: str
    on_time_rate: str
    pod_photos_count: int
    pod_photos_label: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class TopClientAccountItem(BaseModel):
    client_name: str
    site_name: Optional[str] = None
    account_display: str
    drops_count: int
    materials_summary: Optional[str] = None
    subtitle: str
    acceptance_rate: str
    gdns_count_label: str

    model_config = ConfigDict(from_attributes=True)


class RecentDeliveryCard(BaseModel):
    id: int
    gdn_reference: str
    badge_status: str
    location_tag: str
    photo_url: Optional[str] = None
    driver_name: str
    time_ago: str
    title: str
    description: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class RecentDeliveriesResponse(BaseModel):
    items: List[RecentDeliveryCard]
    available_sites: List[str] = Field(default_factory=list)
    total: int


class ManifestItemDetail(BaseModel):
    description: str
    qty: float
    unit: str
    unit_price: float = 0.0
    line_total: float = 0.0
    badge: str


class PhotoEvidenceDetail(BaseModel):
    primary_photo_url: Optional[str] = None
    all_photos: List[str] = Field(default_factory=list)
    location_tag: str
    is_geotagged: bool = True
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class EpodSignatureDetail(BaseModel):
    is_signed: bool = True
    signer_name: str
    signer_role: str
    signed_at: str
    status: str = "Signed & accepted"
    signature_url: Optional[str] = None


class DeliveryDetailResponse(BaseModel):
    id: int
    gdn_reference: str
    verification_badge: str
    is_verified: bool
    title: str
    subtitle: str
    driver_name: str
    driver_phone: Optional[str] = None
    truck_display: str
    site_name: str
    offload_time: str
    weight_display: str
    reference: str
    manifest_items: List[ManifestItemDetail] = Field(default_factory=list)
    total_manifest_items: int
    photo_evidence: PhotoEvidenceDetail
    epod_signature: EpodSignatureDetail
    manifest_pdf_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StoreManagerDashboardResponse(BaseModel):
    metrics: DashboardMetrics
    status_breakdown: LiveStatusBreakdown
    deliveries_table: List[ActiveDeliveryTableRow]
    driver_leaderboard: List[DriverLeaderboardItem] = Field(default_factory=list)
    top_clients: List[TopClientAccountItem] = Field(default_factory=list)
    total_fleet_audit_count: int = 0
    total_active_deliveries: int
    skip: int = 0
    limit: int = 50


class DriverPerformanceResponse(BaseModel):
    """Delivery performance for a single driver over a date window."""

    driver_id: int
    driver_name: Optional[str] = None
    period: str
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    total_stops: int
    deliveries_completed: int
    partial_stops: int
    failed_stops: int
    pending_stops: int
    success_rate: float
    active_days: int
    avg_per_day: float
