"""Add shipping_batches / shipping_batch_packages for lizard export/import workflow.

Revision ID: 0005_shipping_batches
Revises: 0004_artifacts
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_shipping_batches"
down_revision: Union[str, Sequence[str], None] = "0004_artifacts"
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
    if "shipping_batches" not in tables:
        op.create_table(
            "shipping_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "account_id",
                sa.Integer(),
                sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("adapter", sa.String(), nullable=False, server_default="lizard"),
            sa.Column("status", sa.String(), nullable=False, server_default="exported"),
            sa.Column("template_version", sa.String(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(), nullable=False, server_default=""),
            sa.Column("export_artifact_id", sa.Integer(), nullable=True),
            sa.Column("import_artifact_id", sa.Integer(), nullable=True),
            sa.Column("input_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unmatched_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
    if "shipping_batch_packages" not in tables:
        op.create_table(
            "shipping_batch_packages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "batch_id",
                sa.Integer(),
                sa.ForeignKey("shipping_batches.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("package_sn", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="exported"),
            sa.Column("reason", sa.String(), nullable=False, server_default=""),
            sa.UniqueConstraint(
                "batch_id",
                "package_sn",
                name="uq_shipping_batch_package",
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
    if "shipping_batch_packages" in tables:
        op.drop_table("shipping_batch_packages")
    if "shipping_batches" in tables:
        op.drop_table("shipping_batches")
