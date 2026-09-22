from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GDNLineItem(BaseModel):
    item_description: str = Field(..., min_length=1, max_length=500)
    qty: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=50)
    unit_price: float = Field(..., ge=0)
    line_total: float = Field(..., ge=0)


class GDNBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255)
    site_name: str = Field(..., min_length=1, max_length=255)
    materials_description_summary: Optional[str] = Field(None, max_length=1000)
    invoice_date: date
    line_items: List[GDNLineItem] = Field(..., min_length=1)
    payment_status: str = Field("Pending", min_length=1, max_length=50)
    status: Optional[str] = Field("Pending", min_length=1, max_length=100)
    gdn_reference: str = Field(..., min_length=1, max_length=100)
    loaded_at: Optional[datetime] = None
    loading_dock: Optional[str] = Field(None, max_length=100)
    pallets_count: Optional[int] = Field(None, ge=0)
    transporter_name: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def validate_line_totals(self):
        for item in self.line_items:
            expected_total = item.qty * item.unit_price
            if abs(item.line_total - expected_total) > 0.01:
                raise ValueError(
                    f"line_total for '{item.item_description}' must equal qty * unit_price"
                )
        return self


class GDNCreate(GDNBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_name": "ABC Trading LLC",
                "site_name": "Dubai Central Site",
                "materials_description_summary": "Construction materials",
                "invoice_date": "2026-09-22",
                "line_items": [
                    {
                        "item_description": "Cement Bags",
                        "qty": 10,
                        "unit": "Bags",
                        "unit_price": 25.5,
                        "line_total": 255.0,
                    }
                ],
                "payment_status": "Pending",
                "status": "GDN Loaded",
                "gdn_reference": "GDN-2026-0001",
                "loaded_at": "2026-09-22T10:30:00Z",
                "loading_dock": "Dock A-02",
                "pallets_count": 2,
                "transporter_name": "ABC Transport",
            }
        }
    )


class GDNUpdate(BaseModel):
    customer_name: Optional[str] = Field(None, min_length=1, max_length=255)
    site_name: Optional[str] = Field(None, min_length=1, max_length=255)
    materials_description_summary: Optional[str] = Field(None, max_length=1000)
    invoice_date: Optional[date] = None
    line_items: Optional[List[GDNLineItem]] = Field(None, min_length=1)
    payment_status: Optional[str] = Field(None, min_length=1, max_length=50)
    status: Optional[str] = Field(None, min_length=1, max_length=100)
    gdn_reference: Optional[str] = Field(None, min_length=1, max_length=100)
    loaded_at: Optional[datetime] = None
    loading_dock: Optional[str] = Field(None, max_length=100)
    pallets_count: Optional[int] = Field(None, ge=0)
    transporter_name: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def validate_line_totals(self):
        if self.line_items is not None:
            for item in self.line_items:
                expected_total = item.qty * item.unit_price
                if abs(item.line_total - expected_total) > 0.01:
                    raise ValueError(
                        f"line_total for '{item.item_description}' must equal qty * unit_price"
                    )
        return self


class GDNResponse(GDNBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class GDNStats(BaseModel):
    total_invoices: int
    gdns_created: int
    pending_invoices: int
    delivered_gdns: int
    loaded_gdns: int


class GDNListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    stats: GDNStats
    items: List[GDNResponse]
