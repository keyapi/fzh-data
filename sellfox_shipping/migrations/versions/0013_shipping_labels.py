"""Add shipping_labels for carrier label creation tracking.

Revision ID: 0013_shipping_labels
Revises: 0012_package_rates_address_type
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_shipping_labels"
down_revision: Union[str, Sequence[str], None] = "0012_package_rates_address_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "shipping_labels" not in tables:
        op.create_table(
            "shipping_labels",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "account_id",
                sa.Integer,
                sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "package_id",
                sa.Integer,
                sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("carrier", sa.String, default=""),
            sa.Column("service_level", sa.String, default=""),
            sa.Column("tracking_number", sa.String, default=""),
            sa.Column("carrier_order_id", sa.String, default=""),
            sa.Column("request_id", sa.String, default=""),
            sa.Column("label_url", sa.Text, default=""),
            sa.Column(
                "artifact_id",
                sa.Integer,
                sa.ForeignKey("shipping_artifacts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("label_format", sa.String, default="PDF"),
            sa.Column("total_amount", sa.Float, nullable=True),
            sa.Column("currency", sa.String, default="USD"),
            sa.Column("status", sa.String, default="pending"),
            sa.Column("carrier_response_json", sa.Text, default=""),
            sa.Column("created_by", sa.String, default=""),
            sa.Column(
                "created_at",
                sa.DateTime,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.create_index(
            "ix_shipping_labels_package_id",
            "shipping_labels",
            ["package_id"],
        )
        op.create_index(
            "ix_shipping_labels_tracking",
            "shipping_labels",
            ["tracking_number"],
        )


def downgrade() -> None:
    op.drop_table("shipping_labels")
