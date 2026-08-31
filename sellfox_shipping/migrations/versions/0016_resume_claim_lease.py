"""Add claimed_by and claimed_at columns for resume concurrency control.

Revision ID: 0016_resume_claim_lease
Revises: 0015_label_acquisition_safety
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_resume_claim_lease"
down_revision: Union[str, Sequence[str], None] = "0015_label_acquisition_safety"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set[str]:
    rows = bind.exec_driver_sql(f"PRAGMA table_info('{table}')")
    return {row[1] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "shipping_label_operations")
    if "claimed_by" not in cols:
        op.add_column(
            "shipping_label_operations",
            sa.Column("claimed_by", sa.String(), nullable=False, server_default=""),
        )
    if "claimed_at" not in cols:
        op.add_column(
            "shipping_label_operations",
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "shipping_label_operations")
    if "claimed_at" in cols:
        op.drop_column("shipping_label_operations", "claimed_at")
    if "claimed_by" in cols:
        op.drop_column("shipping_label_operations", "claimed_by")
