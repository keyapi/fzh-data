"""Internal package-domain models.

External Sellfox camelCase fields are converted to snake_case before these
models enter the service or persistence layers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SellfoxPackageAddress(BaseModel):
    name: str = ""
    company: str = ""
    address_line_1: str = ""
    address_line_2: str = ""
    city: str = ""
    state_or_region: str = ""
    postal_code: str = ""
    country: str = ""
    country_code: str = ""
    phone: str = ""
    mobile: str = ""
    email: str = ""


class SellfoxPackageLogistics(BaseModel):
    warehouse_name: str = ""
    channel_name: str = ""
    tracking_number: str = ""
    forward_number: str = ""
    estimated_cost: float = 0.0
    currency: str = ""
    weight_grams: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0


class SellfoxPackageOrderRecord(BaseModel):
    external_order_id: str
    order_status: str = ""
    purchase_date: datetime | None = None
    earliest_ship_date: datetime | None = None
    latest_ship_date: datetime | None = None
    order_total: float = 0.0
    currency: str = ""


class SellfoxPackageItemRecord(BaseModel):
    external_order_id: str
    order_item_id: str
    seller_sku: str = ""
    commodity_sku: str = ""
    quantity: int = 0
    main_image: str = ""
    variation: str = ""


class SellfoxPackageRecord(BaseModel):
    account_key: str
    package_sn: str
    source_row_index: int = 0
    shop_id: str = ""
    shop_name: str = ""
    platform_name: str = ""
    marketplace: str = ""
    package_status: str = ""
    local_review_status: str = "pending"
    address: SellfoxPackageAddress = Field(default_factory=SellfoxPackageAddress)
    logistics: SellfoxPackageLogistics = Field(
        default_factory=SellfoxPackageLogistics
    )
    orders: list[SellfoxPackageOrderRecord] = Field(default_factory=list)
    items: list[SellfoxPackageItemRecord] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PackageRowError(BaseModel):
    row_index: int
    package_sn: str = ""
    reason: str


class SellfoxPackagePage(BaseModel):
    page_no: int
    page_size: int
    total_size: int
    records: list[SellfoxPackageRecord] = Field(default_factory=list)
    errors: list[PackageRowError] = Field(default_factory=list)


class PackageListItem(BaseModel):
    account_key: str
    package_sn: str
    package_status: str = ""
    local_review_status: str = "pending"
    channel_name: str = ""
    shop_name: str = ""
    marketplace: str = ""
    tracking_number: str = ""
    order_count: int = 0
    item_count: int = 0
    fetched_at: datetime | None = None
    purchase_date: datetime | None = None
    label_created_at: datetime | None = None


class PackageListResult(BaseModel):
    total: int
    items: list[PackageListItem] = Field(default_factory=list)


class AuditEventRecord(BaseModel):
    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str
    summary: str = ""
    created_at: datetime
