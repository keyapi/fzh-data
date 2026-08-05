"""Add shipping_package_routing for persisted routing decisions.

Revision ID: 0009_package_routing
Revises: 0008_package_dims
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_package_routing"
down_revision: Union[str, Sequence[str], None] = "0008_package_dims"
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
    if "shipping_package_routing" not in tables:
        op.create_table(
            "shipping_package_routing",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "package_id",
                sa.Integer,
                sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"),
                unique=True,
                nullable=False,
            ),
            sa.Column("carrier", sa.String, default=""),
            sa.Column("label", sa.String, default=""),
            sa.Column("reason", sa.String, default=""),
            sa.Column("rule_name", sa.String, default=""),
            sa.Column("matched", sa.Boolean, default=False),
            sa.Column(
                "computed_at",
                sa.DateTime,
                server_default=sa.func.current_timestamp(),
            ),
        )


def downgrade() -> None:
    op.drop_table("shipping_package_routing")
