from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InventoryQuery(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=100)
    mode: str = "snapshot"


class InboundQuery(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=100)


class TransactionQuery(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None
    sku: str | None = Field(default=None, max_length=200)


class InventoryTransaction(BaseModel):
    event_date: datetime | None = None
    adjustment_type: str | None = None
    sku: str | None = None
    quantity: int | None = None
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    description: str | None = None


class TransactionResponse(BaseModel):
    items: list[InventoryTransaction]
    meta: ResponseMeta


class InventoryWarehouse(BaseModel):
    warehouse_id: int | None = None
    warehouse_name: str | None = None


class WarehouseResponse(BaseModel):
    items: list[InventoryWarehouse]
    meta: ResponseMeta


class InventoryItem(BaseModel):
    sku: str
    wayfair_sku: str | None = None
    warehouse: str
    available: int | None = None
    on_hand: int | None = None
    reserved: int | None = None
    unavailable: int | None = None


class ResponseMeta(BaseModel):
    account: str
    source: str
    fetched_at: datetime
    age_seconds: int
    stale: bool
    snapshot_run_id: str | None = None


class InventoryResponse(BaseModel):
    items: list[InventoryItem]
    meta: ResponseMeta
