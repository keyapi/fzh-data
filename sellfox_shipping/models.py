"""Pydantic data models for sellfox_shipping.

Unified models for orders, addresses, packages, labels, and carrier
requests — shared by FastAPI REST, FastMCP tools, and Typer CLI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────

class PackageStatus(str, Enum):
    TO_AUDIT = "to_audit"
    TO_PROCESS = "to_process"
    APPLY_TRACK_NO = "apply_track_no"
    TO_PRINT = "to_print"
    HAS_SHIPPED = "has_shipped"
    HAS_CANCELED = "has_canceled"


class LabelFormat(str, Enum):
    ZPL = "ZPL"
    PDF = "PDF"
    PNG = "PNG"


# ── Address ────────────────────────────────────────────────────────

class Address(BaseModel):
    name: str = ""
    company: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""
    country_code: str = ""
    phone: str = ""
    email: str = ""


# ── Order & Package ────────────────────────────────────────────────

class OrderItem(BaseModel):
    order_item_id: str = ""
    seller_sku: str = ""
    commodity_sku: str = ""
    commodity_name: str = ""
    asin: str = ""
    quantity: int = 0
    main_image: str = ""
    variation: str = ""


class Order(BaseModel):
    id: Optional[int] = None
    amazon_order_id: str = ""
    seller_order_id: str = ""
    package_sn: str = ""
    shop_id: str = ""
    shop_name: str = ""
    platform: str = "Amazon"
    marketplace: str = ""
    order_status: str = ""
    package_status: PackageStatus = PackageStatus.TO_AUDIT
    purchase_date: Optional[datetime] = None
    earliest_ship_date: Optional[datetime] = None
    latest_ship_date: Optional[datetime] = None
    order_total: float = 0.0
    currency: str = "USD"
    shipping_address: Address = Field(default_factory=Address)
    items: list[OrderItem] = Field(default_factory=list)
    raw_json: str = ""
    fetched_at: Optional[datetime] = None


# ── Shipping ───────────────────────────────────────────────────────

class Package(BaseModel):
    weight_kg: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0


class ShipmentRequest(BaseModel):
    order: Order
    carrier: str = ""
    service_level: str = ""
    packages: list[Package] = Field(default_factory=list)
    idempotency_key: str = ""


class Label(BaseModel):
    id: Optional[int] = None
    order_id: Optional[int] = None
    package_sn: str = ""
    carrier: str = ""
    service_level: str = ""
    tracking_number: str = ""
    forward_number: str = ""
    label_format: LabelFormat = LabelFormat.PDF
    label_path: str = ""
    label_data: bytes = b""
    cost: float = 0.0
    currency: str = "USD"
    status: str = "generated"
    carrier_response_json: str = ""
    created_at: Optional[datetime] = None


class Rate(BaseModel):
    carrier: str
    service_level: str
    service_name: str = ""
    total_charge: float = 0.0
    currency: str = "USD"
    transit_days: int = 0
    estimated_delivery: Optional[datetime] = None


class TrackingInfo(BaseModel):
    tracking_number: str
    carrier: str
    status: str = ""
    status_description: str = ""
    estimated_delivery: Optional[datetime] = None
    events: list[dict] = Field(default_factory=list)
