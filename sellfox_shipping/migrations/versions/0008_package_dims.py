"""Add shipping_package_dims for merged package-level dims.

Revision ID: 0008_package_dims
Revises: 0007_submit_rate_gate
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_package_dims"
down_revision: Union[str, Sequence[str], None] = "0007_submit_rate_gate"
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
    if "shipping_package_dims" not in tables:
        op.create_table(
            "shipping_package_dims",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "package_id",
                sa.Integer,
                sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"),
                unique=True,
                nullable=False,
            ),
            sa.Column("weight_kg", sa.Float, default=0),
            sa.Column("length_cm", sa.Float, default=0),
            sa.Column("width_cm", sa.Float, default=0),
            sa.Column("height_cm", sa.Float, default=0),
            sa.Column("sku_count", sa.Integer, default=0),
            sa.Column(
                "computed_at",
                sa.DateTime,
                server_default=sa.func.current_timestamp(),
            ),
        )


def downgrade() -> None:
    op.drop_table("shipping_package_dims")
