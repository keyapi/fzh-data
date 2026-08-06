"""Fence resume leases and link UNKNOWN_BLOCKED resolutions to evidence.

Revision ID: 0018_resume_fencing_and_evidence_link
Revises: 0017_shipping_label_investigations
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_resume_fencing_and_evidence_link"
down_revision: Union[str, Sequence[str], None] = "0017_shipping_label_investigations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set[str]:
    rows = bind.exec_driver_sql(f"PRAGMA table_info('{table}')")
    return {row[1] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    operation_cols = _columns(bind, "shipping_label_operations")
    if "claim_token" not in operation_cols:
        op.add_column(
            "shipping_label_operations",
            sa.Column("claim_token", sa.String(), nullable=False, server_default=""),
        )
    if "resolution_evidence_id" not in operation_cols:
        op.add_column(
            "shipping_label_operations",
            sa.Column("resolution_evidence_id", sa.Integer(), nullable=True),
        )

    investigation_cols = _columns(bind, "shipping_label_investigations")
    if "conclusion" not in investigation_cols:
        op.add_column(
            "shipping_label_investigations",
            sa.Column("conclusion", sa.String(), nullable=False, server_default=""),
        )
    if "provider_order_id" not in investigation_cols:
        op.add_column(
            "shipping_label_investigations",
            sa.Column("provider_order_id", sa.String(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    investigation_cols = _columns(bind, "shipping_label_investigations")
    if "provider_order_id" in investigation_cols:
        op.drop_column("shipping_label_investigations", "provider_order_id")
    if "conclusion" in investigation_cols:
        op.drop_column("shipping_label_investigations", "conclusion")

    operation_cols = _columns(bind, "shipping_label_operations")
    if "resolution_evidence_id" in operation_cols:
        op.drop_column("shipping_label_operations", "resolution_evidence_id")
    if "claim_token" in operation_cols:
        op.drop_column("shipping_label_operations", "claim_token")
