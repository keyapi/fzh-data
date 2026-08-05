"""Add investigation/evidence table for UNKNOWN_BLOCKED resolution.

Revision ID: 0017_shipping_label_investigations
Revises: 0016_resume_claim_lease
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_shipping_label_investigations"
down_revision: Union[str, Sequence[str], None] = "0016_resume_claim_lease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set[str]:
    rows = bind.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    return {row[0] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "shipping_label_investigations" not in tables:
        op.create_table(
            "shipping_label_investigations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "operation_id",
                sa.Integer(),
                sa.ForeignKey("shipping_label_operations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "evidence_type",
                sa.String(),
                nullable=False,
            ),
            sa.Column("external_ref", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "private_artifact_id",
                sa.Integer(),
                sa.ForeignKey("shipping_artifacts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("actor", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
        )
        op.create_index(
            "ix_investigations_operation_id",
            "shipping_label_investigations",
            ["operation_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "shipping_label_investigations" in tables:
        op.drop_table("shipping_label_investigations")
