"""Add shipping_carton_overrides for manual dims补录.

Revision ID: 0003_carton_overrides
Revises: 0002_local_review_status
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_carton_overrides"
down_revision: Union[str, Sequence[str], None] = "0002_local_review_status"
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
    if "shipping_carton_overrides" in tables:
        return
    op.create_table(
        "shipping_carton_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commodity_sku", sa.String(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("length_cm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("width_cm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("height_cm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "account_id",
            "commodity_sku",
            name="uq_shipping_carton_override_account_sku",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "shipping_carton_overrides" in tables:
        op.drop_table("shipping_carton_overrides")
