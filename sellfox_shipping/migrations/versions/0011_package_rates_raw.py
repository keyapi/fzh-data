"""Add raw_data column to shipping_package_rates.

Revision ID: 0011_package_rates_raw
Revises: 0010_package_rates
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_package_rates_raw"
down_revision: Union[str, Sequence[str], None] = "0010_package_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        row[1]
        for row in bind.exec_driver_sql(
            "PRAGMA table_info(shipping_package_rates)"
        )
    }
    if "raw_data" not in columns:
        op.add_column("shipping_package_rates", sa.Column("raw_data", sa.Text, nullable=True))


def downgrade() -> None:
    # SQLite does not support DROP COLUMN in older versions; skip.
    pass
