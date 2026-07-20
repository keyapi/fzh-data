"""Add submission scopes / intents / attempts for P1C submitToPlatform safety.

Revision ID: 0006_submission_intents
Revises: 0005_shipping_batches
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_submission_intents"
down_revision: Union[str, Sequence[str], None] = "0005_shipping_batches"
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
    if "shipping_submission_scopes" not in tables:
        op.create_table(
            "shipping_submission_scopes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "account_id",
                sa.Integer(),
                sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "package_id",
                sa.Integer(),
                sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "order_id",
                sa.Integer(),
                sa.ForeignKey("shipping_orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
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
            sa.UniqueConstraint(
                "account_id",
                "package_id",
                "order_id",
                name="uq_shipping_submission_scope",
            ),
        )
    if "shipping_submission_intents" not in tables:
        op.create_table(
            "shipping_submission_intents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "account_id",
                sa.Integer(),
                sa.ForeignKey("shipping_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "package_id",
                sa.Integer(),
                sa.ForeignKey("shipping_packages.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "order_id",
                sa.Integer(),
                sa.ForeignKey("shipping_orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "scope_id",
                sa.Integer(),
                sa.ForeignKey("shipping_submission_scopes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("external_order_id", sa.String(), nullable=False, server_default=""),
            sa.Column("request_hash", sa.String(), nullable=False),
            sa.Column("canonical_request", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="READY"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("confirmed_by", sa.String(), nullable=False, server_default=""),
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
            sa.UniqueConstraint("request_hash", name="uq_shipping_submission_intent_hash"),
        )
    if "shipping_submission_attempts" not in tables:
        op.create_table(
            "shipping_submission_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "intent_id",
                sa.Integer(),
                sa.ForeignKey("shipping_submission_intents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="CREATED"),
            sa.Column("send_state", sa.String(), nullable=False, server_default="NOT_SENT"),
            sa.Column("actor", sa.String(), nullable=False, server_default=""),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("http_summary", sa.Text(), nullable=False, server_default=""),
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
            sa.UniqueConstraint(
                "intent_id",
                "attempt_no",
                name="uq_shipping_submission_attempt_no",
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
    if "shipping_submission_attempts" in tables:
        op.drop_table("shipping_submission_attempts")
    if "shipping_submission_intents" in tables:
        op.drop_table("shipping_submission_intents")
    if "shipping_submission_scopes" in tables:
        op.drop_table("shipping_submission_scopes")
