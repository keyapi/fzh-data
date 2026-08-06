"""Add derived_reference_no to shipping_labels for Lizard suffixed reference.

Revision ID: 0022_derived_reference_no
Revises: 0021_sellfox_outbox_lease_origin
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_derived_reference_no"
down_revision: Union[str, Sequence[str], None] = "0021_sellfox_outbox_lease_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set[str]:
    rows = bind.exec_driver_sql(f"PRAGMA table_info('{table}')")
    return {row[1] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "shipping_labels")
    if "derived_reference_no" not in cols:
        op.add_column(
            "shipping_labels",
            sa.Column("derived_reference_no", sa.String(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind, "shipping_labels")
    if "derived_reference_no" in cols:
        op.drop_column("shipping_labels", "derived_reference_no")
