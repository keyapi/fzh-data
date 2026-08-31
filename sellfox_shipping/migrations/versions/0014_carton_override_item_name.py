"""Add item_name column to shipping_carton_overrides.

Revision ID: 0014_carton_override_item_name
Revises: 0013_shipping_labels
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_carton_override_item_name"
down_revision: Union[str, Sequence[str], None] = "0013_shipping_labels"
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
    if "shipping_carton_overrides" not in tables:
        return

    columns = {
        row[1]
        for row in bind.exec_driver_sql(
            "PRAGMA table_info('shipping_carton_overrides')"
        )
    }
    if "item_name" not in columns:
        op.add_column(
            "shipping_carton_overrides",
            sa.Column("item_name", sa.String(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "shipping_carton_overrides" not in tables:
        return

    columns = {
        row[1]
        for row in bind.exec_driver_sql(
            "PRAGMA table_info('shipping_carton_overrides')"
        )
    }
    if "item_name" in columns:
        # SQLite doesn't support DROP COLUMN easily; use recreation for dev
        pass
