"""Add address_type column to shipping_package_rates.

Revision ID: 0012_package_rates_address_type
Revises: 0011_package_rates_raw
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_package_rates_address_type"
down_revision: Union[str, Sequence[str], None] = "0011_package_rates_raw"
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
    if "address_type" not in columns:
        op.add_column("shipping_package_rates", sa.Column("address_type", sa.String, default=""))


def downgrade() -> None:
    pass
