"""SQLAlchemy persistence for the package-centric workflow."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
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


@dataclass(frozen=True)
class UpsertOutcome:
    package_id: int
    created: bool


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
        digest = hashlib.sha256(content).hexdigest()
        relpath = f"by-hash/{digest[:2]}/{digest}"
        blob_path = self.artifacts_root / relpath
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            blob_path.write_bytes(content)
        mime = mime_type or _guess_mime(name)
        with self._session_factory.begin() as session:
            account = self._get_or_create_account(session, account_key)
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
            summary=f"{kind_s} {name} sha256={digest[:12]}…",
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

    def list_packages(
        self,
        *,
        account_key: str,
        package_status: str | None = None,
        channel_name: str | None = None,
        local_review_status: str | None = None,
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
            return session.scalar(query) or 0

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


def _guess_mime(file_name: str) -> str:
    lower = file_name.lower()
    if lower.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if lower.endswith(".xls"):
        return "application/vnd.ms-excel"
    if lower.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def _initialize_sqlite(path: Path) -> None:
    with sqlite3.connect(path, timeout=5) as connection:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
