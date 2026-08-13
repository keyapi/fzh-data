"""SQLAlchemy persistence for the package-centric workflow."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
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
    CheckConstraint,
    create_engine,
    delete,
    event,
    func,
    or_,
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
    # 通途订单标记：由 美东100.xls 上传后经 EN(Tongtool Package) 匹配得到。
    # is_tongtool=1 表示该包裹在通途订单清单中；tongtool_p_numbers 记录命中的
    # 通途包裹号（逗号分隔，便于追溯）。
    is_tongtool: Mapped[bool] = mapped_column(Boolean, default=False)
    tongtool_p_numbers: Mapped[str] = mapped_column(String, default="")
    tongtool_shipping_warehouse: Mapped[str] = mapped_column(String, default="")
    tongtool_shipping_method: Mapped[str] = mapped_column(String, default="")


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


class SellfoxWritebackPolicyRow(Base):
    __tablename__ = "shipping_sellfox_writeback_policies"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_sellfox_writeback_policy_account"),
        CheckConstraint(
            "mode IN ('DISABLED', 'PROBE_ONLY', 'SCOPED_BATCH')",
            name="ck_sellfox_writeback_policy_mode",
        ),
        CheckConstraint(
            "capability_status IN ('UNVERIFIED', 'SAFE_TRACKNO_ONLY', "
            "'UNSAFE_PLATFORM_SIDE_EFFECT', 'INEFFECTIVE')",
            name="ck_sellfox_writeback_policy_capability",
        ),
        CheckConstraint(
            "mode <> 'SCOPED_BATCH' OR capability_status = 'SAFE_TRACKNO_ONLY'",
            name="ck_sellfox_writeback_policy_scope_gate",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_accounts.id", ondelete="CASCADE")
    )
    mode: Mapped[str] = mapped_column(
        String, nullable=False, server_default="DISABLED", default="DISABLED"
    )
    capability_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="UNVERIFIED", default="UNVERIFIED"
    )
    evidence_ref: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="", default=""
    )
    approved_by: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class SellfoxOutboxRow(Base):
    __tablename__ = "shipping_sellfox_outbox"
    __table_args__ = (
        UniqueConstraint("candidate_key", name="uq_sellfox_outbox_candidate_key"),
        UniqueConstraint(
            "account_id",
            "package_id",
            "order_id",
            "generation",
            name="uq_sellfox_outbox_generation",
        ),
        CheckConstraint(
            "status IN ('AWAITING_CONFIRMATION', 'PENDING', 'LEASED', "
            "'IN_FLIGHT', 'VERIFY_PENDING', 'VERIFIED', 'RETRYABLE', "
            "'MANUAL_REVIEW', 'UNKNOWN_BLOCKED', 'CONFLICT', 'FAILED_FINAL', 'SUPERSEDED')",
            name="ck_sellfox_outbox_status",
        ),
        CheckConstraint(
            "generation > 0", name="ck_sellfox_outbox_generation_positive"
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_sellfox_outbox_attempt_nonnegative"
        ),
        CheckConstraint(
            "trim(tracking_number) <> ''", name="ck_sellfox_outbox_tracking_nonempty"
        ),
        CheckConstraint(
            "length(candidate_key) = 64", name="ck_sellfox_outbox_candidate_key_sha256"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("shipping_accounts.id", ondelete="CASCADE"))
    package_id: Mapped[int] = mapped_column(ForeignKey("shipping_packages.id", ondelete="CASCADE"))
    order_id: Mapped[int] = mapped_column(ForeignKey("shipping_orders.id", ondelete="CASCADE"))
    generation: Mapped[int] = mapped_column(Integer)
    tracking_number: Mapped[str] = mapped_column(String)
    candidate_key: Mapped[str] = mapped_column(String)
    submission_intent_id: Mapped[int | None] = mapped_column(ForeignKey("shipping_submission_intents.id", ondelete="SET NULL"), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_origin_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default="AWAITING_CONFIRMATION",
        default="AWAITING_CONFIRMATION",
    )
    request_hash: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    lease_owner: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    lease_token: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    confirmed_by: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    last_error_class: Mapped[str] = mapped_column(
        String, nullable=False, server_default="", default=""
    )
    last_error_summary: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="", default=""
    )
    conflicts_with_outbox_id: Mapped[int | None] = mapped_column(ForeignKey("shipping_sellfox_outbox.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class SellfoxOutboxSourceRow(Base):
    __tablename__ = "shipping_sellfox_outbox_sources"
    __table_args__ = (
        UniqueConstraint("outbox_id", "source_type", "source_id", name="uq_sellfox_outbox_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    outbox_id: Mapped[int] = mapped_column(ForeignKey("shipping_sellfox_outbox.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


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
    scope_id: int = 0


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
class SellfoxWritebackPolicyRecord:
    account_key: str
    mode: str
    capability_status: str
    evidence_ref: str = ""
    approved_by: str = ""
    approved_at: datetime | None = None


@dataclass(frozen=True)
class SellfoxOutboxSourceRecord:
    source_type: str
    source_id: str


@dataclass(frozen=True)
class SellfoxOutboxRecord:
    id: int
    account_key: str
    package_id: int
    package_sn: str
    order_db_id: int
    external_order_id: str
    generation: int
    tracking_number: str
    candidate_key: str
    status: str
    submission_intent_id: int | None
    request_hash: str
    attempt_count: int
    conflicts_with_outbox_id: int | None
    next_attempt_at: datetime | None = None
    lease_owner: str = ""
    lease_token: str = ""
    lease_expires_at: datetime | None = None
    confirmed_by: str = ""
    confirmed_at: datetime | None = None
    last_error_class: str = ""
    last_error_summary: str = ""
    sources: tuple[SellfoxOutboxSourceRecord, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class SellfoxOutboxCandidateReport:
    counts: dict[str, int]
    results: tuple[dict[str, object], ...]


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
    derived_reference_no: Mapped[str] = mapped_column(String, default="")
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
    derived_reference_no: str = ""
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
    claimed_by: Mapped[str] = mapped_column(String, default="")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str] = mapped_column(String, default="")
    resolution_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipping_label_investigations.id", ondelete="SET NULL"),
        nullable=True,
    )
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
    resolution_evidence_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InvestigationRow(Base):
    """Append-only investigation/evidence for UNKNOWN_BLOCKED resolution."""

    __tablename__ = "shipping_label_investigations"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("shipping_label_operations.id", ondelete="CASCADE"),
    )
    evidence_type: Mapped[str] = mapped_column(String)
    conclusion: Mapped[str] = mapped_column(String, default="")
    provider_order_id: Mapped[str] = mapped_column(String, default="")
    external_ref: Mapped[str] = mapped_column(String, default="")
    private_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipping_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


@dataclass(frozen=True)
class InvestigationRecord:
    id: int
    operation_id: int
    evidence_type: str
    conclusion: str
    provider_order_id: str
    external_ref: str
    private_artifact_id: int | None
    note: str
    actor: str
    created_at: datetime | None = None


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

    def finalize_excel_tracking_with_outbox(
        self,
        *,
        account_key: str,
        package_sn: str,
        tracking_number: str,
        source_id: str,
        actor: str,
        estimated_cost: float | None = None,
        cost_currency: str | None = None,
    ) -> tuple[SellfoxPackageRecord, SellfoxOutboxCandidateReport]:
        report = self._finalize_tracking_with_outbox(
            account_key=account_key,
            package_sn=package_sn,
            tracking_number=tracking_number,
            source_type="excel_tracking_import",
            source_id=source_id,
            actor=actor,
            estimated_cost=estimated_cost,
            cost_currency=cost_currency,
        )
        package = self.get(account_key, package_sn)
        assert package is not None
        return package, report

    def finalize_label_success_with_outbox(
        self,
        *,
        operation_id: int,
        label_id: int,
        actor: str,
        expected_claim_id: str | None = None,
    ) -> SellfoxOutboxCandidateReport:
        label = self.get_label(label_id)
        if label is None:
            raise LookupError(f"label not found: {label_id}")
        package_sns = self.get_package_sns_by_db_ids({label.package_id})
        package_sn = package_sns.get(label.package_id, "")
        if not package_sn:
            raise LookupError(f"package not found for label_id={label_id}")
        return self._finalize_tracking_with_outbox(
            account_key=label.account_key,
            package_sn=package_sn,
            tracking_number=label.tracking_number,
            source_type="api_label",
            source_id=f"label:{label_id}:operation:{operation_id}",
            actor=actor,
            operation_id=operation_id,
            label_id=label_id,
            expected_claim_id=expected_claim_id,
        )

    def _finalize_tracking_with_outbox(
        self,
        *,
        account_key: str,
        package_sn: str,
        tracking_number: str,
        source_type: str,
        source_id: str,
        actor: str,
        estimated_cost: float | None = None,
        cost_currency: str | None = None,
        operation_id: int | None = None,
        label_id: int | None = None,
        expected_claim_id: str | None = None,
    ) -> SellfoxOutboxCandidateReport:
        tracking = (tracking_number or "").strip()
        actor_name = (actor or "").strip()
        if not actor_name:
            raise ValueError("actor is required")
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        counts = {"input": 0, "created": 0, "existing": 0, "skipped": 0, "conflict": 0, "failed": 0}
        results: list[dict[str, object]] = []
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                package = connection.execute(
                    "SELECT p.id, p.account_id, p.package_status, p.local_review_status "
                    "FROM shipping_packages p JOIN shipping_accounts a ON a.id=p.account_id "
                    "WHERE a.account_key=? AND p.package_sn=?",
                    (account_key, package_sn),
                ).fetchone()
                if package is None:
                    raise LookupError(f"Package {package_sn} not found")
                package_id, account_id, package_status, review_status = package
                skip_reason = ""
                if not tracking or tracking == package_sn:
                    skip_reason = "tracking_missing_or_placeholder"
                elif review_status != "approved":
                    skip_reason = "package_not_approved"
                elif package_status in {"has_shipped", "has_canceled"}:
                    skip_reason = "package_status_not_submittable"
                if skip_reason:
                    connection.rollback()
                    counts["input"] = 1
                    counts["skipped"] = 1
                    results.append(
                        {
                            "package_sn": package_sn,
                            "external_order_id": "",
                            "outcome": "skipped",
                            "reason": skip_reason,
                        }
                    )
                    self.append_audit_event(
                        actor=actor_name,
                        action="sellfox_outbox.finalize_tracking_skipped",
                        entity_type="shipping_package",
                        entity_id=package_sn,
                        summary=json.dumps(
                            {"skipped": 1, "reason": skip_reason}, sort_keys=True
                        ),
                    )
                    return SellfoxOutboxCandidateReport(
                        counts=counts, results=tuple(results)
                    )

                if operation_id is not None:
                    op_row = connection.execute(
                        "SELECT status, claim_token FROM shipping_label_operations WHERE id=? AND package_id=?",
                        (operation_id, package_id),
                    ).fetchone()
                    if op_row is None:
                        raise LookupError(f"label operation not found: {operation_id}")
                    if expected_claim_id is not None and op_row[1] != expected_claim_id:
                        raise RuntimeError(f"resume lease lost for operation_id={operation_id}")
                    if op_row[0] not in {"SENT", "ACCEPTED", "LABEL_PENDING", "SUCCEEDED"}:
                        raise RuntimeError(f"invalid transition: {op_row[0]} -> SUCCEEDED for operation_id={operation_id}")
                    linked = connection.execute(
                        "SELECT id, is_active, status, tracking_number FROM shipping_labels WHERE id=? AND operation_id=? AND package_id=?",
                        (label_id, operation_id, package_id),
                    ).fetchone()
                    if linked is None or not linked[1] or linked[2] == "cancelled":
                        raise RuntimeError("active linked label required for API outbox finalization")
                    if linked[3] != tracking:
                        raise RuntimeError("label tracking does not match finalizer tracking")

                connection.execute(
                    "UPDATE shipping_packages SET tracking_number=?, estimated_cost=coalesce(?, estimated_cost), "
                    "cost_currency=coalesce(?, cost_currency) WHERE id=?",
                    (tracking, estimated_cost, cost_currency, package_id),
                )
                if operation_id is not None and op_row[0] != "SUCCEEDED":
                    connection.execute(
                        "UPDATE shipping_label_operations SET status='SUCCEEDED', tracking_number=?, updated_at=? WHERE id=?",
                        (tracking, now, operation_id),
                    )

                orders = connection.execute(
                    "SELECT o.id, o.external_order_id FROM shipping_orders o "
                    "JOIN shipping_package_orders po ON po.order_id=o.id "
                    "WHERE po.package_id=? ORDER BY o.external_order_id",
                    (package_id,),
                ).fetchall()
                counts["input"] = max(1, len(orders))
                if not orders:
                    counts["skipped"] = 1
                    results.append(
                        {
                            "package_sn": package_sn,
                            "external_order_id": "",
                            "outcome": "skipped",
                            "reason": "package_has_no_orders",
                        }
                    )
                for order_id, external_order_id in orders:
                    item_count = connection.execute(
                        "SELECT count(*) FROM shipping_package_items WHERE package_id=? "
                        "AND external_order_id=? AND order_item_id<>'' AND quantity>0",
                        (package_id, external_order_id),
                    ).fetchone()[0]
                    if not item_count:
                        counts["skipped"] += 1
                        results.append({"package_sn": package_sn, "external_order_id": external_order_id, "outcome": "skipped", "reason": "order_items_incomplete"})
                        continue
                    candidate_key = _sellfox_outbox_candidate_key(
                        account_key=account_key, package_sn=package_sn,
                        external_order_id=external_order_id, tracking_number=tracking,
                    )
                    existing = connection.execute(
                        "SELECT id, status FROM shipping_sellfox_outbox WHERE candidate_key=?",
                        (candidate_key,),
                    ).fetchone()
                    prior = connection.execute(
                        "SELECT id, generation, tracking_number, status FROM shipping_sellfox_outbox "
                        "WHERE account_id=? AND package_id=? AND order_id=? AND status<>'SUPERSEDED' "
                        "ORDER BY generation DESC LIMIT 1",
                        (account_id, package_id, order_id),
                    ).fetchone()
                    if existing is not None:
                        outbox_id = existing[0]
                        outcome = "existing"
                        if existing[1] == "SUPERSEDED":
                            if prior is not None and prior[0] != outbox_id:
                                if prior[3] in {"AWAITING_CONFIRMATION", "PENDING", "RETRYABLE"}:
                                    connection.execute(
                                        "UPDATE shipping_sellfox_outbox SET status='SUPERSEDED', updated_at=? WHERE id=?", (now, prior[0])
                                    )
                                    connection.execute(
                                        "UPDATE shipping_sellfox_outbox SET status='AWAITING_CONFIRMATION', "
                                        "conflicts_with_outbox_id=NULL, updated_at=? WHERE id=?", (now, outbox_id)
                                    )
                                else:
                                    connection.execute(
                                        "UPDATE shipping_sellfox_outbox SET status='CONFLICT', "
                                        "conflicts_with_outbox_id=?, updated_at=? WHERE id=?", (prior[0], now, outbox_id)
                                    )
                                    outcome = "conflict"
                            else:
                                connection.execute(
                                    "UPDATE shipping_sellfox_outbox SET status='AWAITING_CONFIRMATION', "
                                    "conflicts_with_outbox_id=NULL, updated_at=? WHERE id=?", (now, outbox_id)
                                )
                        counts[outcome] += 1
                    else:
                        generation = (prior[1] if prior else 0) + 1
                        status = "AWAITING_CONFIRMATION"
                        conflicts_with = None
                        outcome = "created"
                        if prior is not None and prior[2] != tracking:
                            if prior[3] in {"AWAITING_CONFIRMATION", "PENDING", "RETRYABLE"}:
                                connection.execute("UPDATE shipping_sellfox_outbox SET status='SUPERSEDED', updated_at=? WHERE id=?", (now, prior[0]))
                            else:
                                status = "CONFLICT"
                                conflicts_with = prior[0]
                                outcome = "conflict"
                        connection.execute(
                            "INSERT INTO shipping_sellfox_outbox "
                            "(account_id, package_id, order_id, generation, tracking_number, candidate_key, status, "
                            "request_hash, attempt_count, lease_owner, lease_token, confirmed_by, last_error_class, "
                            "last_error_summary, conflicts_with_outbox_id, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, '', 0, '', '', '', '', '', ?, ?, ?)",
                            (account_id, package_id, order_id, generation, tracking, candidate_key, status, conflicts_with, now, now),
                        )
                        outbox_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                        counts[outcome] += 1
                    connection.execute(
                        "INSERT OR IGNORE INTO shipping_sellfox_outbox_sources "
                        "(outbox_id, source_type, source_id, created_at) VALUES (?, ?, ?, ?)",
                        (outbox_id, source_type, source_id, now),
                    )
                    results.append({"package_sn": package_sn, "external_order_id": external_order_id, "outbox_id": outbox_id, "outcome": outcome})
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.append_audit_event(
            actor=actor_name, action="sellfox_outbox.finalize_tracking",
            entity_type="shipping_package", entity_id=package_sn,
            summary=json.dumps(counts, sort_keys=True),
        )
        return SellfoxOutboxCandidateReport(counts=counts, results=tuple(results))

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
        skipped_sns: list[str] | None = None,
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
            batch.skipped_count = len(skipped_sns or [])
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
            for sn in (skipped_sns or []):
                self._upsert_batch_package(
                    session, batch_id, sn, "tracking_skipped", "outbox candidate skipped"
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

    def resolve_submission_scope_block(
        self,
        *,
        account_key: str,
        package_sn: str,
        external_order_id: str,
        actor: str,
    ) -> int:
        """Clear an UNKNOWN_BLOCKED submission scope and reset its UNKNOWN intents.

        A human confirms the prior ambiguous submit did NOT apply (e.g. a 4xx
        rejection), so the package can be re-submitted. Records an audit event.
        Returns the scope id.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            package = session.scalar(
                select(PackageRow).where(
                    PackageRow.account_id == account.id,
                    PackageRow.package_sn == package_sn,
                )
            )
            order = session.scalar(
                select(OrderRow).where(
                    OrderRow.account_id == account.id,
                    OrderRow.external_order_id == external_order_id,
                )
            )
            if package is None or order is None:
                raise LookupError(
                    f"package {package_sn} or order {external_order_id} not found"
                )
            scope = session.scalar(
                select(SubmissionScopeRow).where(
                    SubmissionScopeRow.account_id == account.id,
                    SubmissionScopeRow.package_id == package.id,
                    SubmissionScopeRow.order_id == order.id,
                )
            )
            if scope is None:
                raise LookupError(
                    f"no submission scope for {package_sn} / {external_order_id}"
                )
            if scope.status == "UNKNOWN_BLOCKED":
                scope.status = "OPEN"
                scope.updated_at = now
            # Reset stale UNKNOWN intents back to READY so they can be re-submitted.
            for intent in session.scalars(
                select(SubmissionIntentRow).where(
                    SubmissionIntentRow.scope_id == scope.id,
                    SubmissionIntentRow.status == "UNKNOWN",
                )
            ):
                intent.status = "READY"
                intent.updated_at = now
            session.add(
                AuditEventRow(
                    actor=actor,
                    action="submission.scope_unblock",
                    entity_type="submission_scope",
                    entity_id=str(scope.id),
                    summary=f"unblock {package_sn} / {external_order_id}",
                    created_at=now,
                )
            )
            return scope.id

    def resolve_unknown_blocked_scope(
        self, *, intent_id: int, actor: str, note: str
    ) -> SubmissionIntentRecord:
        """Human-approved, audited unblock of an UNKNOWN_BLOCKED submission scope.

        Only call after checking that the failed attempt had no Sellfox side
        effect (for example a 401/403 before send, or readback confirms trackNo
        unchanged). The old UNKNOWN attempt remains as audit; the intent is
        returned to READY so the same request can be submitted again.
        """
        actor_s = (actor or "").strip()
        note_s = (note or "").strip()
        if not actor_s:
            raise ValueError("actor is required")
        if not note_s:
            raise ValueError("note is required")
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            intent = session.get(SubmissionIntentRow, intent_id)
            if intent is None:
                raise LookupError(f"Intent {intent_id} not found")
            scope = session.get(SubmissionScopeRow, intent.scope_id)
            if scope is None or scope.status != "UNKNOWN_BLOCKED":
                raise RuntimeError(
                    f"scope for intent {intent_id} is not UNKNOWN_BLOCKED"
                )
            if intent.status not in {"UNKNOWN", "READY", "FAILED"}:
                raise RuntimeError(
                    f"intent {intent_id} status {intent.status} cannot be safely reset"
                )
            scope.status = "OPEN"
            scope.updated_at = now
            if intent.status == "UNKNOWN":
                intent.status = "READY"
            intent.updated_at = now
        self.append_audit_event(
            actor=actor_s,
            action="submission.scope.resolve_unknown_blocked",
            entity_type="submission_intent",
            entity_id=str(intent_id),
            summary=note_s,
        )
        record = self.get_submission_intent(intent_id)
        assert record is not None
        return record

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
        date_field: str = "label",
        has_label: str | None = None,
        exclude_shops: list[str] | None = None,
        tongtool: str | None = None,
        tongtool_warehouse: str | None = None,
        tongtool_method: str | None = None,
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
            if tongtool in ("yes", "no"):
                query = query.where(
                    PackageRow.is_tongtool == (True if tongtool == "yes" else False)
                )
            if tongtool_warehouse:
                query = query.where(
                    PackageRow.tongtool_shipping_warehouse == tongtool_warehouse
                )
            if tongtool_method:
                query = query.where(
                    PackageRow.tongtool_shipping_method == tongtool_method
                )
            if has_label in ("yes", "no"):
                label_exists = (
                    select(ShippingLabelRow.id)
                    .where(ShippingLabelRow.package_id == PackageRow.id)
                    .where(ShippingLabelRow.status != "cancelled")
                    .exists()
                )
                query = query.where(label_exists if has_label == "yes" else ~label_exists)
            if exclude_shops:
                query = query.where(
                    PackageRow.shop_name.notin_(exclude_shops)
                )
            if date_start is not None or date_end is not None:
                if date_field == "order":
                    query = query.join(
                        PackageOrderRow,
                        PackageOrderRow.package_id == PackageRow.id,
                    ).join(
                        OrderRow,
                        OrderRow.id == PackageOrderRow.order_id,
                    )
                    if date_start is not None:
                        query = query.where(OrderRow.purchase_date >= date_start)
                    if date_end is not None:
                        query = query.where(OrderRow.purchase_date < date_end + "T23:59:59")
                else:
                    query = query.join(
                        ShippingLabelRow,
                        ShippingLabelRow.package_id == PackageRow.id,
                        isouter=True,
                    )
                    query = query.where(
                        or_(
                            ShippingLabelRow.id.is_(None),
                            ShippingLabelRow.status != "cancelled",
                        )
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
                # Earliest purchase date among all orders
                purchase_date = session.scalar(
                    select(func.min(OrderRow.purchase_date))
                    .select_from(PackageOrderRow)
                    .join(OrderRow, OrderRow.id == PackageOrderRow.order_id)
                    .where(PackageOrderRow.package_id == package.id)
                )
                # Earliest non-cancelled label creation time
                label_created_at = session.scalar(
                    select(func.min(ShippingLabelRow.created_at))
                    .where(ShippingLabelRow.package_id == package.id)
                    .where(ShippingLabelRow.status != "cancelled")
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
                        purchase_date=purchase_date,
                        label_created_at=label_created_at,
                        is_tongtool=bool(package.is_tongtool),
                        tongtool_p_numbers=package.tongtool_p_numbers or "",
                        tongtool_shipping_warehouse=package.tongtool_shipping_warehouse or "",
                        tongtool_shipping_method=package.tongtool_shipping_method or "",
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
        date_field: str = "label",
        has_label: str | None = None,
        exclude_shops: list[str] | None = None,
        tongtool: str | None = None,
        tongtool_warehouse: str | None = None,
        tongtool_method: str | None = None,
    ) -> int:
        with self._session_factory() as session:
            query = (
                select(func.count(func.distinct(PackageRow.id)))
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
            if tongtool in ("yes", "no"):
                query = query.where(
                    PackageRow.is_tongtool == (True if tongtool == "yes" else False)
                )
            if tongtool_warehouse:
                query = query.where(
                    PackageRow.tongtool_shipping_warehouse == tongtool_warehouse
                )
            if tongtool_method:
                query = query.where(
                    PackageRow.tongtool_shipping_method == tongtool_method
                )
            if has_label in ("yes", "no"):
                label_exists = (
                    select(ShippingLabelRow.id)
                    .where(ShippingLabelRow.package_id == PackageRow.id)
                    .where(ShippingLabelRow.status != "cancelled")
                    .exists()
                )
                query = query.where(label_exists if has_label == "yes" else ~label_exists)
            if exclude_shops:
                query = query.where(
                    PackageRow.shop_name.notin_(exclude_shops)
                )
            if date_start is not None or date_end is not None:
                if date_field == "order":
                    query = query.join(
                        PackageOrderRow, PackageOrderRow.package_id == PackageRow.id
                    ).join(OrderRow, OrderRow.id == PackageOrderRow.order_id)
                    if date_start is not None:
                        query = query.where(OrderRow.purchase_date >= date_start)
                    if date_end is not None:
                        query = query.where(OrderRow.purchase_date < date_end + "T23:59:59")
                else:
                    query = query.join(
                        ShippingLabelRow, ShippingLabelRow.package_id == PackageRow.id, isouter=True
                    )
                    query = query.where(
                        or_(
                            ShippingLabelRow.id.is_(None),
                            ShippingLabelRow.status != "cancelled",
                        )
                    )
                    if date_start is not None:
                        query = query.where(ShippingLabelRow.created_at >= date_start)
                    if date_end is not None:
                        query = query.where(ShippingLabelRow.created_at < date_end + "T23:59:59")
                query = query.distinct()
            return session.scalar(query) or 0

    def mark_tongtool(
        self,
        *,
        account_key: str,
        package_sn: str,
        p_numbers: list[str] | None = None,
        shipping_warehouse: str = "",
        shipping_method: str = "",
    ) -> bool:
        """Persist the 通途订单 mark on a package (matched via EN Tongtool Package)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(PackageRow).where(
                    PackageRow.account_id == account.id,
                    PackageRow.package_sn == package_sn,
                )
            )
            if row is None:
                return False
            row.is_tongtool = True
            row.tongtool_p_numbers = ",".join(
                dict.fromkeys(p for p in (p_numbers or []) if p)
            )
            if shipping_warehouse:
                row.tongtool_shipping_warehouse = shipping_warehouse
            if shipping_method:
                row.tongtool_shipping_method = shipping_method
            session.add(
                AuditEventRow(
                    actor="tongtool",
                    action="package.tongtool_mark",
                    entity_type="shipping_package",
                    entity_id=package_sn,
                    summary=f"mark tongtool p_numbers={row.tongtool_p_numbers} warehouse={shipping_warehouse} method={shipping_method}",
                    created_at=now,
                )
            )
            return True

    def clear_tongtool(self, *, account_key: str, package_sn: str) -> bool:
        """Clear the 通途订单 mark on a package."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(PackageRow).where(
                    PackageRow.account_id == account.id,
                    PackageRow.package_sn == package_sn,
                )
            )
            if row is None:
                return False
            row.is_tongtool = False
            row.tongtool_p_numbers = ""
            row.tongtool_shipping_warehouse = ""
            row.tongtool_shipping_method = ""
            session.add(
                AuditEventRow(
                    actor="tongtool",
                    action="package.tongtool_unmark",
                    entity_type="shipping_package",
                    entity_id=package_sn,
                    summary="clear tongtool mark",
                    created_at=now,
                )
            )
            return True

    def get_tongtool_mark(
        self, *, account_key: str, package_sn: str
    ) -> dict:
        """Return the 通途订单 mark for a package (for detail page)."""
        with self._session_factory() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(PackageRow).where(
                    PackageRow.account_id == account.id,
                    PackageRow.package_sn == package_sn,
                )
            )
            if row is None:
                return {"is_tongtool": False, "tongtool_p_numbers": "", "tongtool_shipping_warehouse": "", "tongtool_shipping_method": ""}
            return {
                "is_tongtool": bool(row.is_tongtool),
                "tongtool_p_numbers": row.tongtool_p_numbers or "",
                "tongtool_shipping_warehouse": row.tongtool_shipping_warehouse or "",
                "tongtool_shipping_method": row.tongtool_shipping_method or "",
            }

    def index_packages_by_external_order(
        self, account_key: str
    ) -> dict[str, list[str]]:
        """external_order_id (Amazon 订单号) -> [package_sn, ...] 索引，供通途匹配。"""
        with self._session_factory() as session:
            account = self._get_or_create_account(session, account_key)
            rows = (
                session.execute(
                    select(PackageRow.package_sn, OrderRow.external_order_id)
                    .select_from(PackageRow)
                    .join(
                        PackageOrderRow,
                        PackageOrderRow.package_id == PackageRow.id,
                    )
                    .join(OrderRow, OrderRow.id == PackageOrderRow.order_id)
                    .where(PackageRow.account_id == account.id)
                )
                .all()
            )
            index: dict[str, list[str]] = {}
            for package_sn, ext_id in rows:
                if ext_id:
                    index.setdefault(ext_id, []).append(package_sn)
            return index

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

    def get_sellfox_writeback_policy(
        self, account_key: str, *, create: bool = True
    ) -> SellfoxWritebackPolicyRecord:
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(SellfoxWritebackPolicyRow).where(
                    SellfoxWritebackPolicyRow.account_id == account.id
                )
            )
            if row is None:
                if not create:
                    return SellfoxWritebackPolicyRecord(
                        account_key=account.account_key,
                        mode="DISABLED",
                        capability_status="UNVERIFIED",
                    )
                row = SellfoxWritebackPolicyRow(
                    account_id=account.id,
                    mode="DISABLED",
                    capability_status="UNVERIFIED",
                )
                session.add(row)
                session.flush()
            return SellfoxWritebackPolicyRecord(
                account_key=account.account_key,
                mode=row.mode,
                capability_status=row.capability_status,
                evidence_ref=row.evidence_ref or "",
                approved_by=row.approved_by or "",
                approved_at=row.approved_at,
            )

    def create_sellfox_outbox_candidates(
        self,
        *,
        account_key: str,
        package_sn: str,
        tracking_number: str,
        source_type: str,
        source_id: str,
        actor: str,
        apply: bool = True,
    ) -> SellfoxOutboxCandidateReport:
        """Create order-level writeback candidates without external HTTP."""
        source_type = (source_type or "").strip()
        source_id = (source_id or "").strip()
        actor = (actor or "").strip()
        tracking = (tracking_number or "").strip()
        if source_type not in {"api_label", "excel_tracking_import"}:
            raise ValueError("unsupported Sellfox outbox source_type")
        if not source_id:
            raise ValueError("source_id is required")
        if apply and not actor:
            raise ValueError("actor is required when applying candidates")

        counts = {
            "input": 0,
            "created": 0,
            "existing": 0,
            "skipped": 0,
            "conflict": 0,
            "failed": 0,
        }
        results: list[dict[str, object]] = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        session = self._session_factory()
        try:
            account = session.scalar(
                select(ShippingAccountRow).where(
                    ShippingAccountRow.account_key == account_key
                )
            )
            package = (
                session.scalar(
                    select(PackageRow).where(
                        PackageRow.account_id == account.id,
                        PackageRow.package_sn == package_sn,
                    )
                )
                if account is not None
                else None
            )
            if package is None:
                counts["input"] = 1
                counts["failed"] = 1
                results.append({"package_sn": package_sn, "outcome": "failed", "reason": "package_not_found"})
            else:
                report = self._create_sellfox_outbox_candidates_in_session(
                    session,
                    account=account,
                    package=package,
                    tracking_number=tracking,
                    source_type=source_type,
                    source_id=source_id,
                    now=now,
                    require_active_label=True,
                )
                counts = dict(report.counts)
                results = [dict(item) for item in report.results]

            if apply:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        if apply and actor:
            self.append_audit_event(
                actor=actor,
                action="sellfox_outbox.candidates_create",
                entity_type="shipping_package",
                entity_id=package_sn,
                summary=json.dumps(counts, sort_keys=True),
            )
        return SellfoxOutboxCandidateReport(counts=counts, results=tuple(results))

    @staticmethod
    def _add_sellfox_outbox_source(
        session: Session,
        outbox_id: int,
        source_type: str,
        source_id: str,
        created_at: datetime,
    ) -> None:
        session.execute(
            sqlite_insert(SellfoxOutboxSourceRow)
            .values(
                outbox_id=outbox_id,
                source_type=source_type,
                source_id=source_id,
                created_at=created_at,
            )
            .on_conflict_do_nothing(
                index_elements=["outbox_id", "source_type", "source_id"]
            )
        )

    def _create_sellfox_outbox_candidates_in_session(
        self,
        session: Session,
        *,
        account: ShippingAccountRow,
        package: PackageRow,
        tracking_number: str,
        source_type: str,
        source_id: str,
        now: datetime,
        require_active_label: bool = True,
    ) -> SellfoxOutboxCandidateReport:
        """Create candidates inside the caller's transaction."""
        tracking = (tracking_number or "").strip()
        counts = {
            "input": 0,
            "created": 0,
            "existing": 0,
            "skipped": 0,
            "conflict": 0,
            "failed": 0,
        }
        results: list[dict[str, object]] = []
        order_rows = session.execute(
            select(OrderRow.id, OrderRow.external_order_id)
            .join(PackageOrderRow, PackageOrderRow.order_id == OrderRow.id)
            .where(PackageOrderRow.package_id == package.id)
            .order_by(OrderRow.external_order_id)
        ).all()
        counts["input"] = max(1, len(order_rows))

        skip_reason = ""
        if not tracking or tracking == package.package_sn:
            skip_reason = "tracking_missing_or_placeholder"
        elif package.local_review_status != "approved":
            skip_reason = "package_not_approved"
        elif package.package_status in {"has_shipped", "has_canceled"}:
            skip_reason = "package_status_not_submittable"
        elif source_type == "api_label" and require_active_label:
            active_label = session.scalar(
                select(ShippingLabelRow.id).where(
                    ShippingLabelRow.package_id == package.id,
                    ShippingLabelRow.is_active.is_(True),
                    ShippingLabelRow.status != "cancelled",
                    ShippingLabelRow.tracking_number == tracking,
                )
            )
            if active_label is None:
                skip_reason = "active_label_required"

        if skip_reason:
            counts["skipped"] = counts["input"]
            results.extend(
                {
                    "package_sn": package.package_sn,
                    "external_order_id": external_order_id,
                    "outcome": "skipped",
                    "reason": skip_reason,
                }
                for _, external_order_id in (order_rows or [(0, "")])
            )
            return SellfoxOutboxCandidateReport(
                counts=counts, results=tuple(results)
            )

        if not order_rows:
            counts["skipped"] = 1
            results.append(
                {
                    "package_sn": package.package_sn,
                    "external_order_id": "",
                    "outcome": "skipped",
                    "reason": "package_has_no_orders",
                }
            )
            return SellfoxOutboxCandidateReport(
                counts=counts, results=tuple(results)
            )

        for order_id, external_order_id in order_rows:
            item_count = (
                session.scalar(
                    select(func.count())
                    .select_from(PackageItemRow)
                    .where(
                        PackageItemRow.package_id == package.id,
                        PackageItemRow.external_order_id == external_order_id,
                        PackageItemRow.order_item_id != "",
                        PackageItemRow.quantity > 0,
                    )
                )
                or 0
            )
            if item_count == 0:
                counts["skipped"] += 1
                results.append(
                    {
                        "package_sn": package.package_sn,
                        "external_order_id": external_order_id,
                        "outcome": "skipped",
                        "reason": "order_items_incomplete",
                    }
                )
                continue

            candidate_key = _sellfox_outbox_candidate_key(
                account_key=account.account_key,
                package_sn=package.package_sn,
                external_order_id=external_order_id,
                tracking_number=tracking,
            )
            existing = session.scalar(
                select(SellfoxOutboxRow).where(
                    SellfoxOutboxRow.candidate_key == candidate_key
                )
            )
            prior = session.scalar(
                select(SellfoxOutboxRow)
                .where(
                    SellfoxOutboxRow.account_id == account.id,
                    SellfoxOutboxRow.package_id == package.id,
                    SellfoxOutboxRow.order_id == order_id,
                    SellfoxOutboxRow.status != "SUPERSEDED",
                )
                .order_by(SellfoxOutboxRow.generation.desc())
                .limit(1)
            )
            if existing is not None:
                if existing.status == "SUPERSEDED":
                    if prior is not None and prior.id != existing.id:
                        if prior.status in {
                            "AWAITING_CONFIRMATION",
                            "PENDING",
                            "RETRYABLE",
                        }:
                            prior.status = "SUPERSEDED"
                            prior.updated_at = now
                            existing.status = "AWAITING_CONFIRMATION"
                            existing.updated_at = now
                            existing.conflicts_with_outbox_id = None
                        else:
                            existing.status = "CONFLICT"
                            existing.conflicts_with_outbox_id = prior.id
                            existing.updated_at = now
                    else:
                        existing.status = "AWAITING_CONFIRMATION"
                        existing.updated_at = now
                outcome = "existing"
                if existing.status == "CONFLICT":
                    outcome = "conflict"
                self._add_sellfox_outbox_source(
                    session, existing.id, source_type, source_id, now
                )
                counts[outcome] += 1
                results.append(
                    {
                        "package_sn": package.package_sn,
                        "external_order_id": external_order_id,
                        "outbox_id": existing.id,
                        "outcome": outcome,
                    }
                )
                continue

            generation = (prior.generation if prior is not None else 0) + 1
            status = "AWAITING_CONFIRMATION"
            conflicts_with = None
            outcome = "created"
            if prior is not None and prior.tracking_number != tracking:
                if prior.status in {
                    "AWAITING_CONFIRMATION",
                    "PENDING",
                    "RETRYABLE",
                }:
                    prior.status = "SUPERSEDED"
                    prior.updated_at = now
                else:
                    status = "CONFLICT"
                    conflicts_with = prior.id
                    outcome = "conflict"

            row = SellfoxOutboxRow(
                account_id=account.id,
                package_id=package.id,
                order_id=order_id,
                generation=generation,
                tracking_number=tracking,
                candidate_key=candidate_key,
                status=status,
                conflicts_with_outbox_id=conflicts_with,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            self._add_sellfox_outbox_source(
                session, row.id, source_type, source_id, now
            )
            counts[outcome] += 1
            results.append(
                {
                    "package_sn": package.package_sn,
                    "external_order_id": external_order_id,
                    "outbox_id": row.id,
                    "outcome": outcome,
                }
            )

        return SellfoxOutboxCandidateReport(counts=counts, results=tuple(results))

    def list_sellfox_outbox(
        self,
        *,
        account_key: str | None = None,
        package_sn: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SellfoxOutboxRecord]:
        with self._session_factory() as session:
            query = (
                select(
                    SellfoxOutboxRow,
                    ShippingAccountRow.account_key,
                    PackageRow.package_sn,
                    OrderRow.external_order_id,
                )
                .join(ShippingAccountRow, ShippingAccountRow.id == SellfoxOutboxRow.account_id)
                .join(PackageRow, PackageRow.id == SellfoxOutboxRow.package_id)
                .join(OrderRow, OrderRow.id == SellfoxOutboxRow.order_id)
            )
            if account_key:
                query = query.where(ShippingAccountRow.account_key == account_key)
            if package_sn:
                query = query.where(PackageRow.package_sn == package_sn)
            if status:
                query = query.where(SellfoxOutboxRow.status == status)
            rows = session.execute(
                query.order_by(
                    SellfoxOutboxRow.generation.desc(),
                    OrderRow.external_order_id,
                    SellfoxOutboxRow.id.desc(),
                ).limit(limit)
            ).all()
            return [
                self._sellfox_outbox_to_record(session, row, key, sn, external)
                for row, key, sn, external in rows
            ]

    def get_sellfox_outbox(self, outbox_id: int) -> SellfoxOutboxRecord | None:
        with self._session_factory() as session:
            result = session.execute(
                select(
                    SellfoxOutboxRow,
                    ShippingAccountRow.account_key,
                    PackageRow.package_sn,
                    OrderRow.external_order_id,
                )
                .join(ShippingAccountRow, ShippingAccountRow.id == SellfoxOutboxRow.account_id)
                .join(PackageRow, PackageRow.id == SellfoxOutboxRow.package_id)
                .join(OrderRow, OrderRow.id == SellfoxOutboxRow.order_id)
                .where(SellfoxOutboxRow.id == outbox_id)
            ).one_or_none()
            if result is None:
                return None
            row, account_key, package_sn, external_order_id = result
            return self._sellfox_outbox_to_record(
                session, row, account_key, package_sn, external_order_id
            )

    @staticmethod
    def _sellfox_outbox_to_record(
        session: Session,
        row: SellfoxOutboxRow,
        account_key: str,
        package_sn: str,
        external_order_id: str,
    ) -> SellfoxOutboxRecord:
        sources = session.scalars(
            select(SellfoxOutboxSourceRow)
            .where(SellfoxOutboxSourceRow.outbox_id == row.id)
            .order_by(SellfoxOutboxSourceRow.id)
        ).all()
        return SellfoxOutboxRecord(
            id=row.id,
            account_key=account_key,
            package_id=row.package_id,
            package_sn=package_sn,
            order_db_id=row.order_id,
            external_order_id=external_order_id,
            generation=row.generation,
            tracking_number=row.tracking_number,
            candidate_key=row.candidate_key,
            status=row.status,
            submission_intent_id=row.submission_intent_id,
            request_hash=row.request_hash or "",
            attempt_count=row.attempt_count or 0,
            conflicts_with_outbox_id=row.conflicts_with_outbox_id,
            next_attempt_at=row.next_attempt_at,
            lease_owner=row.lease_owner or "",
            lease_token=row.lease_token or "",
            lease_expires_at=row.lease_expires_at,
            confirmed_by=row.confirmed_by or "",
            confirmed_at=row.confirmed_at,
            last_error_class=row.last_error_class or "",
            last_error_summary=row.last_error_summary or "",
            sources=tuple(
                SellfoxOutboxSourceRecord(
                    source_type=source.source_type, source_id=source.source_id
                )
                for source in sources
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def set_sellfox_outbox_status(
        self, outbox_id: int, status: str
    ) -> SellfoxOutboxRecord:
        with self._session_factory.begin() as session:
            row = session.get(SellfoxOutboxRow, outbox_id)
            if row is None:
                raise LookupError(f"Sellfox outbox {outbox_id} not found")
            row.status = status
            row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.get_sellfox_outbox(outbox_id)
        assert result is not None
        return result

    def record_sellfox_writeback_capability(
        self,
        *,
        account_key: str,
        capability_status: str,
        evidence_ref: str,
        actor: str,
    ) -> SellfoxWritebackPolicyRecord:
        capability_status = (capability_status or "").strip().upper()
        evidence_ref = (evidence_ref or "").strip()
        actor = (actor or "").strip()
        allowed = {
            "UNVERIFIED",
            "SAFE_TRACKNO_ONLY",
            "UNSAFE_PLATFORM_SIDE_EFFECT",
            "INEFFECTIVE",
        }
        if capability_status not in allowed:
            raise ValueError("unsupported Sellfox writeback capability status")
        if not evidence_ref:
            raise ValueError("evidence_ref is required")
        if not actor:
            raise ValueError("actor is required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(SellfoxWritebackPolicyRow).where(
                    SellfoxWritebackPolicyRow.account_id == account.id
                )
            )
            if row is None:
                row = SellfoxWritebackPolicyRow(
                    account_id=account.id,
                    mode="DISABLED",
                    capability_status="UNVERIFIED",
                )
                session.add(row)
                session.flush()
            if capability_status == "SAFE_TRACKNO_ONLY":
                if row.mode not in {"PROBE_ONLY", "SCOPED_BATCH"}:
                    row.mode = "PROBE_ONLY"
            else:
                row.mode = "DISABLED"
            row.capability_status = capability_status
            row.evidence_ref = evidence_ref
            row.approved_by = actor
            row.approved_at = now
            row.updated_at = now
        self.append_audit_event(
            actor=actor,
            action="sellfox_outbox.capability_record",
            entity_type="shipping_account",
            entity_id=account_key,
            summary=f"capability={capability_status}",
        )
        return self.get_sellfox_writeback_policy(account_key)

    def set_sellfox_writeback_policy(
        self, *, account_key: str, mode: str, actor: str
    ) -> SellfoxWritebackPolicyRecord:
        mode = (mode or "").strip().upper()
        actor = (actor or "").strip()
        if mode not in {"DISABLED", "PROBE_ONLY", "SCOPED_BATCH"}:
            raise ValueError("unsupported Sellfox writeback policy mode")
        if not actor:
            raise ValueError("actor is required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            row = session.scalar(
                select(SellfoxWritebackPolicyRow).where(
                    SellfoxWritebackPolicyRow.account_id == account.id
                )
            )
            if row is None:
                row = SellfoxWritebackPolicyRow(
                    account_id=account.id,
                    mode="DISABLED",
                    capability_status="UNVERIFIED",
                )
                session.add(row)
                session.flush()
            if mode == "SCOPED_BATCH" and row.capability_status != "SAFE_TRACKNO_ONLY":
                raise ValueError(
                    "SCOPED_BATCH requires SAFE_TRACKNO_ONLY capability evidence"
                )
            row.mode = mode
            row.approved_by = actor
            row.updated_at = now
        self.append_audit_event(
            actor=actor,
            action="sellfox_outbox.policy_set",
            entity_type="shipping_account",
            entity_id=account_key,
            summary=f"mode={mode}",
        )
        return self.get_sellfox_writeback_policy(account_key)

    def confirm_sellfox_outbox(
        self,
        *,
        outbox_id: int,
        submission_intent_id: int,
        request_hash: str,
        actor: str,
    ) -> SellfoxOutboxRecord:
        actor = (actor or "").strip()
        if not actor:
            raise ValueError("actor is required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = session.get(SellfoxOutboxRow, outbox_id)
            if row is None:
                raise LookupError(f"Sellfox outbox {outbox_id} not found")
            allowed = SELLFOX_OUTBOX_TRANSITIONS.get(row.status, frozenset())
            if "PENDING" not in allowed:
                raise RuntimeError(
                    f"invalid transition: {row.status} -> PENDING for outbox {outbox_id}"
                )
            row.status = "PENDING"
            row.submission_intent_id = submission_intent_id
            row.request_hash = request_hash or ""
            row.confirmed_by = actor
            row.confirmed_at = now
            row.updated_at = now
            row.lease_owner = ""
            row.lease_token = ""
            row.lease_expires_at = None
            row.lease_origin_status = ""
        result = self.get_sellfox_outbox(outbox_id)
        assert result is not None
        return result

    def claim_sellfox_outbox(
        self,
        *,
        outbox_id: int,
        owner: str,
        lease_token: str,
        lease_seconds: int = 60,
    ) -> bool:
        owner = (owner or "").strip()
        lease_token = (lease_token or "").strip()
        if not owner or not lease_token:
            raise ValueError("owner and lease_token are required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        now_iso = now.isoformat(sep=" ")
        expires_iso = (now + timedelta(seconds=max(1, lease_seconds))).isoformat(sep=" ")
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT status, lease_expires_at FROM shipping_sellfox_outbox WHERE id=?", (outbox_id,),
                ).fetchone()
                if row is None:
                    return False
                status, lease_expires_at = row
                if status not in SELLFOX_OUTBOX_CLAIMABLE_STATUSES:
                    return False
                if lease_expires_at and lease_expires_at >= now_iso:
                    return False
                placeholders = ",".join("?" for _ in SELLFOX_OUTBOX_CLAIMABLE_STATUSES)
                cursor = connection.execute(
                    f"UPDATE shipping_sellfox_outbox SET status='LEASED', lease_owner=?, lease_token=?, "
                    f"lease_expires_at=?, lease_origin_status=?, updated_at=? "
                    f"WHERE id=? AND status IN ({placeholders}) "
                    f"AND (lease_expires_at IS NULL OR lease_expires_at < ?)",
                    (
                        owner,
                        lease_token,
                        expires_iso,
                        status,
                        now_iso,
                        outbox_id,
                        *tuple(SELLFOX_OUTBOX_CLAIMABLE_STATUSES),
                        now_iso,
                    ),
                )
                ok = cursor.rowcount == 1
                connection.commit()
                return ok
            except Exception:
                connection.rollback()
                raise

    def claim_due_sellfox_outbox(
        self,
        *,
        account_key: str,
        owner: str,
        lease_token: str,
        lease_seconds: int = 60,
        limit: int = 1,
    ) -> list[int]:
        owner = (owner or "").strip()
        lease_token = (lease_token or "").strip()
        if not owner or not lease_token:
            raise ValueError("owner and lease_token are required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        now_iso = now.isoformat(sep=" ")
        expires_iso = (now + timedelta(seconds=max(1, lease_seconds))).isoformat(sep=" ")
        claimed: list[int] = []
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                account_id = connection.execute(
                    "SELECT id FROM shipping_accounts WHERE account_key=?", (account_key,),
                ).fetchone()
                if account_id is None:
                    return []
                placeholders = ",".join("?" for _ in SELLFOX_OUTBOX_CLAIMABLE_STATUSES)
                rows = connection.execute(
                    f"SELECT id, status FROM shipping_sellfox_outbox WHERE account_id=? AND status IN ({placeholders}) "
                    f"AND (lease_expires_at IS NULL OR lease_expires_at < ?) "
                    f"AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                    f"ORDER BY (next_attempt_at IS NULL) ASC, next_attempt_at ASC, id ASC LIMIT ?",
                    (
                        account_id[0],
                        *tuple(SELLFOX_OUTBOX_CLAIMABLE_STATUSES),
                        now_iso,
                        now_iso,
                        max(1, limit),
                    ),
                ).fetchall()
                for outbox_id, status in rows:
                    connection.execute(
                        f"UPDATE shipping_sellfox_outbox SET status='LEASED', lease_owner=?, lease_token=?, "
                        f"lease_expires_at=?, lease_origin_status=?, updated_at=? "
                        f"WHERE id=? AND status IN ({placeholders})",
                        (
                            owner,
                            lease_token,
                            expires_iso,
                            status,
                            now_iso,
                            outbox_id,
                            *tuple(SELLFOX_OUTBOX_CLAIMABLE_STATUSES),
                        ),
                    )
                    claimed.append(outbox_id)
                connection.commit()
                return claimed
            except Exception:
                connection.rollback()
                raise

    def mark_sellfox_outbox_in_flight(
        self, *, outbox_id: int, lease_token: str
    ) -> bool:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "UPDATE shipping_sellfox_outbox SET status='IN_FLIGHT', updated_at=? "
                    "WHERE id=? AND status='LEASED' AND lease_token=?", (now_iso, outbox_id, lease_token),
                )
                ok = cursor.rowcount == 1
                connection.commit()
                return ok
            except Exception:
                connection.rollback()
                raise

    def release_sellfox_outbox_lease(
        self, *, outbox_id: int, lease_token: str
    ) -> bool:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "UPDATE shipping_sellfox_outbox SET "
                    "status=CASE WHEN lease_origin_status='' THEN 'PENDING' ELSE lease_origin_status END, "
                    "lease_owner='', lease_token='', lease_expires_at=NULL, lease_origin_status='', updated_at=? "
                    "WHERE id=? AND status='LEASED' AND lease_token=?", (now_iso, outbox_id, lease_token),
                )
                ok = cursor.rowcount == 1
                connection.commit()
                return ok
            except Exception:
                connection.rollback()
                raise

    def finish_sellfox_outbox(
        self,
        *,
        outbox_id: int,
        lease_token: str,
        status: str,
        error_class: str = "",
        error_summary: str = "",
        increment_attempt: bool = True,
        next_attempt_at: datetime | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        now_iso = now.isoformat(sep=" ")
        next_iso = next_attempt_at.isoformat(sep=" ") if next_attempt_at is not None else None
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT status, lease_token FROM shipping_sellfox_outbox WHERE id=?", (outbox_id,),
                ).fetchone()
                if row is None:
                    return False
                current_status, current_token = row
                allowed = SELLFOX_OUTBOX_TRANSITIONS.get(current_status, frozenset())
                if status not in allowed:
                    return False
                if current_status in {"LEASED", "IN_FLIGHT"} and current_token != lease_token:
                    return False
                attempt_expr = "attempt_count + 1" if increment_attempt else "attempt_count"
                connection.execute(
                    "UPDATE shipping_sellfox_outbox SET status=?, last_error_class=?, last_error_summary=?, "
                    f"next_attempt_at=?, lease_owner='', lease_token='', lease_expires_at=NULL, "
                    f"lease_origin_status='', attempt_count={attempt_expr}, updated_at=? WHERE id=?",
                    (status, error_class, error_summary, next_iso, now_iso, outbox_id),
                )
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    def recover_stale_sellfox_outbox(self, *, actor: str) -> int:
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
        recovered = 0
        expired_leases = 0
        with sqlite3.connect(self._db_path, timeout=5) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "UPDATE shipping_sellfox_outbox SET status='UNKNOWN_BLOCKED', "
                    "last_error_class='crash_recovery', last_error_summary='IN_FLIGHT found during recovery', "
                    "lease_owner='', lease_token='', lease_expires_at=NULL, lease_origin_status='', updated_at=? "
                    "WHERE status='IN_FLIGHT'",
                    (now_iso,),
                )
                recovered = int(cursor.rowcount)
                cursor = connection.execute(
                    "UPDATE shipping_sellfox_outbox SET "
                    "status=CASE WHEN lease_origin_status='' THEN 'PENDING' ELSE lease_origin_status END, "
                    "lease_owner='', lease_token='', lease_expires_at=NULL, lease_origin_status='', updated_at=? "
                    "WHERE status='LEASED' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                    (now_iso, now_iso),
                )
                expired_leases = int(cursor.rowcount)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if recovered or expired_leases:
            self.append_audit_event(
                actor=actor or "system",
                action="sellfox_outbox.recover",
                entity_type="shipping_sellfox_outbox",
                entity_id="*",
                summary=f"recovered={recovered} expired_leases={expired_leases}",
            )
        return recovered

    def list_due_sellfox_outbox(
        self,
        *,
        account_key: str,
        limit: int = 50,
    ) -> list[SellfoxOutboxRecord]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    SellfoxOutboxRow,
                    ShippingAccountRow.account_key,
                    PackageRow.package_sn,
                    OrderRow.external_order_id,
                )
                .join(ShippingAccountRow, ShippingAccountRow.id == SellfoxOutboxRow.account_id)
                .join(PackageRow, PackageRow.id == SellfoxOutboxRow.package_id)
                .join(OrderRow, OrderRow.id == SellfoxOutboxRow.order_id)
                .where(
                    ShippingAccountRow.account_key == account_key,
                    SellfoxOutboxRow.status.in_(tuple(SELLFOX_OUTBOX_CLAIMABLE_STATUSES)),
                    or_(
                        SellfoxOutboxRow.lease_expires_at.is_(None),
                        SellfoxOutboxRow.lease_expires_at < now,
                    ),
                    or_(
                        SellfoxOutboxRow.next_attempt_at.is_(None),
                        SellfoxOutboxRow.next_attempt_at <= now,
                    ),
                )
                .order_by(
                    SellfoxOutboxRow.next_attempt_at.asc(), SellfoxOutboxRow.id.asc()
                )
                .limit(limit)
            ).all()
            return [
                self._sellfox_outbox_to_record(session, row, key, sn, external)
                for row, key, sn, external in rows
            ]

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
            row = (
                session.query(PackageDimsRow)
                .filter(PackageDimsRow.package_id == package_db_id)
                .first()
            )
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
                    "error_class, error_summary, created_by, claimed_by, claim_token, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'RESERVED', '', '', 0, '', '', ?, '', '', ?, ?)",
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

    def release_active_label_operation(
        self, package_db_id: int, *, actor: str
    ) -> int:
        """Cancel stuck active operations for a package so a new one can be claimed.

        Only invoked when the caller has confirmed there is no valid active label
        (the active-label guard still blocks duplicate creation).

        Auto-releases RESERVED / ACCEPTED / LABEL_PENDING / SUCCEEDED → CANCELLED.
        UNKNOWN_BLOCKED is deliberately NOT auto-released — its carrier outcome is
        ambiguous and must go through the evidence-based resolve workflow.
        Returns the number released.
        """
        released = 0
        with self._session_factory() as session:
            rows = (
                session.query(LabelOperationRow)
                .where(LabelOperationRow.package_id == package_db_id)
                .all()
            )
            for row in rows:
                current = (row.status or "").strip()
                if current == "UNKNOWN_BLOCKED":
                    continue
                if current not in ACTIVE_LABEL_OPERATION_STATUSES and current != "SUCCEEDED":
                    continue
                try:
                    self.transition_label_operation(
                        row.id,
                        status="CANCELLED",
                        error_summary=(
                            "auto-release: no valid label; reclaimed for new creation"
                        ),
                    )
                    released += 1
                except RuntimeError:
                    # SENT without a linked label cannot be auto-released — skip.
                    continue
        if released:
            self.append_audit_event(
                actor=actor or "system",
                action="label_operation.auto_release",
                entity_type="shipping_package",
                entity_id=str(package_db_id),
                summary=f"released {released} active operation(s) for new label",
            )
        return released

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
        expected_claim_id: str | None = None,
    ) -> LabelOperationRecord | None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = session.get(LabelOperationRow, operation_id)
            if row is None:
                return None
            if (
                expected_claim_id is not None
                and row.claim_token != expected_claim_id
            ):
                raise RuntimeError(
                    f"resume lease lost for operation_id={operation_id}"
                )
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

    def resolve_unknown_blocked_operation(
        self,
        operation_id: int,
        *,
        target_status: str,
        resolution: str,
        provider_order_id: str = "",
        note: str = "",
        actor: str = "",
        evidence_id: int,
        expected_conclusion: str,
    ) -> None:
        """Human-driven resolution: bypass state machine for UNKNOWN_BLOCKED operations.

        This is a controlled, audited transition. Only valid from UNKNOWN_BLOCKED.
        Allowed targets: FAILED_SAFE, FAILED_FINAL, ACCEPTED.
        """
        from datetime import datetime, timezone

        if not (actor or "").strip():
            raise ValueError("actor is required for resolution")
        if target_status not in {"FAILED_SAFE", "FAILED_FINAL", "ACCEPTED"}:
            raise ValueError(
                f"invalid resolution target {target_status!r}"
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            row = session.get(LabelOperationRow, operation_id)
            if row is None:
                raise RuntimeError(
                    f"label operation not found: {operation_id}"
                )
            current = (row.status or "").strip()
            if current != "UNKNOWN_BLOCKED":
                raise RuntimeError(
                    f"resolve_unknown_blocked_operation requires "
                    f"UNKNOWN_BLOCKED, got {current!r} for "
                    f"operation_id={operation_id}"
                )
            evidence = session.get(InvestigationRow, evidence_id)
            if evidence is None:
                raise RuntimeError(f"evidence not found: {evidence_id}")
            if evidence.operation_id != operation_id:
                raise RuntimeError(
                    f"evidence {evidence_id} does not belong to operation {operation_id}"
                )
            if evidence.conclusion != expected_conclusion:
                raise RuntimeError(
                    f"evidence conclusion {evidence.conclusion!r} does not support "
                    f"resolution {resolution!r}"
                )
            if (
                resolution == "provide_known_id"
                and evidence.provider_order_id.strip() != provider_order_id.strip()
            ):
                raise RuntimeError(
                    "evidence provider_order_id mismatch for provide_known_id"
                )
            if not evidence.private_artifact_id and (
                evidence.evidence_type == "other" or not evidence.external_ref.strip()
            ):
                raise RuntimeError(
                    "resolution evidence requires an authoritative external_ref "
                    "or private artifact"
                )

            parts = [f"resolution={resolution}", f"actor={actor}"]
            if note.strip():
                parts.append(f"note={note.strip()[:200]}")
            audit = "; ".join(parts)

            prior = (row.error_summary or "").strip()
            row.error_summary = (
                f"{prior} | {audit}" if prior else audit
            )[:500]
            row.error_class = f"human:{resolution}"
            row.status = target_status
            row.resolution_evidence_id = evidence_id
            if provider_order_id.strip():
                row.provider_order_id = provider_order_id.strip()
            row.updated_at = now
            session.add(row)

        self.append_audit_event(
            actor=actor,
            action="label_operation.resolve_unknown_blocked",
            entity_type="shipping_label_operation",
            entity_id=str(operation_id),
            summary=(
                f"resolution={resolution} target={target_status} evidence_id={evidence_id}"
                + (f" provider_order_id={provider_order_id.strip()}"
                   if provider_order_id.strip() else "")
            )[:500],
        )

    def get_label_operation(self, operation_id: int) -> LabelOperationRecord:
        with self._session_factory() as session:
            row = session.get(LabelOperationRow, operation_id)
            if row is None:
                raise RuntimeError(f"label operation not found: {operation_id}")
            account = session.get(ShippingAccountRow, row.account_id)
            return _label_operation_to_record(
                account.account_key if account else "", row
            )

    def acquire_resume_lease(
        self, operation_id: int, *, actor: str, lease_seconds: int = 300
    ) -> str | None:
        """Atomically acquire a lease on an existing operation for exclusive resume.

        Only succeeds when the operation is in ACCEPTED or LABEL_PENDING
        and either unclaimed or the previous lease has expired.
        Returns True if the lease was acquired, False otherwise.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expiry = now - timedelta(seconds=lease_seconds)
        now_iso = now.isoformat(sep=" ")
        expiry_iso = expiry.isoformat(sep=" ")
        token = uuid.uuid4().hex
        connection = sqlite3.connect(self._db_path, timeout=30)
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE shipping_label_operations "
                "SET claimed_by = ?, claimed_at = ?, claim_token = ? "
                "WHERE id = ? AND status IN ('ACCEPTED', 'LABEL_PENDING') "
                "AND (claimed_by = '' OR claimed_by IS NULL OR claimed_at < ?)",
                (actor, now_iso, token, operation_id, expiry_iso),
            )
            connection.commit()
            return token if cursor.rowcount == 1 else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release_resume_lease(self, operation_id: int, *, claim_id: str) -> bool:
        """Release the resume lease on a label operation."""
        with self._session_factory.begin() as session:
            result = session.query(LabelOperationRow).where(
                LabelOperationRow.id == operation_id,
                LabelOperationRow.claim_token == claim_id,
            ).update(
                {
                    LabelOperationRow.claimed_by: "",
                    LabelOperationRow.claimed_at: None,
                    LabelOperationRow.claim_token: "",
                },
                synchronize_session=False,
            )
            return result == 1

    def add_investigation(
        self,
        *,
        operation_id: int,
        evidence_type: str,
        conclusion: str,
        provider_order_id: str = "",
        actor: str,
        external_ref: str = "",
        private_artifact_id: int | None = None,
        note: str = "",
    ) -> InvestigationRecord:
        """Append an investigation record. Append-only — cannot modify or delete."""
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            inv = InvestigationRow(
                operation_id=operation_id,
                evidence_type=evidence_type,
                conclusion=conclusion,
                provider_order_id=provider_order_id,
                external_ref=external_ref,
                private_artifact_id=private_artifact_id,
                note=note,
                actor=actor,
                created_at=now,
            )
            session.add(inv)
            session.flush()
            return InvestigationRecord(
                id=inv.id,
                operation_id=inv.operation_id,
                evidence_type=inv.evidence_type,
                conclusion=inv.conclusion,
                provider_order_id=inv.provider_order_id,
                external_ref=inv.external_ref,
                private_artifact_id=inv.private_artifact_id,
                note=inv.note,
                actor=inv.actor,
                created_at=inv.created_at,
            )

    def get_investigations(
        self, operation_id: int
    ) -> list[InvestigationRecord]:
        """List all investigation records for an operation."""
        with self._session_factory() as session:
            rows = (
                session.query(InvestigationRow)
                .where(InvestigationRow.operation_id == operation_id)
                .order_by(InvestigationRow.created_at.asc())
                .all()
            )
            return [
                InvestigationRecord(
                    id=r.id,
                    operation_id=r.operation_id,
                    evidence_type=r.evidence_type,
                    conclusion=r.conclusion,
                    provider_order_id=r.provider_order_id,
                    external_ref=r.external_ref,
                    private_artifact_id=r.private_artifact_id,
                    note=r.note,
                    actor=r.actor,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def get_investigation(self, investigation_id: int) -> InvestigationRecord:
        """Get a single investigation record by id."""
        with self._session_factory() as session:
            row = session.get(InvestigationRow, investigation_id)
            if row is None:
                raise RuntimeError(f"investigation not found: {investigation_id}")
            return InvestigationRecord(
                id=row.id,
                operation_id=row.operation_id,
                evidence_type=row.evidence_type,
                conclusion=row.conclusion,
                provider_order_id=row.provider_order_id,
                external_ref=row.external_ref,
                private_artifact_id=row.private_artifact_id,
                note=row.note,
                actor=row.actor,
                created_at=row.created_at,
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
        derived_reference_no: str = "",
        expected_claim_id: str | None = None,
    ) -> ShippingLabelRecord:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
            package = session.get(PackageRow, package_db_id)
            if package is None or package.account_id != account.id:
                raise LookupError(f"package not found: {package_db_id}")

            operation = None
            if operation_id is not None:
                operation = session.get(LabelOperationRow, operation_id)
                if operation is None or operation.package_id != package_db_id:
                    raise LookupError(f"label operation not found: {operation_id}")
                if (
                    expected_claim_id is not None
                    and operation.claim_token != expected_claim_id
                ):
                    raise RuntimeError(
                        f"resume lease lost for operation_id={operation_id}"
                    )
                if operation.status not in {
                    "SENT",
                    "ACCEPTED",
                    "LABEL_PENDING",
                    "SUCCEEDED",
                }:
                    raise RuntimeError(
                        f"invalid transition: {operation.status} -> SUCCEEDED "
                        f"for operation_id={operation_id}"
                    )
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
                derived_reference_no=derived_reference_no,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            label_id = int(row.id)

            if operation is not None:
                package.tracking_number = tracking_number
                operation.status = "SUCCEEDED"
                operation.tracking_number = tracking_number
                operation.updated_at = now
                self._create_sellfox_outbox_candidates_in_session(
                    session,
                    account=account,
                    package=package,
                    tracking_number=tracking_number,
                    source_type="api_label",
                    source_id=f"label:{label_id}:operation:{operation_id}",
                    now=now,
                )
            session.add(
                AuditEventRow(
                    actor=created_by,
                    action="labels.create",
                    entity_type="shipping_label",
                    entity_id=str(label_id),
                    summary=(
                        f"{carrier} tracking={tracking_number} "
                        f"order={carrier_order_id}"
                    ),
                    created_at=now,
                )
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
        # Only overwrite address fields with non-empty incoming values
        if address.name:
            package.address_name = address.name
        if address.company:
            package.address_company = address.company
        if address.address_line_1:
            package.address_line_1 = address.address_line_1
        if address.address_line_2:
            package.address_line_2 = address.address_line_2
        if address.city:
            package.address_city = address.city
        if address.state_or_region:
            package.address_state_or_region = address.state_or_region
        if address.postal_code:
            package.address_postal_code = address.postal_code
        if address.country:
            package.address_country = address.country
        if address.country_code:
            package.address_country_code = address.country_code
        if address.phone:
            package.address_phone = address.phone
        if address.mobile:
            package.address_mobile = address.mobile
        if address.email:
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
        scope_id=int(row.scope_id or 0),
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
        derived_reference_no=row.derived_reference_no or "",
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
        resolution_evidence_id=row.resolution_evidence_id,
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


def _sellfox_outbox_candidate_key(
    *,
    account_key: str,
    package_sn: str,
    external_order_id: str,
    tracking_number: str,
) -> str:
    canonical = json.dumps(
        {
            "account_key": account_key,
            "package_sn": package_sn,
            "external_order_id": external_order_id,
            "tracking_number": tracking_number,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


SELLFOX_OUTBOX_CLAIMABLE_STATUSES = frozenset({
    "PENDING",
    "RETRYABLE",
    "VERIFY_PENDING",
})

SELLFOX_OUTBOX_TRANSITIONS: dict[str, frozenset[str]] = {
    "AWAITING_CONFIRMATION": frozenset({"PENDING"}),
    "PENDING": frozenset({"LEASED", "MANUAL_REVIEW", "SUPERSEDED"}),
    "RETRYABLE": frozenset({"LEASED", "MANUAL_REVIEW"}),
    "VERIFY_PENDING": frozenset({
        "VERIFY_PENDING",
        "VERIFIED",
        "CONFLICT",
        "MANUAL_REVIEW",
        "UNKNOWN_BLOCKED",
    }),
    "LEASED": frozenset({
        "PENDING",
        "IN_FLIGHT",
        "VERIFY_PENDING",
        "VERIFIED",
        "RETRYABLE",
        "MANUAL_REVIEW",
        "UNKNOWN_BLOCKED",
        "FAILED_FINAL",
        "CONFLICT",
    }),
    "IN_FLIGHT": frozenset({
        "VERIFY_PENDING",
        "VERIFIED",
        "RETRYABLE",
        "MANUAL_REVIEW",
        "UNKNOWN_BLOCKED",
        "FAILED_FINAL",
        "CONFLICT",
    }),
    "UNKNOWN_BLOCKED": frozenset(),
    "MANUAL_REVIEW": frozenset(),
    "FAILED_FINAL": frozenset(),
    "VERIFIED": frozenset(),
    "CONFLICT": frozenset(),
    "SUPERSEDED": frozenset(),
}

SELLFOX_OUTBOX_RETRY_BACKOFF_SECONDS = (60, 300, 900, 3600, 21600)
SELLFOX_OUTBOX_VERIFY_BACKOFF_SECONDS = (30, 120, 300, 900)

def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def _initialize_sqlite(path: Path) -> None:
    with sqlite3.connect(path, timeout=5) as connection:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
