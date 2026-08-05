"""Add label acquisition operation safety.

Revision ID: 0015_label_acquisition_safety
Revises: 0014_carton_override_item_name
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_label_acquisition_safety"
down_revision: Union[str, Sequence[str], None] = "0014_carton_override_item_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE_OPERATION_STATUSES = (
    "RESERVED",
    "SENT",
    "ACCEPTED",
    "LABEL_PENDING",
    "UNKNOWN_BLOCKED",
)


def _tables(bind) -> set[str]:
    return {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _columns(bind, table: str) -> set[str]:
    return {row[1] for row in bind.exec_driver_sql(f"PRAGMA table_info('{table}')")}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "shipping_labels" in tables:
        duplicate_rows = bind.exec_driver_sql(
            """
            SELECT package_id, group_concat(id), count(*)
            FROM shipping_labels
            WHERE coalesce(status, '') != 'cancelled'
            GROUP BY package_id
            HAVING count(*) > 1
            """
        ).fetchall()
        if duplicate_rows:
            details = "; ".join(
                f"package_id={row[0]} label_ids={row[1]}" for row in duplicate_rows
            )
            raise RuntimeError(
                "Cannot add active label uniqueness; resolve duplicate active labels: "
                + details
            )

        cols = _columns(bind, "shipping_labels")
        if "operation_id" not in cols:
            op.add_column("shipping_labels", sa.Column("operation_id", sa.Integer(), nullable=True))
        if "is_active" not in cols:
            op.add_column(
                "shipping_labels",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            )
            bind.exec_driver_sql(
                "UPDATE shipping_labels SET is_active = CASE WHEN coalesce(status, '') = 'cancelled' THEN 0 ELSE 1 END"
            )

    if "shipping_label_operations" not in tables:
        op.create_table(
            "shipping_label_operations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("package_id", sa.Integer(), sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"), nullable=False),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("carrier", sa.String(), nullable=False, server_default=""),
            sa.Column("service_level", sa.String(), nullable=False, server_default=""),
            sa.Column("idempotency_key", sa.String(), nullable=False, server_default=""),
            sa.Column("request_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="RESERVED"),
            sa.Column("provider_order_id", sa.String(), nullable=False, server_default=""),
            sa.Column("tracking_number", sa.String(), nullable=False, server_default=""),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_class", sa.String(), nullable=False, server_default=""),
            sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
        )
        op.create_index("ix_label_operations_package", "shipping_label_operations", ["package_id"])
        op.create_index("ix_label_operations_status", "shipping_label_operations", ["status"])

    if "shipping_labels" in _tables(bind):
        indexes = {row[1] for row in bind.exec_driver_sql("PRAGMA index_list('shipping_labels')")}
        if "uq_shipping_labels_one_active_per_package" not in indexes:
            bind.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_shipping_labels_one_active_per_package "
                "ON shipping_labels(package_id) WHERE is_active = 1"
            )

    indexes = {row[1] for row in bind.exec_driver_sql("PRAGMA index_list('shipping_label_operations')")}
    if "uq_label_operations_one_active_per_package" not in indexes:
        statuses = ", ".join(f"'{s}'" for s in ACTIVE_OPERATION_STATUSES)
        bind.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_label_operations_one_active_per_package "
            f"ON shipping_label_operations(package_id) WHERE status IN ({statuses})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "shipping_label_operations" in tables:
        op.drop_table("shipping_label_operations")
    if "shipping_labels" in tables:
        # SQLite DROP COLUMN is intentionally omitted for dev downgrade.
        pass
