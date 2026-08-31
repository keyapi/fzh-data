"""Add cross-process submit rate gate (SQLite).

Revision ID: 0007_submit_rate_gate
Revises: 0006_submission_intents
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_submit_rate_gate"
down_revision: Union[str, Sequence[str], None] = "0006_submission_intents"
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
    if "shipping_submit_rate_gate" not in tables:
        op.create_table(
            "shipping_submit_rate_gate",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("last_submit_unix", sa.Float(), nullable=False, server_default="0"),
        )
        op.execute(
            sa.text(
                "INSERT INTO shipping_submit_rate_gate (id, last_submit_unix) VALUES (1, 0)"
            )
        )


def downgrade() -> None:
    op.drop_table("shipping_submit_rate_gate")
