"""Add local_review_status for package review workflow.

Revision ID: 0002_local_review_status
Revises: 0001_package_schema
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_local_review_status"
down_revision: Union[str, Sequence[str], None] = "0001_package_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        row[1]
        for row in bind.exec_driver_sql("PRAGMA table_info(shipping_packages)")
    }
    if "local_review_status" not in columns:
        op.add_column(
            "shipping_packages",
            sa.Column(
                "local_review_status",
                sa.String(),
                nullable=False,
                server_default="pending",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {
        row[1]
        for row in bind.exec_driver_sql("PRAGMA table_info(shipping_packages)")
    }
    if "local_review_status" in columns:
        op.drop_column("shipping_packages", "local_review_status")
