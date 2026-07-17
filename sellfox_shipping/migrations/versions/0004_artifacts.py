"""Add shipping_artifacts for export/import file registry (content_hash dedup).

Revision ID: 0004_artifacts
Revises: 0003_carton_overrides
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_artifacts"
down_revision: Union[str, Sequence[str], None] = "0003_carton_overrides"
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
    if "shipping_artifacts" in tables:
        return
    op.create_table(
        "shipping_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("storage_relpath", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False, server_default=""),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("template_version", sa.String(), nullable=False, server_default=""),
        sa.Column("virtual_folder", sa.String(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_shipping_artifacts_account_hash",
        "shipping_artifacts",
        ["account_id", "content_hash"],
    )
    op.create_index(
        "ix_shipping_artifacts_account_kind",
        "shipping_artifacts",
        ["account_id", "kind"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "shipping_artifacts" in tables:
        op.drop_table("shipping_artifacts")
