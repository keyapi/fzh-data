"""SQLAlchemy persistence for the package-centric workflow."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    event,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from sellfox_shipping.carriers.lizard.dims import CartonDims
from sellfox_shipping.package_models import (
    AuditEventRecord,
    PackageListItem,
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)


class Base(DeclarativeBase):
    pass


class ShippingAccountRow(Base):
    __tablename__ = "shipping_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_key: Mapped[str] = mapped_column(String, unique=True)


class OrderRow(Base):
    __tablename__ = "shipping_orders"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "external_order_id",
            name="uq_shipping_order_account_external",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    external_order_id: Mapped[str] = mapped_column(String)
    order_status: Mapped[str] = mapped_column(String, default="")
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    earliest_ship_date: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    latest_ship_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    order_total: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String, default="")


class PackageRow(Base):
    __tablename__ = "shipping_packages"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "package_sn",
            name="uq_shipping_package_account_sn",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    package_sn: Mapped[str] = mapped_column(String)
    shop_id: Mapped[str] = mapped_column(String, default="")
    shop_name: Mapped[str] = mapped_column(String, default="")
    platform_name: Mapped[str] = mapped_column(String, default="")
    marketplace: Mapped[str] = mapped_column(String, default="")
    package_status: Mapped[str] = mapped_column(String, default="")
    local_review_status: Mapped[str] = mapped_column(String, default="pending")
    address_name: Mapped[str] = mapped_column(String, default="")
    address_company: Mapped[str] = mapped_column(String, default="")
    address_line_1: Mapped[str] = mapped_column(String, default="")
    address_line_2: Mapped[str] = mapped_column(String, default="")
    address_city: Mapped[str] = mapped_column(String, default="")
    address_state_or_region: Mapped[str] = mapped_column(String, default="")
    address_postal_code: Mapped[str] = mapped_column(String, default="")
    address_country: Mapped[str] = mapped_column(String, default="")
    address_country_code: Mapped[str] = mapped_column(String, default="")
    address_phone: Mapped[str] = mapped_column(String, default="")
    address_mobile: Mapped[str] = mapped_column(String, default="")
    address_email: Mapped[str] = mapped_column(String, default="")
    warehouse_name: Mapped[str] = mapped_column(String, default="")
    channel_name: Mapped[str] = mapped_column(String, default="")
    tracking_number: Mapped[str] = mapped_column(String, default="")
    forward_number: Mapped[str] = mapped_column(String, default="")
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    cost_currency: Mapped[str] = mapped_column(String, default="")
    weight_grams: Mapped[float] = mapped_column(Float, default=0)
    length_cm: Mapped[float] = mapped_column(Float, default=0)
    width_cm: Mapped[float] = mapped_column(Float, default=0)
    height_cm: Mapped[float] = mapped_column(Float, default=0)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class PackageOrderRow(Base):
    __tablename__ = "shipping_package_orders"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "order_id",
            name="uq_shipping_package_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE")
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_orders.id", ondelete="CASCADE")
    )


class PackageItemRow(Base):
    __tablename__ = "shipping_package_items"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "order_item_id",
            name="uq_shipping_package_item",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE")
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipping_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_order_id: Mapped[str] = mapped_column(String, default="")
    order_item_id: Mapped[str] = mapped_column(String)
    seller_sku: Mapped[str] = mapped_column(String, default="")
    commodity_sku: Mapped[str] = mapped_column(String, default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    main_image: Mapped[str] = mapped_column(String, default="")
    variation: Mapped[str] = mapped_column(String, default="")


class AuditEventRow(Base):
    __tablename__ = "shipping_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class CartonOverrideRow(Base):
    __tablename__ = "shipping_carton_overrides"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "commodity_sku",
            name="uq_shipping_carton_override_account_sku",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    commodity_sku: Mapped[str] = mapped_column(String)
    weight_kg: Mapped[float] = mapped_column(Float, default=0)
    length_cm: Mapped[float] = mapped_column(Float, default=0)
    width_cm: Mapped[float] = mapped_column(Float, default=0)
    height_cm: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(String, default="")
    item_name: Mapped[str] = mapped_column(String, default="")
    updated_by: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


@dataclass(frozen=True)
class CartonOverrideRecord:
    account_key: str
    commodity_sku: str
    dims: CartonDims
    note: str = ""
    updated_by: str = ""
    item_name: str = ""


@dataclass(frozen=True)
class ArtifactRecord:
    id: int
    account_key: str
    kind: str
    file_name: str
    content_hash: str
    storage_relpath: str
    mime_type: str = ""
    file_size: int = 0
    template_version: str = ""
    virtual_folder: str = ""
    summary: str = ""
    created_by: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class ShippingBatchRecord:
    id: int
    account_key: str
    adapter: str
    status: str
    template_version: str = ""
    created_by: str = ""
    export_artifact_id: int | None = None
    import_artifact_id: int | None = None
    input_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    unmatched_count: int = 0
    summary: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class BatchPackageRecord:
    batch_id: int
    package_sn: str
    status: str
    reason: str = ""


class ArtifactRow(Base):
    __tablename__ = "shipping_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String)
    file_name: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    storage_relpath: Mapped[str] = mapped_column(String)
    mime_type: Mapped[str] = mapped_column(String, default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    template_version: Mapped[str] = mapped_column(String, default="")
    virtual_folder: Mapped[str] = mapped_column(String, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class ShippingBatchRow(Base):
    __tablename__ = "shipping_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    adapter: Mapped[str] = mapped_column(String, default="lizard")
    status: Mapped[str] = mapped_column(String, default="exported")
    template_version: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    export_artifact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    import_artifact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class BatchPackageRow(Base):
    __tablename__ = "shipping_batch_packages"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "package_sn",
            name="uq_shipping_batch_package",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_batches.id", ondelete="CASCADE")
    )
    package_sn: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="exported")
    reason: Mapped[str] = mapped_column(String, default="")


class SubmissionScopeRow(Base):
    __tablename__ = "shipping_submission_scopes"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "package_id",
            "order_id",
            name="uq_shipping_submission_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE")
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_orders.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class SubmissionIntentRow(Base):
    __tablename__ = "shipping_submission_intents"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE")
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_orders.id", ondelete="CASCADE")
    )
    scope_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_submission_scopes.id", ondelete="CASCADE")
    )
    external_order_id: Mapped[str] = mapped_column(String, default="")
    request_hash: Mapped[str] = mapped_column(String, unique=True)
    canonical_request: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="READY")
    version: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class SubmissionAttemptRow(Base):
    __tablename__ = "shipping_submission_attempts"
    __table_args__ = (
        UniqueConstraint(
            "intent_id",
            "attempt_no",
            name="uq_shipping_submission_attempt_no",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    intent_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_submission_intents.id", ondelete="CASCADE")
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="CREATED")
    send_state: Mapped[str] = mapped_column(String, default="NOT_SENT")
    actor: Mapped[str] = mapped_column(String, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


@dataclass(frozen=True)
class SubmissionIntentRecord:
    id: int
    account_key: str
    package_id: int
    order_db_id: int
    external_order_id: str
    request_hash: str
    canonical_request: str
    status: str
    version: int
    confirmed_by: str = ""


@dataclass(frozen=True)
class SubmissionAttemptRecord:
    id: int
    intent_id: int
    attempt_no: int
    status: str
    send_state: str
    actor: str = ""
    http_status: int | None = None
    http_summary: str = ""


@dataclass(frozen=True)
class UpsertOutcome:
    package_id: int
    created: bool


@dataclass(frozen=True)
class PackageDimsRecord:
    package_id: int
    weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    sku_count: int
    computed_at: datetime | None = None


@dataclass(frozen=True)
class PackageRoutingRecord:
    package_id: int
    carrier: str
    label: str
    reason: str
    rule_name: str
    matched: bool
    computed_at: datetime | None = None


class PackageDimsRow(Base):
    __tablename__ = "shipping_package_dims"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE"),
        unique=True,
    )
    weight_kg: Mapped[float] = mapped_column(Float, default=0)
    length_cm: Mapped[float] = mapped_column(Float, default=0)
    width_cm: Mapped[float] = mapped_column(Float, default=0)
    height_cm: Mapped[float] = mapped_column(Float, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class PackageRoutingRow(Base):
    __tablename__ = "shipping_package_routing"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE"),
        unique=True,
    )
    carrier: Mapped[str] = mapped_column(String, default="")
    label: Mapped[str] = mapped_column(String, default="")
    reason: Mapped[str] = mapped_column(String, default="")
    rule_name: Mapped[str] = mapped_column(String, default="")
    matched: Mapped[bool] = mapped_column(default=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class PackageRateRow(Base):
    """One row per rate fetch — not unique on package_id, preserves history."""

    __tablename__ = "shipping_package_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE"),
    )
    carrier: Mapped[str] = mapped_column(String, default="")
    service: Mapped[str] = mapped_column(String, default="")
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    billing_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    zone: Mapped[str] = mapped_column(String, default="")
    channel: Mapped[str] = mapped_column(String, default="")
    max_side_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_lb: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_fedex: Mapped[bool] = mapped_column(default=False)
    address_type: Mapped[str] = mapped_column(String, default="")
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


@dataclass(frozen=True)
class PackageRateRecord:
    id: int
    package_id: int
    carrier: str
    service: str
    total_amount: float | None
    currency: str
    billing_weight: float | None
    zone: str
    channel: str
    max_side_in: float | None
    weight_lb: float | None
    is_fedex: bool
    address_type: str = ""
    raw_data: str | None = None
    fetched_at: datetime | None = None


class ShippingLabelRow(Base):
    """One row per label creation attempt — not unique, preserves history."""

    __tablename__ = "shipping_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE"),
    )
    carrier: Mapped[str] = mapped_column(String, default="")
    service_level: Mapped[str] = mapped_column(String, default="")
    tracking_number: Mapped[str] = mapped_column(String, default="")
    carrier_order_id: Mapped[str] = mapped_column(String, default="")
    request_id: Mapped[str] = mapped_column(String, default="")
    label_url: Mapped[str] = mapped_column(Text, default="")
    operation_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipping_label_operations.id", ondelete="SET NULL"),
        nullable=True,
    )
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipping_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    label_format: Mapped[str] = mapped_column(String, default="PDF")
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    status: Mapped[str] = mapped_column(String, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    carrier_response_json: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


@dataclass(frozen=True)
class ShippingLabelRecord:
    id: int
    account_key: str
    package_id: int
    carrier: str
    service_level: str
    tracking_number: str
    carrier_order_id: str
    request_id: str
    label_url: str
    operation_id: int | None
    artifact_id: int | None
    label_format: str
    total_amount: float | None
    currency: str
    status: str
    is_active: bool
    carrier_response_json: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


ACTIVE_LABEL_OPERATION_STATUSES = {
    "RESERVED",
    "SENT",
    "ACCEPTED",
    "LABEL_PENDING",
    "UNKNOWN_BLOCKED",
}

# SUCCEEDED / FAILED_* / CANCELLED are terminal for the unique active-op index.
# SUCCEEDED is "done with an active label", not an in-flight claim slot.
ALLOWED_LABEL_OPERATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "RESERVED": frozenset({"SENT", "FAILED_SAFE", "CANCELLED"}),
    "SENT": frozenset(
        {"ACCEPTED", "SUCCEEDED", "FAILED_SAFE", "FAILED_FINAL", "UNKNOWN_BLOCKED"}
    ),
    "ACCEPTED": frozenset(
        {"LABEL_PENDING", "SUCCEEDED", "FAILED_FINAL", "UNKNOWN_BLOCKED", "CANCELLED"}
    ),
    "LABEL_PENDING": frozenset(
        {
            "LABEL_PENDING",
            "SUCCEEDED",
            "FAILED_FINAL",
            "UNKNOWN_BLOCKED",
            "CANCELLED",
        }
    ),
    "SUCCEEDED": frozenset({"CANCELLED"}),
    "FAILED_SAFE": frozenset(),
    "FAILED_FINAL": frozenset(),
    "UNKNOWN_BLOCKED": frozenset(),
    "CANCELLED": frozenset(),
}


class LabelOperationRow(Base):
    """One logical carrier create-label operation with recovery state."""

    __tablename__ = "shipping_label_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_packages.id", ondelete="CASCADE")
    )
    generation: Mapped[int] = mapped_column(Integer)
    carrier: Mapped[str] = mapped_column(String, default="")
    service_level: Mapped[str] = mapped_column(String, default="")
    idempotency_key: Mapped[str] = mapped_column(String, default="")
    request_hash: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="RESERVED")
    provider_order_id: Mapped[str] = mapped_column(String, default="")
    tracking_number: Mapped[str] = mapped_column(String, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str] = mapped_column(String, default="")
    error_summary: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


@dataclass(frozen=True)
class LabelOperationRecord:
    id: int
    account_key: str
    package_id: int
    generation: int
    carrier: str
    service_level: str
    idempotency_key: str
    request_hash: str
    status: str
    provider_order_id: str
    tracking_number: str
    attempt_count: int
    error_class: str
    error_summary: str
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PackageRepository:
    """Persist normalized package snapshots with account-scoped uniqueness."""

    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _initialize_sqlite(path)
        from sellfox_shipping.schema import upgrade_schema

        upgrade_schema(path)
        self.engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _configure_sqlite)
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self._db_path = path
        self.artifacts_root = path.parent / "artifacts"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def upsert(self, record: SellfoxPackageRecord) -> UpsertOutcome:
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, record.account_key)
            package = session.scalar(
                select(PackageRow).where(
                    PackageRow.account_id == account.id,
                    PackageRow.package_sn == record.package_sn,
                )
            )
            if package is None:
                result = session.execute(
                    sqlite_insert(PackageRow)
                    .values(
                        account_id=account.id,
                        package_sn=record.package_sn,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["account_id", "package_sn"]
                    )
                )
                created = result.rowcount == 1
                package = session.scalar(
                    select(PackageRow).where(
                        PackageRow.account_id == account.id,
                        PackageRow.package_sn == record.package_sn,
                    )
                )
                if package is None:
                    raise RuntimeError("package upsert did not return a row")
            else:
                created = False

            self._apply_package_fields(package, record)
            order_rows = self._upsert_orders(session, account.id, record)

            session.execute(
                delete(PackageOrderRow).where(
                    PackageOrderRow.package_id == package.id
                )
            )
            session.execute(
                delete(PackageItemRow).where(PackageItemRow.package_id == package.id)
            )
            for order in order_rows.values():
                session.add(
                    PackageOrderRow(
                        package_id=package.id,
                        order_id=order.id,
                    )
                )
            unique_items = {
                item.order_item_id: item
                for item in record.items
            }
            for item in unique_items.values():
                order = order_rows.get(item.external_order_id)
                session.add(
                    PackageItemRow(
                        package_id=package.id,
                        order_id=order.id if order else None,
                        external_order_id=item.external_order_id,
                        order_item_id=item.order_item_id,
                        seller_sku=item.seller_sku,
                        commodity_sku=item.commodity_sku,
                        quantity=item.quantity,
                        main_image=item.main_image,
                        variation=item.variation,
                    )
                )

            package_id = package.id
        return UpsertOutcome(package_id=package_id, created=created)

    def get(
        self,
        account_key: str,
        package_sn: str,
    ) -> SellfoxPackageRecord | None:
        with self._session_factory() as session:
            package = session.scalar(
                select(PackageRow)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
            )
            if package is None:
                return None

            order_rows = session.scalars(
                select(OrderRow)
                .join(
                    PackageOrderRow,
                    PackageOrderRow.order_id == OrderRow.id,
                )
                .where(PackageOrderRow.package_id == package.id)
                .order_by(OrderRow.external_order_id)
            ).all()
            item_rows = session.scalars(
                select(PackageItemRow)
                .where(PackageItemRow.package_id == package.id)
                .order_by(PackageItemRow.order_item_id)
            ).all()
            return self._to_record(account_key, package, order_rows, item_rows)

    def set_local_review_status(
        self,
        *,
        account_key: str,
        package_sn: str,
        local_review_status: str,
    ) -> SellfoxPackageRecord:
        with self._session_factory.begin() as session:
            package = session.scalar(
                select(PackageRow)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
            )
            if package is None:
                raise LookupError(f"Package {package_sn} not found")
            package.local_review_status = local_review_status
            order_rows = session.scalars(
                select(OrderRow)
                .join(
                    PackageOrderRow,
                    PackageOrderRow.order_id == OrderRow.id,
                )
                .where(PackageOrderRow.package_id == package.id)
                .order_by(OrderRow.external_order_id)
            ).all()
            item_rows = session.scalars(
                select(PackageItemRow)
                .where(PackageItemRow.package_id == package.id)
                .order_by(PackageItemRow.order_item_id)
            ).all()
            return self._to_record(account_key, package, order_rows, item_rows)

    def set_tracking_number(
        self,
        *,
        account_key: str,
        package_sn: str,
        tracking_number: str,
        estimated_cost: float | None = None,
        cost_currency: str | None = None,
    ) -> SellfoxPackageRecord:
        with self._session_factory.begin() as session:
            package = session.scalar(
                select(PackageRow)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
            )
            if package is None:
                raise LookupError(f"Package {package_sn} not found")
            package.tracking_number = tracking_number
            if estimated_cost is not None:
                package.estimated_cost = estimated_cost
            if cost_currency is not None:
                package.cost_currency = cost_currency
            order_rows = session.scalars(
                select(OrderRow)
                .join(
                    PackageOrderRow,
                    PackageOrderRow.order_id == OrderRow.id,
                )
                .where(PackageOrderRow.package_id == package.id)
                .order_by(OrderRow.external_order_id)
            ).all()
            item_rows = session.scalars(
                select(PackageItemRow)
                .where(PackageItemRow.package_id == package.id)
                .order_by(PackageItemRow.order_item_id)
            ).all()
            return self._to_record(account_key, package, order_rows, item_rows)

    def get_carton_override(
        self, account_key: str, commodity_sku: str
    ) -> CartonOverrideRecord | None:
        sku = (commodity_sku or "").strip()
        if not sku:
            return None
        with self._session_factory() as session:
            row = session.scalar(
                select(CartonOverrideRow)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == CartonOverrideRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    CartonOverrideRow.commodity_sku == sku,
                )
            )
            if row is None:
                return None
            return CartonOverrideRecord(
                account_key=account_key,
                commodity_sku=row.commodity_sku,
                dims=CartonDims(
                    weight_kg=float(row.weight_kg or 0),
                    length_cm=float(row.length_cm or 0),
                    width_cm=float(row.width_cm or 0),
                    height_cm=float(row.height_cm or 0),
                ),
                note=row.note or "",
                updated_by=row.updated_by or "",
                item_name=row.item_name or "",
            )

    def set_carton_override(
        self,
        *,
        account_key: str,
        commodity_sku: str,
        dims: CartonDims,
        actor: str,
        note: str = "",
    ) -> CartonOverrideRecord:
        sku = (commodity_sku or "").strip()
        if not sku:
            raise ValueError("commodity_sku is required")
        if not dims.is_complete:
            raise ValueError("dims must be complete (weight and L/W/H > 0)")
        actor_name = (actor or "").strip()
        if not actor_name:
            raise ValueError("actor is required")
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(CartonOverrideRow).where(
                    CartonOverrideRow.account_id == account.id,
                    CartonOverrideRow.commodity_sku == sku,
                )
            )
            if row is None:
                row = CartonOverrideRow(
                    account_id=account.id,
                    commodity_sku=sku,
                )
                session.add(row)
            row.weight_kg = dims.weight_kg
            row.length_cm = dims.length_cm
            row.width_cm = dims.width_cm
            row.height_cm = dims.height_cm
            row.note = note or ""
            row.updated_by = actor_name
            row.updated_at = datetime.now(timezone.utc)
        self.append_audit_event(
            actor=actor_name,
            action="lizard.carton_override",
            entity_type="commodity_sku",
            entity_id=sku,
            summary=(
                f"{dims.weight_kg}kg {dims.length_cm}x{dims.width_cm}x{dims.height_cm}cm"
            ),
        )
        record = self.get_carton_override(account_key, sku)
        assert record is not None
        return record

    def upsert_carton_item_name(
        self,
        *,
        account_key: str,
        commodity_sku: str,
        item_name: str,
    ) -> None:
        """Persist item_name for a commodity_sku without requiring dims."""
        sku = (commodity_sku or "").strip()
        if not sku:
            return
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(CartonOverrideRow).where(
                    CartonOverrideRow.account_id == account.id,
                    CartonOverrideRow.commodity_sku == sku,
                )
            )
            if row is None:
                row = CartonOverrideRow(
                    account_id=account.id,
                    commodity_sku=sku,
                )
                session.add(row)
            row.item_name = item_name or ""

    def register_artifact(
        self,
        *,
        account_key: str,
        kind: str,
        file_name: str,
        content: bytes,
        actor: str,
        template_version: str = "",
        virtual_folder: str = "",
        mime_type: str = "",
        summary: str = "",
    ) -> ArtifactRecord:
        """Register a file artifact; physical bytes deduped by content_hash.

        Like ERPNext File: same content_hash → one blob on disk; multiple
        artifact rows may use different file_name / virtual_folder.
        """
        kind_s = (kind or "").strip()
        name = Path(file_name or "unnamed.bin").name
        actor_s = (actor or "").strip()
        if not kind_s:
            raise ValueError("kind is required")
        if not actor_s:
            raise ValueError("actor is required")
        if not content:
            raise ValueError("content is empty")
        digest = hashlib.md5(content, usedforsecurity=False).hexdigest()
        mime = mime_type or _guess_mime(name)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            # Reuse blob path if this content_hash already stored (ERPNext-like dedup).
            prior = session.scalar(
                select(ArtifactRow)
                .where(
                    ArtifactRow.account_id == account.id,
                    ArtifactRow.content_hash == digest,
                )
                .limit(1)
            )
            if prior is not None:
                relpath = prior.storage_relpath
            else:
                relpath = _flat_private_relpath(name, digest)
                blob_path = self.artifacts_root / relpath
                blob_path.parent.mkdir(parents=True, exist_ok=True)
                if not blob_path.exists():
                    blob_path.write_bytes(content)
            row = ArtifactRow(
                account_id=account.id,
                kind=kind_s,
                file_name=name,
                content_hash=digest,
                storage_relpath=relpath.replace("\\", "/"),
                mime_type=mime,
                file_size=len(content),
                template_version=template_version or "",
                virtual_folder=virtual_folder or "",
                summary=summary or "",
                created_by=actor_s,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.flush()
            artifact_id = int(row.id)
        self.append_audit_event(
            actor=actor_s,
            action="artifacts.register",
            entity_type="artifact",
            entity_id=str(artifact_id),
            summary=f"{kind_s} {name} md5={digest[:12]}…",
        )
        record = self.get_artifact(artifact_id)
        assert record is not None
        return record

    def get_artifact(self, artifact_id: int) -> ArtifactRecord | None:
        with self._session_factory() as session:
            row = session.get(ArtifactRow, artifact_id)
            if row is None:
                return None
            account = session.get(ShippingAccountRow, row.account_id)
            return _artifact_to_record(account.account_key if account else "", row)

    def resolve_artifact_path(self, artifact: ArtifactRecord) -> Path:
        return self.artifacts_root / artifact.storage_relpath

    def list_artifacts(
        self,
        *,
        account_key: str,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ArtifactRecord]:
        with self._session_factory() as session:
            query = (
                select(ArtifactRow, ShippingAccountRow.account_key)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == ArtifactRow.account_id,
                )
                .where(ShippingAccountRow.account_key == account_key)
                .order_by(ArtifactRow.id.desc())
                .offset(offset)
                .limit(limit)
            )
            if kind is not None:
                query = query.where(ArtifactRow.kind == kind)
            rows = session.execute(query).all()
            return [_artifact_to_record(ak, row) for row, ak in rows]

    def create_export_batch(
        self,
        *,
        account_key: str,
        actor: str,
        template_version: str,
        export_artifact_id: int | None,
        exported_package_sns: list[str],
        skipped_rows: list[dict],
        summary: str = "",
    ) -> ShippingBatchRecord:
        actor_s = (actor or "").strip()
        if not actor_s:
            raise ValueError("actor is required")
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            batch = ShippingBatchRow(
                account_id=account.id,
                adapter="lizard",
                status="exported",
                template_version=template_version or "",
                created_by=actor_s,
                export_artifact_id=export_artifact_id,
                input_count=len(exported_package_sns) + len(skipped_rows),
                success_count=len(exported_package_sns),
                skipped_count=len(skipped_rows),
                summary=summary or "",
                created_at=now,
                updated_at=now,
            )
            session.add(batch)
            session.flush()
            batch_id = int(batch.id)
            for sn in exported_package_sns:
                session.add(
                    BatchPackageRow(
                        batch_id=batch_id,
                        package_sn=sn,
                        status="exported",
                        reason="",
                    )
                )
            for row in skipped_rows:
                session.add(
                    BatchPackageRow(
                        batch_id=batch_id,
                        package_sn=str(row.get("package_sn") or ""),
                        status="skipped",
                        reason=str(row.get("reason") or ""),
                    )
                )
        self.append_audit_event(
            actor=actor_s,
            action="batches.export_created",
            entity_type="batch",
            entity_id=str(batch_id),
            summary=summary or f"exported={len(exported_package_sns)}",
        )
        record = self.get_batch(batch_id)
        assert record is not None
        return record

    def apply_import_to_batch(
        self,
        *,
        batch_id: int,
        import_artifact_id: int | None,
        matched_sns: list[str],
        conflict_sns: list[str],
        unmatched_sns: list[str],
        actor: str,
        summary: str = "",
    ) -> ShippingBatchRecord:
        actor_s = (actor or "").strip() or "system"
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            batch = session.get(ShippingBatchRow, batch_id)
            if batch is None:
                raise LookupError(f"Batch {batch_id} not found")
            batch.import_artifact_id = import_artifact_id
            batch.status = "tracking_imported"
            batch.success_count = len(matched_sns)
            batch.failed_count = len(conflict_sns)
            batch.unmatched_count = len(unmatched_sns)
            batch.summary = summary or batch.summary
            batch.updated_at = now
            for sn in matched_sns:
                self._upsert_batch_package(session, batch_id, sn, "tracking_matched", "")
            for sn in conflict_sns:
                self._upsert_batch_package(
                    session, batch_id, sn, "tracking_conflict", "tracking conflict"
                )
            for sn in unmatched_sns:
                self._upsert_batch_package(
                    session, batch_id, sn, "unmatched", "not in local DB"
                )
        self.append_audit_event(
            actor=actor_s,
            action="batches.tracking_imported",
            entity_type="batch",
            entity_id=str(batch_id),
            summary=summary,
        )
        record = self.get_batch(batch_id)
        assert record is not None
        return record

    def _upsert_batch_package(
        self,
        session: Session,
        batch_id: int,
        package_sn: str,
        status: str,
        reason: str,
    ) -> None:
        sn = (package_sn or "").strip()
        if not sn:
            return
        row = session.scalar(
            select(BatchPackageRow).where(
                BatchPackageRow.batch_id == batch_id,
                BatchPackageRow.package_sn == sn,
            )
        )
        if row is None:
            session.add(
                BatchPackageRow(
                    batch_id=batch_id,
                    package_sn=sn,
                    status=status,
                    reason=reason,
                )
            )
        else:
            row.status = status
            row.reason = reason

    def get_batch(self, batch_id: int) -> ShippingBatchRecord | None:
        with self._session_factory() as session:
            row = session.get(ShippingBatchRow, batch_id)
            if row is None:
                return None
            account = session.get(ShippingAccountRow, row.account_id)
            return _batch_to_record(account.account_key if account else "", row)

    def list_batches(
        self,
        *,
        account_key: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ShippingBatchRecord]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ShippingBatchRow, ShippingAccountRow.account_key)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == ShippingBatchRow.account_id,
                )
                .where(ShippingAccountRow.account_key == account_key)
                .order_by(ShippingBatchRow.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return [_batch_to_record(ak, row) for row, ak in rows]

    def list_batch_packages(self, batch_id: int) -> list[BatchPackageRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(BatchPackageRow)
                .where(BatchPackageRow.batch_id == batch_id)
                .order_by(BatchPackageRow.package_sn)
            ).all()
            return [
                BatchPackageRecord(
                    batch_id=r.batch_id,
                    package_sn=r.package_sn,
                    status=r.status,
                    reason=r.reason or "",
                )
                for r in rows
            ]

    def get_package_sn_by_db_id(self, package_db_id: int) -> str | None:
        with self._session_factory() as session:
            row = session.get(PackageRow, package_db_id)
            return row.package_sn if row is not None else None

    def mark_submission_intent_verified(
        self,
        *,
        intent_id: int,
        summary: str = "",
    ) -> SubmissionIntentRecord:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            intent = session.get(SubmissionIntentRow, intent_id)
            if intent is None:
                raise LookupError(f"Intent {intent_id} not found")
            if intent.status not in {"SUCCESS", "VERIFIED"}:
                raise RuntimeError(
                    f"intent status {intent.status} cannot be verified"
                )
            intent.status = "VERIFIED"
            intent.updated_at = now
            if summary:
                # keep audit trail on latest attempt if any
                attempt = session.scalar(
                    select(SubmissionAttemptRow)
                    .where(SubmissionAttemptRow.intent_id == intent_id)
                    .order_by(SubmissionAttemptRow.attempt_no.desc())
                    .limit(1)
                )
                if attempt is not None:
                    note = (attempt.http_summary or "")
                    suffix = f" | verified: {summary}"
                    attempt.http_summary = (note + suffix)[:2000]
                    attempt.updated_at = now
            account = session.get(ShippingAccountRow, intent.account_id)
            return _intent_to_record(
                account.account_key if account else "", intent
            )

    def get_package_db_id(self, account_key: str, package_sn: str) -> int | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(PackageRow.id)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
            )
            return int(row) if row is not None else None

    def list_package_order_db_ids(
        self, account_key: str, package_sn: str
    ) -> list[tuple[int, str]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(OrderRow.id, OrderRow.external_order_id)
                .join(PackageOrderRow, PackageOrderRow.order_id == OrderRow.id)
                .join(PackageRow, PackageRow.id == PackageOrderRow.package_id)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
                .order_by(OrderRow.external_order_id)
            ).all()
            return [(int(oid), str(ext)) for oid, ext in rows]

    def list_order_items_for_package_order(
        self,
        *,
        package_db_id: int,
        external_order_id: str,
    ) -> list[dict[str, object]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(PackageItemRow)
                .where(
                    PackageItemRow.package_id == package_db_id,
                    PackageItemRow.external_order_id == external_order_id,
                )
                .order_by(PackageItemRow.order_item_id)
            ).all()
            return [
                {
                    "order_item_id": r.order_item_id,
                    "quantity": int(r.quantity or 0),
                }
                for r in rows
            ]

    def _get_or_create_submission_scope(
        self,
        session: Session,
        *,
        account_id: int,
        package_id: int,
        order_db_id: int,
    ) -> SubmissionScopeRow:
        scope = session.scalar(
            select(SubmissionScopeRow).where(
                SubmissionScopeRow.account_id == account_id,
                SubmissionScopeRow.package_id == package_id,
                SubmissionScopeRow.order_id == order_db_id,
            )
        )
        if scope is None:
            scope = SubmissionScopeRow(
                account_id=account_id,
                package_id=package_id,
                order_id=order_db_id,
                status="OPEN",
            )
            session.add(scope)
            session.flush()
        return scope

    def is_submission_scope_blocked(
        self,
        *,
        account_key: str,
        package_db_id: int,
        order_db_id: int,
    ) -> bool:
        with self._session_factory() as session:
            account = self._get_or_create_account(session, account_key)
            scope = session.scalar(
                select(SubmissionScopeRow).where(
                    SubmissionScopeRow.account_id == account.id,
                    SubmissionScopeRow.package_id == package_db_id,
                    SubmissionScopeRow.order_id == order_db_id,
                )
            )
            return scope is not None and scope.status == "UNKNOWN_BLOCKED"

    def is_submission_scope_blocked_by_intent(self, intent_id: int) -> bool:
        with self._session_factory() as session:
            intent = session.get(SubmissionIntentRow, intent_id)
            if intent is None:
                return True
            scope = session.get(SubmissionScopeRow, intent.scope_id)
            return scope is not None and scope.status == "UNKNOWN_BLOCKED"

    def upsert_submission_intent(
        self,
        *,
        account_key: str,
        package_db_id: int,
        order_db_id: int,
        external_order_id: str,
        request_hash: str,
        canonical_request: str,
        confirmed_by: str,
    ) -> SubmissionIntentRecord:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            scope = self._get_or_create_submission_scope(
                session,
                account_id=account.id,
                package_id=package_db_id,
                order_db_id=order_db_id,
            )
            if scope.status == "UNKNOWN_BLOCKED":
                raise RuntimeError("submission scope is UNKNOWN_BLOCKED")
            existing = session.scalar(
                select(SubmissionIntentRow).where(
                    SubmissionIntentRow.request_hash == request_hash
                )
            )
            if existing is not None:
                return _intent_to_record(account_key, existing)
            row = SubmissionIntentRow(
                account_id=account.id,
                package_id=package_db_id,
                order_id=order_db_id,
                scope_id=scope.id,
                external_order_id=external_order_id,
                request_hash=request_hash,
                canonical_request=canonical_request,
                status="READY",
                version=0,
                confirmed_by=confirmed_by,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return _intent_to_record(account_key, row)

    def get_submission_intent(self, intent_id: int) -> SubmissionIntentRecord | None:
        with self._session_factory() as session:
            row = session.get(SubmissionIntentRow, intent_id)
            if row is None:
                return None
            account = session.get(ShippingAccountRow, row.account_id)
            return _intent_to_record(account.account_key if account else "", row)

    def get_submission_attempt(
        self, attempt_id: int
    ) -> SubmissionAttemptRecord | None:
        with self._session_factory() as session:
            row = session.get(SubmissionAttemptRow, attempt_id)
            if row is None:
                return None
            return _attempt_to_record(row)

    def create_submission_attempt(
        self,
        *,
        intent_id: int,
        actor: str,
    ) -> SubmissionAttemptRecord:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            intent = session.get(SubmissionIntentRow, intent_id)
            if intent is None:
                raise LookupError(f"Intent {intent_id} not found")
            if intent.status not in {"READY", "FAILED"}:
                raise RuntimeError(f"intent status {intent.status} cannot submit")
            last_no = session.scalar(
                select(func.max(SubmissionAttemptRow.attempt_no)).where(
                    SubmissionAttemptRow.intent_id == intent_id
                )
            )
            attempt_no = int(last_no or 0) + 1
            row = SubmissionAttemptRow(
                intent_id=intent_id,
                attempt_no=attempt_no,
                status="CREATED",
                send_state="NOT_SENT",
                actor=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return _attempt_to_record(row)

    def cas_submission_to_in_flight(
        self,
        *,
        intent_id: int,
        attempt_id: int,
        expected_intent_version: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            intent = session.get(SubmissionIntentRow, intent_id)
            attempt = session.get(SubmissionAttemptRow, attempt_id)
            if intent is None or attempt is None:
                return False
            if intent.status not in {"READY", "FAILED"}:
                return False
            if intent.version != expected_intent_version:
                return False
            if attempt.status != "CREATED" or attempt.send_state != "NOT_SENT":
                return False
            intent.status = "IN_FLIGHT"
            intent.version = expected_intent_version + 1
            intent.updated_at = now
            attempt.status = "IN_FLIGHT"
            attempt.send_state = "SENT"
            attempt.updated_at = now
            return True

    def mark_submission_attempt_result(
        self,
        *,
        attempt_id: int,
        intent_id: int,
        attempt_status: str,
        intent_status: str,
        http_status: int | None,
        http_summary: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            attempt = session.get(SubmissionAttemptRow, attempt_id)
            intent = session.get(SubmissionIntentRow, intent_id)
            if attempt is None or intent is None:
                raise LookupError("attempt or intent missing")
            attempt.status = attempt_status
            attempt.http_status = http_status
            attempt.http_summary = http_summary or ""
            attempt.updated_at = now
            intent.status = intent_status
            intent.updated_at = now

    def mark_submission_unknown_and_block_scope(
        self,
        *,
        attempt_id: int,
        intent_id: int,
        http_summary: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            attempt = session.get(SubmissionAttemptRow, attempt_id)
            intent = session.get(SubmissionIntentRow, intent_id)
            if attempt is None or intent is None:
                raise LookupError("attempt or intent missing")
            attempt.status = "UNKNOWN"
            attempt.http_summary = http_summary or ""
            attempt.updated_at = now
            intent.status = "UNKNOWN"
            intent.updated_at = now
            scope = session.get(SubmissionScopeRow, intent.scope_id)
            if scope is not None:
                scope.status = "UNKNOWN_BLOCKED"
                scope.updated_at = now

    def recover_stale_submission_in_flight(self, *, actor: str) -> int:
        now = datetime.now(timezone.utc)
        recovered = 0
        with self._session_factory.begin() as session:
            stale_intents = session.scalars(
                select(SubmissionIntentRow).where(
                    SubmissionIntentRow.status == "IN_FLIGHT"
                )
            ).all()
            for intent in stale_intents:
                intent.status = "UNKNOWN"
                intent.updated_at = now
                scope = session.get(SubmissionScopeRow, intent.scope_id)
                if scope is not None:
                    scope.status = "UNKNOWN_BLOCKED"
                    scope.updated_at = now
                recovered += 1
            stale_attempts = session.scalars(
                select(SubmissionAttemptRow).where(
                    SubmissionAttemptRow.status == "IN_FLIGHT"
                )
            ).all()
            for attempt in stale_attempts:
                attempt.status = "UNKNOWN"
                attempt.updated_at = now
        if recovered:
            self.append_audit_event(
                actor=actor,
                action="submission.recover_in_flight",
                entity_type="submission",
                entity_id="*",
                summary=f"recovered={recovered}",
            )
        return recovered

    def list_intent_statuses_for_package(self, package_db_id: int) -> list[str]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SubmissionIntentRow.status).where(
                    SubmissionIntentRow.package_id == package_db_id
                )
            ).all()
            return [str(s) for s in rows]

    def list_submission_intents_for_package(
        self,
        *,
        account_key: str,
        package_sn: str,
    ) -> list[SubmissionIntentRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SubmissionIntentRow)
                .join(PackageRow, PackageRow.id == SubmissionIntentRow.package_id)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
                .order_by(SubmissionIntentRow.id)
            ).all()
            return [_intent_to_record(account_key, row) for row in rows]

    def list_packages(
        self,
        *,
        account_key: str,
        package_status: str | None = None,
        channel_name: str | None = None,
        local_review_status: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PackageListItem]:
        with self._session_factory() as session:
            query = (
                select(PackageRow, ShippingAccountRow.account_key)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(ShippingAccountRow.account_key == account_key)
            )
            if package_status is not None:
                query = query.where(PackageRow.package_status == package_status)
            if channel_name is not None:
                query = query.where(PackageRow.channel_name == channel_name)
            if local_review_status is not None:
                query = query.where(
                    PackageRow.local_review_status == local_review_status
                )
            if date_start is not None or date_end is not None:
                query = query.join(
                    ShippingLabelRow,
                    ShippingLabelRow.package_id == PackageRow.id,
                    isouter=True,
                )
                if date_start is not None:
                    query = query.where(
                        ShippingLabelRow.created_at >= date_start
                    )
                if date_end is not None:
                    query = query.where(
                        ShippingLabelRow.created_at < date_end + "T23:59:59"
                    )
                query = query.distinct()
            query = (
                query.order_by(PackageRow.package_sn)
                .offset(offset)
                .limit(limit)
            )
            rows = session.execute(query).all()
            items: list[PackageListItem] = []
            for package, account in rows:
                order_count = (
                    session.scalar(
                        select(func.count())
                        .select_from(PackageOrderRow)
                        .where(PackageOrderRow.package_id == package.id)
                    )
                    or 0
                )
                item_count = (
                    session.scalar(
                        select(func.count())
                        .select_from(PackageItemRow)
                        .where(PackageItemRow.package_id == package.id)
                    )
                    or 0
                )
                items.append(
                    PackageListItem(
                        account_key=account,
                        package_sn=package.package_sn,
                        package_status=package.package_status,
                        local_review_status=package.local_review_status or "pending",
                        channel_name=package.channel_name,
                        shop_name=package.shop_name,
                        marketplace=package.marketplace,
                        tracking_number=package.tracking_number,
                        order_count=order_count,
                        item_count=item_count,
                        fetched_at=package.fetched_at,
                    )
                )
            return items

    def count_packages(
        self,
        *,
        account_key: str,
        package_status: str | None = None,
        channel_name: str | None = None,
        local_review_status: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> int:
        with self._session_factory() as session:
            query = (
                select(func.count())
                .select_from(PackageRow)
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(ShippingAccountRow.account_key == account_key)
            )
            if package_status is not None:
                query = query.where(PackageRow.package_status == package_status)
            if channel_name is not None:
                query = query.where(PackageRow.channel_name == channel_name)
            if local_review_status is not None:
                query = query.where(
                    PackageRow.local_review_status == local_review_status
                )
            if date_start is not None or date_end is not None:
                query = query.join(
                    ShippingLabelRow,
                    ShippingLabelRow.package_id == PackageRow.id,
                    isouter=True,
                )
                if date_start is not None:
                    query = query.where(ShippingLabelRow.created_at >= date_start)
                if date_end is not None:
                    query = query.where(ShippingLabelRow.created_at < date_end + "T23:59:59")
                query = query.distinct()
            return session.scalar(query) or 0

    def list_distinct_channels(self, account_key: str) -> list[str]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(PackageRow.channel_name)
                    .join(
                        ShippingAccountRow,
                        ShippingAccountRow.id == PackageRow.account_id,
                    )
                    .where(ShippingAccountRow.account_key == account_key)
                    .where(PackageRow.channel_name.isnot(None))
                    .where(PackageRow.channel_name != "")
                    .distinct()
                    .order_by(PackageRow.channel_name)
                )
                .scalars()
                .all()
            )
            return [r for r in rows if r]

    def append_audit_event(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        summary: str = "",
    ) -> int:
        with self._session_factory.begin() as session:
            row = AuditEventRow(
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(row)
            session.flush()
            return row.id

    def list_audit_events(self, *, limit: int = 50) -> list[AuditEventRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AuditEventRow)
                .order_by(AuditEventRow.id.desc())
                .limit(limit)
            ).all()
            return [
                AuditEventRecord(
                    id=row.id,
                    actor=row.actor,
                    action=row.action,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    summary=row.summary,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def count_rows(self) -> dict[str, int]:
        tables = {
            "accounts": ShippingAccountRow,
            "packages": PackageRow,
            "orders": OrderRow,
            "package_orders": PackageOrderRow,
            "package_items": PackageItemRow,
            "audit_events": AuditEventRow,
        }
        with self._session_factory() as session:
            return {
                name: session.scalar(select(func.count()).select_from(model)) or 0
                for name, model in tables.items()
            }

    def upsert_package_dims(
        self,
        *,
        package_db_id: int,
        weight_kg: float,
        length_cm: float,
        width_cm: float,
        height_cm: float,
        sku_count: int,
    ) -> PackageDimsRecord:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = session.get(PackageDimsRow, package_db_id)
            if row is None:
                row = PackageDimsRow(package_id=package_db_id)
                session.add(row)
            row.weight_kg = weight_kg
            row.length_cm = length_cm
            row.width_cm = width_cm
            row.height_cm = height_cm
            row.sku_count = sku_count
            row.computed_at = now
        return PackageDimsRecord(
            package_id=package_db_id,
            weight_kg=weight_kg,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            sku_count=sku_count,
            computed_at=now,
        )

    def get_package_dims(self, package_db_id: int) -> PackageDimsRecord | None:
        with self._session_factory() as session:
            row = (
                session.query(PackageDimsRow)
                .filter(PackageDimsRow.package_id == package_db_id)
                .first()
            )
            if row is None:
                return None
            return PackageDimsRecord(
                package_id=row.package_id,
                weight_kg=float(row.weight_kg or 0),
                length_cm=float(row.length_cm or 0),
                width_cm=float(row.width_cm or 0),
                height_cm=float(row.height_cm or 0),
                sku_count=int(row.sku_count or 0),
                computed_at=row.computed_at,
            )

    def upsert_package_routing(
        self,
        *,
        package_db_id: int,
        carrier: str,
        label: str,
        reason: str,
        rule_name: str,
        matched: bool,
    ) -> PackageRoutingRecord:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = (
                session.query(PackageRoutingRow)
                .filter(PackageRoutingRow.package_id == package_db_id)
                .first()
            )
            if row is None:
                row = PackageRoutingRow(package_id=package_db_id)
                session.add(row)
            row.carrier = carrier
            row.label = label
            row.reason = reason
            row.rule_name = rule_name
            row.matched = matched
            row.computed_at = now
        return PackageRoutingRecord(
            package_id=package_db_id,
            carrier=carrier,
            label=label,
            reason=reason,
            rule_name=rule_name,
            matched=matched,
            computed_at=now,
        )

    def get_package_routing(self, package_db_id: int) -> PackageRoutingRecord | None:
        with self._session_factory() as session:
            row = (
                session.query(PackageRoutingRow)
                .filter(PackageRoutingRow.package_id == package_db_id)
                .first()
            )
            if row is None:
                return None
            return PackageRoutingRecord(
                package_id=row.package_id,
                carrier=row.carrier or "",
                label=row.label or "",
                reason=row.reason or "",
                rule_name=row.rule_name or "",
                matched=bool(row.matched),
                computed_at=row.computed_at,
            )

    def insert_package_rate(self, *, package_db_id: int, rate: dict, raw_data: str | None = None) -> PackageRateRecord:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = PackageRateRow(
                package_id=package_db_id,
                carrier=rate.get("source", ""),
                service=rate.get("service", ""),
                total_amount=rate.get("total_amount"),
                currency=rate.get("currency", "USD"),
                billing_weight=rate.get("billing_weight"),
                zone=str(rate.get("zone") or ""),
                channel=rate.get("channel", ""),
                max_side_in=rate.get("max_side_in"),
                weight_lb=rate.get("weight_lb"),
                is_fedex=rate.get("use_fedex", False),
                address_type=rate.get("address_type", ""),
                raw_data=raw_data,
                fetched_at=now,
            )
            session.add(row)
            session.flush()
            return _rate_row_to_record(row)

    def list_package_rates(
        self, package_db_id: int, *, limit: int = 20
    ) -> list[PackageRateRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(PackageRateRow)
                .where(PackageRateRow.package_id == package_db_id)
                .order_by(PackageRateRow.fetched_at.desc())
                .limit(limit)
                .all()
            )
            return [_rate_row_to_record(r) for r in rows]

    # ── shipping_labels ──────────────────────────────────────────

    # -- label operation claim / transition / query --

    def claim_label_operation(
        self,
        *,
        account_key: str,
        package_db_id: int,
        carrier: str,
        service_level: str,
        idempotency_key: str,
        request_hash: str,
        actor: str,
    ) -> LabelOperationRecord:
        active_statuses = tuple(ACTIVE_LABEL_OPERATION_STATUSES)
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
        with sqlite3.connect(self._db_path, timeout=30) as connection:
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                account_row = connection.execute(
                    "SELECT id FROM shipping_accounts WHERE account_key = ?",
                    (account_key,),
                ).fetchone()
                if account_row is None:
                    raise RuntimeError(f"account not found: {account_key}")
                account_id = int(account_row[0])

                package_row = connection.execute(
                    "SELECT account_id FROM shipping_packages WHERE id = ?",
                    (package_db_id,),
                ).fetchone()
                if package_row is None:
                    raise RuntimeError(f"package not found: {package_db_id}")
                if int(package_row[0]) != account_id:
                    raise RuntimeError("package does not belong to account")

                active_label = connection.execute(
                    "SELECT id FROM shipping_labels WHERE package_id = ? AND is_active = 1 LIMIT 1",
                    (package_db_id,),
                ).fetchone()
                if active_label is not None:
                    raise RuntimeError(
                        "active label exists for "
                        f"package_id={package_db_id} label_id={active_label[0]}"
                    )

                placeholders = ",".join("?" for _ in active_statuses)
                active_operation = connection.execute(
                    f"SELECT id, status FROM shipping_label_operations "
                    f"WHERE package_id = ? AND status IN ({placeholders}) LIMIT 1",
                    (package_db_id, *active_statuses),
                ).fetchone()
                if active_operation is not None:
                    raise RuntimeError(
                        "active label operation exists for "
                        f"package_id={package_db_id} op_id={active_operation[0]} "
                        f"status={active_operation[1]}"
                    )

                max_gen = connection.execute(
                    "SELECT coalesce(max(generation), 0) FROM shipping_label_operations WHERE package_id = ?",
                    (package_db_id,),
                ).fetchone()[0]
                generation = int(max_gen) + 1

                connection.execute(
                    "INSERT INTO shipping_label_operations "
                    "(account_id, package_id, generation, carrier, service_level, "
                    "idempotency_key, request_hash, status, "
                    "provider_order_id, tracking_number, attempt_count, "
                    "error_class, error_summary, created_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'RESERVED', '', '', 0, '', '', ?, ?, ?)",
                    (account_id, package_db_id, generation, carrier, service_level,
                     idempotency_key, request_hash, actor, now_iso, now_iso),
                )
                operation_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]

                connection.commit()
            except Exception:
                connection.rollback()
                raise

        self.append_audit_event(
            actor=actor,
            action="label_operation.claim",
            entity_type="shipping_label_operation",
            entity_id=str(operation_id),
            summary=f"carrier={carrier} generation={generation}",
        )
        return self.get_label_operation(operation_id)

    def transition_label_operation(
        self,
        operation_id: int,
        *,
        status: str,
        provider_order_id: str = "",
        tracking_number: str = "",
        error_class: str = "",
        error_summary: str = "",
        increment_attempt: bool = False,
    ) -> LabelOperationRecord | None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = session.get(LabelOperationRow, operation_id)
            if row is None:
                return None
            current = (row.status or "").strip()
            target = (status or "").strip()
            allowed = ALLOWED_LABEL_OPERATION_TRANSITIONS.get(current)
            if allowed is None:
                raise RuntimeError(
                    f"invalid transition: unknown current status {current!r} "
                    f"for operation_id={operation_id}"
                )
            # Crash-window escape hatch only: SENT may become CANCELLED when a
            # label row is already linked to this operation (insert succeeded,
            # outer SUCCEEDED transition never ran). Do not allow bare SENT→CANCELLED.
            if current == "SENT" and target == "CANCELLED":
                linked = (
                    session.query(ShippingLabelRow.id)
                    .where(ShippingLabelRow.operation_id == operation_id)
                    .limit(1)
                    .first()
                )
                if linked is None:
                    raise RuntimeError(
                        f"invalid transition: {current} -> {target} "
                        f"for operation_id={operation_id} "
                        "(no linked label; refuse unconditional SENT→CANCELLED)"
                    )
            elif target not in allowed:
                raise RuntimeError(
                    f"invalid transition: {current} -> {target} "
                    f"for operation_id={operation_id}"
                )
            row.status = target
            row.updated_at = now
            if provider_order_id:
                row.provider_order_id = provider_order_id
            if tracking_number:
                row.tracking_number = tracking_number
            if error_class:
                row.error_class = error_class
            if error_summary:
                row.error_summary = error_summary
            if increment_attempt:
                row.attempt_count = (row.attempt_count or 0) + 1
        self.append_audit_event(
            actor="system",
            action="label_operation.transition",
            entity_type="shipping_label_operation",
            entity_id=str(operation_id),
            summary=f"status={status}",
        )
        return self.get_label_operation(operation_id)

    def get_label_operation(self, operation_id: int) -> LabelOperationRecord:
        with self._session_factory() as session:
            row = session.get(LabelOperationRow, operation_id)
            if row is None:
                raise RuntimeError(f"label operation not found: {operation_id}")
            account = session.get(ShippingAccountRow, row.account_id)
            return _label_operation_to_record(
                account.account_key if account else "", row
            )

    def list_label_operations(
        self,
        *,
        account_key: str | None = None,
        package_sn: str | None = None,
        status: str | None = None,
        carrier: str | None = None,
        limit: int = 50,
    ) -> list[LabelOperationRecord]:
        with self._session_factory() as session:
            q = session.query(LabelOperationRow)
            if account_key:
                q = q.join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == LabelOperationRow.account_id,
                )
                q = q.where(ShippingAccountRow.account_key == account_key)
            if package_sn:
                q = q.join(PackageRow, PackageRow.id == LabelOperationRow.package_id)
                q = q.where(PackageRow.package_sn == package_sn)
            if status:
                q = q.where(LabelOperationRow.status == status)
            if carrier:
                q = q.where(LabelOperationRow.carrier == carrier)
            rows = q.order_by(LabelOperationRow.created_at.desc()).limit(limit).all()
            result: list[LabelOperationRecord] = []
            for row in rows:
                account = session.get(ShippingAccountRow, row.account_id)
                result.append(
                    _label_operation_to_record(
                        account.account_key if account else "", row
                    )
                )
            return result

    def get_package_sns_by_db_ids(
        self, package_db_ids: set[int]
    ) -> dict[int, str]:
        if not package_db_ids:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(PackageRow.id, PackageRow.package_sn).where(
                    PackageRow.id.in_(package_db_ids)
                )
            ).all()
            return {int(package_id): str(package_sn) for package_id, package_sn in rows}

    def get_label_for_operation(
        self, operation_id: int
    ) -> ShippingLabelRecord | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(ShippingLabelRow)
                .where(ShippingLabelRow.operation_id == operation_id)
                .order_by(ShippingLabelRow.id.desc())
                .limit(1)
            )
            if row is None:
                return None
            account = session.get(ShippingAccountRow, row.account_id)
            return _shipping_label_to_record(
                account.account_key if account else "", row
            )

    def insert_label(
        self,
        *,
        account_key: str,
        package_db_id: int,
        carrier: str,
        service_level: str,
        tracking_number: str,
        carrier_order_id: str,
        request_id: str,
        label_url: str,
        operation_id: int | None = None,
        artifact_id: int | None,
        total_amount: float | None,
        currency: str,
        status: str,
        carrier_response_json: str,
        created_by: str,
    ) -> ShippingLabelRecord:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = ShippingLabelRow(
                account_id=account.id,
                package_id=package_db_id,
                carrier=carrier,
                service_level=service_level,
                tracking_number=tracking_number,
                carrier_order_id=carrier_order_id,
                request_id=request_id,
                label_url=label_url,
                operation_id=operation_id,
                artifact_id=artifact_id,
                total_amount=total_amount,
                currency=currency,
                status=status,
                is_active=status != "cancelled",
                carrier_response_json=carrier_response_json,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            label_id = int(row.id)
        self.append_audit_event(
            actor=created_by,
            action="labels.create",
            entity_type="shipping_label",
            entity_id=str(label_id),
            summary=f"{carrier} tracking={tracking_number} order={carrier_order_id}",
        )
        record = self.get_label(label_id)
        assert record is not None
        return record

    def get_label(self, label_id: int) -> ShippingLabelRecord | None:
        with self._session_factory() as session:
            row = session.get(ShippingLabelRow, label_id)
            if row is None:
                return None
            account = session.get(ShippingAccountRow, row.account_id)
            return _shipping_label_to_record(
                account.account_key if account else "", row
            )

    def list_labels_for_package(
        self,
        *,
        account_key: str,
        package_sn: str,
        limit: int = 50,
    ) -> list[ShippingLabelRecord]:
        with self._session_factory() as session:
            rows = (
                session.query(ShippingLabelRow)
                .join(
                    PackageRow,
                    PackageRow.id == ShippingLabelRow.package_id,
                )
                .join(
                    ShippingAccountRow,
                    ShippingAccountRow.id == PackageRow.account_id,
                )
                .where(
                    ShippingAccountRow.account_key == account_key,
                    PackageRow.package_sn == package_sn,
                )
                .order_by(ShippingLabelRow.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                _shipping_label_to_record(account_key, r) for r in rows
            ]

    def update_label_status(
        self, label_id: int, status: str
    ) -> ShippingLabelRecord | None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = session.get(ShippingLabelRow, label_id)
            if row is None:
                return None
            row.status = status
            if status == "cancelled":
                row.is_active = False
            row.updated_at = now
        self.append_audit_event(
            actor="system",
            action="labels.update_status",
            entity_type="shipping_label",
            entity_id=str(label_id),
            summary=f"status={status}",
        )
        return self.get_label(label_id)

    def finalize_label_cancellation(
        self,
        label_id: int,
        *,
        actor: str = "",
    ) -> tuple[ShippingLabelRecord, LabelOperationRecord | None]:
        """Atomically mark label inactive and release linked operation to CANCELLED.

        Carrier cancel must already be confirmed (or skipped for local
        reconciliation of a previously cancelled label). Both writes share one
        SQLite transaction so a crash cannot leave inactive label + active op.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        operation_id: int | None = None
        with self._session_factory.begin() as session:
            label = session.get(ShippingLabelRow, label_id)
            if label is None:
                raise RuntimeError(f"label not found: {label_id}")

            if label.operation_id is not None:
                operation_id = int(label.operation_id)
                op = session.get(LabelOperationRow, operation_id)
                if op is None:
                    raise RuntimeError(
                        f"label operation not found: {operation_id}"
                    )
                current = (op.status or "").strip()
                if current != "CANCELLED":
                    allowed = ALLOWED_LABEL_OPERATION_TRANSITIONS.get(current)
                    if allowed is None:
                        raise RuntimeError(
                            f"invalid transition: unknown current status "
                            f"{current!r} for operation_id={operation_id}"
                        )
                    if current == "SENT":
                        # Linked label is this row — crash-window release OK.
                        pass
                    elif "CANCELLED" not in allowed:
                        raise RuntimeError(
                            f"invalid transition: {current} -> CANCELLED "
                            f"for operation_id={operation_id}"
                        )
                    op.status = "CANCELLED"
                    op.error_class = "cancelled"
                    op.error_summary = f"label_id={label_id}"
                    op.updated_at = now

            label.status = "cancelled"
            label.is_active = False
            label.updated_at = now

        self.append_audit_event(
            actor=actor or "system",
            action="labels.finalize_cancellation",
            entity_type="shipping_label",
            entity_id=str(label_id),
            summary=(
                f"operation_id={operation_id}" if operation_id is not None else "no operation"
            ),
        )
        label_rec = self.get_label(label_id)
        assert label_rec is not None
        op_rec = (
            self.get_label_operation(operation_id)
            if operation_id is not None
            else None
        )
        return label_rec, op_rec

    @staticmethod
    def _get_or_create_account(
        session: Session,
        account_key: str,
    ) -> ShippingAccountRow:
        account = session.scalar(
            select(ShippingAccountRow).where(
                ShippingAccountRow.account_key == account_key
            )
        )
        if account is None:
            session.execute(
                sqlite_insert(ShippingAccountRow)
                .values(account_key=account_key)
                .on_conflict_do_nothing(index_elements=["account_key"])
            )
            account = session.scalar(
                select(ShippingAccountRow).where(
                    ShippingAccountRow.account_key == account_key
                )
            )
            if account is None:
                raise RuntimeError("account upsert did not return a row")
        return account

    @staticmethod
    def _upsert_orders(
        session: Session,
        account_id: int,
        record: SellfoxPackageRecord,
    ) -> dict[str, OrderRow]:
        order_records = {
            order.external_order_id: order
            for order in record.orders
        }
        for item in record.items:
            if item.external_order_id and item.external_order_id not in order_records:
                order_records[item.external_order_id] = SellfoxPackageOrderRecord(
                    external_order_id=item.external_order_id
                )

        rows: dict[str, OrderRow] = {}
        for external_order_id, order in order_records.items():
            row = session.scalar(
                select(OrderRow).where(
                    OrderRow.account_id == account_id,
                    OrderRow.external_order_id == external_order_id,
                )
            )
            if row is None:
                session.execute(
                    sqlite_insert(OrderRow)
                    .values(
                        account_id=account_id,
                        external_order_id=external_order_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["account_id", "external_order_id"]
                    )
                )
                row = session.scalar(
                    select(OrderRow).where(
                        OrderRow.account_id == account_id,
                        OrderRow.external_order_id == external_order_id,
                    )
                )
                if row is None:
                    raise RuntimeError("order upsert did not return a row")
            row.order_status = order.order_status
            row.purchase_date = order.purchase_date
            row.earliest_ship_date = order.earliest_ship_date
            row.latest_ship_date = order.latest_ship_date
            row.order_total = order.order_total
            row.currency = order.currency
            rows[external_order_id] = row
        return rows

    @staticmethod
    def _apply_package_fields(
        package: PackageRow,
        record: SellfoxPackageRecord,
    ) -> None:
        address = record.address
        logistics = record.logistics
        package.shop_id = record.shop_id
        package.shop_name = record.shop_name
        package.platform_name = record.platform_name
        package.marketplace = record.marketplace
        package.package_status = record.package_status
        package.address_name = address.name
        package.address_company = address.company
        package.address_line_1 = address.address_line_1
        package.address_line_2 = address.address_line_2
        package.address_city = address.city
        package.address_state_or_region = address.state_or_region
        package.address_postal_code = address.postal_code
        package.address_country = address.country
        package.address_country_code = address.country_code
        package.address_phone = address.phone
        package.address_mobile = address.mobile
        package.address_email = address.email
        package.warehouse_name = logistics.warehouse_name
        package.channel_name = logistics.channel_name
        package.tracking_number = logistics.tracking_number
        package.forward_number = logistics.forward_number
        package.estimated_cost = logistics.estimated_cost
        package.cost_currency = logistics.currency
        package.weight_grams = logistics.weight_grams
        package.length_cm = logistics.length_cm
        package.width_cm = logistics.width_cm
        package.height_cm = logistics.height_cm
        package.raw_json = json.dumps(
            record.raw_payload,
            ensure_ascii=False,
            default=str,
        )
        package.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        _auto_set_review_on_terminal_status(package)

    @staticmethod
    def _to_record(
        account_key: str,
        package: PackageRow,
        order_rows: list[OrderRow],
        item_rows: list[PackageItemRow],
    ) -> SellfoxPackageRecord:
        return SellfoxPackageRecord(
            account_key=account_key,
            package_sn=package.package_sn,
            shop_id=package.shop_id,
            shop_name=package.shop_name,
            platform_name=package.platform_name,
            marketplace=package.marketplace,
            package_status=package.package_status,
            local_review_status=package.local_review_status or "pending",
            address=SellfoxPackageAddress(
                name=package.address_name,
                company=package.address_company,
                address_line_1=package.address_line_1,
                address_line_2=package.address_line_2,
                city=package.address_city,
                state_or_region=package.address_state_or_region,
                postal_code=package.address_postal_code,
                country=package.address_country,
                country_code=package.address_country_code,
                phone=package.address_phone,
                mobile=package.address_mobile,
                email=package.address_email,
            ),
            logistics=SellfoxPackageLogistics(
                warehouse_name=package.warehouse_name,
                channel_name=package.channel_name,
                tracking_number=package.tracking_number,
                forward_number=package.forward_number,
                estimated_cost=package.estimated_cost,
                currency=package.cost_currency,
                weight_grams=package.weight_grams,
                length_cm=package.length_cm,
                width_cm=package.width_cm,
                height_cm=package.height_cm,
            ),
            orders=[
                SellfoxPackageOrderRecord(
                    external_order_id=row.external_order_id,
                    order_status=row.order_status,
                    purchase_date=row.purchase_date,
                    earliest_ship_date=row.earliest_ship_date,
                    latest_ship_date=row.latest_ship_date,
                    order_total=row.order_total,
                    currency=row.currency,
                )
                for row in order_rows
            ],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id=row.external_order_id,
                    order_item_id=row.order_item_id,
                    seller_sku=row.seller_sku,
                    commodity_sku=row.commodity_sku,
                    quantity=row.quantity,
                    main_image=row.main_image,
                    variation=row.variation,
                )
                for row in item_rows
            ],
            raw_payload=json.loads(package.raw_json or "{}"),
        )


def _artifact_to_record(account_key: str, row: ArtifactRow) -> ArtifactRecord:
    return ArtifactRecord(
        id=int(row.id),
        account_key=account_key,
        kind=row.kind,
        file_name=row.file_name,
        content_hash=row.content_hash,
        storage_relpath=row.storage_relpath,
        mime_type=row.mime_type or "",
        file_size=int(row.file_size or 0),
        template_version=row.template_version or "",
        virtual_folder=row.virtual_folder or "",
        summary=row.summary or "",
        created_by=row.created_by or "",
        created_at=row.created_at,
    )


def _batch_to_record(account_key: str, row: ShippingBatchRow) -> ShippingBatchRecord:
    return ShippingBatchRecord(
        id=int(row.id),
        account_key=account_key,
        adapter=row.adapter or "lizard",
        status=row.status or "",
        template_version=row.template_version or "",
        created_by=row.created_by or "",
        export_artifact_id=row.export_artifact_id,
        import_artifact_id=row.import_artifact_id,
        input_count=int(row.input_count or 0),
        success_count=int(row.success_count or 0),
        skipped_count=int(row.skipped_count or 0),
        failed_count=int(row.failed_count or 0),
        unmatched_count=int(row.unmatched_count or 0),
        summary=row.summary or "",
        created_at=row.created_at,
    )


def _intent_to_record(account_key: str, row: SubmissionIntentRow) -> SubmissionIntentRecord:
    return SubmissionIntentRecord(
        id=int(row.id),
        account_key=account_key,
        package_id=int(row.package_id),
        order_db_id=int(row.order_id),
        external_order_id=row.external_order_id or "",
        request_hash=row.request_hash,
        canonical_request=row.canonical_request or "",
        status=row.status or "",
        version=int(row.version or 0),
        confirmed_by=row.confirmed_by or "",
    )


def _attempt_to_record(row: SubmissionAttemptRow) -> SubmissionAttemptRecord:
    return SubmissionAttemptRecord(
        id=int(row.id),
        intent_id=int(row.intent_id),
        attempt_no=int(row.attempt_no or 1),
        status=row.status or "",
        send_state=row.send_state or "",
        actor=row.actor or "",
        http_status=row.http_status,
        http_summary=row.http_summary or "",
    )


def _rate_row_to_record(row: PackageRateRow) -> PackageRateRecord:
    fetched_at = row.fetched_at
    if fetched_at is not None:
        from datetime import timedelta, timezone

        fetched_at = fetched_at.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(hours=8))
        )
    return PackageRateRecord(
        id=int(row.id),
        package_id=int(row.package_id),
        carrier=row.carrier or "",
        service=row.service or "",
        total_amount=float(row.total_amount) if row.total_amount is not None else None,
        currency=row.currency or "USD",
        billing_weight=float(row.billing_weight) if row.billing_weight is not None else None,
        zone=row.zone or "",
        channel=row.channel or "",
        max_side_in=float(row.max_side_in) if row.max_side_in is not None else None,
        weight_lb=float(row.weight_lb) if row.weight_lb is not None else None,
        is_fedex=bool(row.is_fedex),
        address_type=row.address_type or "",
        raw_data=row.raw_data,
        fetched_at=fetched_at,
    )


def _shipping_label_to_record(
    account_key: str, row: ShippingLabelRow
) -> ShippingLabelRecord:
    created_at = row.created_at
    updated_at = row.updated_at
    if created_at is not None:
        from datetime import timedelta, timezone
        created_at = created_at.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(hours=8))
        )
    if updated_at is not None:
        from datetime import timedelta, timezone
        updated_at = updated_at.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(hours=8))
        )
    return ShippingLabelRecord(
        id=int(row.id),
        account_key=account_key,
        package_id=int(row.package_id),
        carrier=row.carrier or "",
        service_level=row.service_level or "",
        tracking_number=row.tracking_number or "",
        carrier_order_id=row.carrier_order_id or "",
        request_id=row.request_id or "",
        label_url=row.label_url or "",
        operation_id=int(row.operation_id) if row.operation_id is not None else None,
        artifact_id=int(row.artifact_id) if row.artifact_id is not None else None,
        label_format=row.label_format or "PDF",
        total_amount=float(row.total_amount) if row.total_amount is not None else None,
        currency=row.currency or "USD",
        status=row.status or "pending",
        is_active=bool(row.is_active),
        carrier_response_json=row.carrier_response_json or "",
        created_by=row.created_by or "",
    created_at=created_at,
    updated_at=updated_at,
)


def _label_operation_to_record(
    account_key: str, row: LabelOperationRow
) -> LabelOperationRecord:
    created_at = row.created_at
    updated_at = row.updated_at
    if created_at is not None:
        from datetime import timedelta, timezone as tz
        created_at = created_at.replace(tzinfo=tz.utc).astimezone(tz(timedelta(hours=8)))
    if updated_at is not None:
        from datetime import timedelta, timezone as tz
        updated_at = updated_at.replace(tzinfo=tz.utc).astimezone(tz(timedelta(hours=8)))
    return LabelOperationRecord(
        id=int(row.id),
        account_key=account_key,
        package_id=int(row.package_id),
        generation=int(row.generation or 0),
        carrier=row.carrier or "",
        service_level=row.service_level or "",
        idempotency_key=row.idempotency_key or "",
        request_hash=row.request_hash or "",
        status=row.status or "RESERVED",
        provider_order_id=row.provider_order_id or "",
        tracking_number=row.tracking_number or "",
        attempt_count=int(row.attempt_count or 0),
        error_class=row.error_class or "",
        error_summary=row.error_summary or "",
        created_by=row.created_by or "",
        created_at=created_at,
        updated_at=updated_at,
    )


def _guess_mime(file_name: str) -> str:
    lower = file_name.lower()
    if lower.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if lower.endswith(".xls"):
        return "application/vnd.ms-excel"
    if lower.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


def _sanitize_filename(name: str) -> str:
    """Keep a readable flat name; strip path separators (ERPNext-like)."""
    import re

    base = Path(name or "unnamed.bin").name
    cleaned = "".join("_" if ch in '\\/:*?"<>|\0' else ch for ch in base)
    cleaned = re.sub(r"[_\s]+", "_", cleaned).strip("._ ")
    return cleaned or "unnamed.bin"


def _flat_private_relpath(file_name: str, content_hash: str) -> str:
    """ERPNext-like flat private/files path; hash suffix avoids name collisions."""
    safe = _sanitize_filename(file_name)
    stem = Path(safe).stem
    suffix = Path(safe).suffix or ".bin"
    # Prefer readable name; include short hash so two different files can share a stem.
    return f"private/files/{stem}_{content_hash[:8]}{suffix}"


def _auto_set_review_on_terminal_status(package: PackageRow) -> None:
    """When package_status is terminal, promote default 'pending' review to match.

    Only touches rows whose local_review_status is still the DB default ('pending').
    Manual review decisions (approved / rejected) are never overwritten.
    """
    _TERMINAL_REVIEW = {
        "has_shipped": "shipped",
        "has_canceled": "closed",
    }
    target = _TERMINAL_REVIEW.get(package.package_status)
    if target is None:
        return
    current = (package.local_review_status or "pending").strip()
    if current == "pending":
        package.local_review_status = target


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def _initialize_sqlite(path: Path) -> None:
    with sqlite3.connect(path, timeout=5) as connection:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
