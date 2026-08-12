"""Add tongtool mark columns to shipping_packages.

Revision ID: 0023_tongtool_mark
Revises: 0022_derived_reference_no
Create Date: 2026-08-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_tongtool_mark"
down_revision: Union[str, Sequence[str], None] = "0022_derived_reference_no"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set[str]:
    rows = bind.exec_driver_sql(f"PRAGMA table_info('{table}')")
    return {row[1] for row in rows}


def _table_exists(bind, table: str) -> bool:
    rows = bind.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchall()
    return bool(rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "shipping_packages"):
        return
    cols = _columns(bind, "shipping_packages")
    if "is_tongtool" not in cols:
        op.add_column(
            "shipping_packages",
            sa.Column("is_tongtool", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "tongtool_p_numbers" not in cols:
        op.add_column(
            "shipping_packages",
            sa.Column("tongtool_p_numbers", sa.String(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "shipping_packages"):
        return
    cols = _columns(bind, "shipping_packages")
    if "tongtool_p_numbers" in cols:
        op.drop_column("shipping_packages", "tongtool_p_numbers")
    if "is_tongtool" in cols:
        op.drop_column("shipping_packages", "is_tongtool")
