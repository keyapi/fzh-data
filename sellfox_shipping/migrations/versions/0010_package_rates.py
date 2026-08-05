"""Add shipping_package_rates for rate quote history.

Revision ID: 0010_package_rates
Revises: 0009_package_routing
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_package_rates"
down_revision: Union[str, Sequence[str], None] = "0009_package_routing"
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
    if "shipping_package_rates" not in tables:
        op.create_table(
            "shipping_package_rates",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "package_id",
                sa.Integer,
                sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("carrier", sa.String, default=""),
            sa.Column("service", sa.String, default=""),
            sa.Column("total_amount", sa.Float, nullable=True),
            sa.Column("currency", sa.String, default="USD"),
            sa.Column("billing_weight", sa.Float, nullable=True),
            sa.Column("zone", sa.String, default=""),
            sa.Column("channel", sa.String, default=""),
            sa.Column("max_side_in", sa.Float, nullable=True),
            sa.Column("weight_lb", sa.Float, nullable=True),
            sa.Column("is_fedex", sa.Boolean, default=False),
            sa.Column(
                "fetched_at",
                sa.DateTime,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.create_index(
            "ix_shipping_package_rates_package_id",
            "shipping_package_rates",
            ["package_id"],
        )


def downgrade() -> None:
    op.drop_table("shipping_package_rates")
