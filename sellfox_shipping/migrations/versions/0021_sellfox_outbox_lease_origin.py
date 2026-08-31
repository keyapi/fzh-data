"""Add lease origin status to Sellfox outbox for crash-safe recovery.

Revision ID: 0021_sellfox_outbox_lease_origin
Revises: 0020_sellfox_writeback_outbox
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0021_sellfox_outbox_lease_origin"
down_revision: Union[str, Sequence[str], None] = "0020_sellfox_writeback_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {
        column["name"] for column in inspector.get_columns("shipping_sellfox_outbox")
    }
    if "lease_origin_status" not in columns:
        op.add_column(
            "shipping_sellfox_outbox",
            sa.Column(
                "lease_origin_status",
                sa.String(),
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    op.drop_column("shipping_sellfox_outbox", "lease_origin_status")
