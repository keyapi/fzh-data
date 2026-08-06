"""Add reliable Sellfox tracking writeback outbox tables.

Revision ID: 0020_sellfox_writeback_outbox
Revises: 0019_repair_resolution_evidence_fk
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0020_sellfox_writeback_outbox"
down_revision: Union[str, Sequence[str], None] = "0019_repair_resolution_evidence_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    def require_columns(table: str, required: set[str]) -> None:
        inspector = inspect(op.get_bind())
        present = {column["name"] for column in inspector.get_columns(table)}
        missing = required - present
        if missing:
            raise RuntimeError(
                f"{table} already exists but is missing columns: {sorted(missing)}"
            )
    if "shipping_sellfox_writeback_policies" not in existing:
        op.create_table(
        "shipping_sellfox_writeback_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="DISABLED"),
        sa.Column(
            "capability_status",
            sa.String(),
            nullable=False,
            server_default="UNVERIFIED",
        ),
        sa.Column("evidence_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("approved_by", sa.String(), nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.ForeignKeyConstraint(["account_id"], ["shipping_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", name="uq_sellfox_writeback_policy_account"),
        sa.CheckConstraint(
            "mode IN ('DISABLED', 'PROBE_ONLY', 'SCOPED_BATCH')",
            name="ck_sellfox_writeback_policy_mode",
        ),
        sa.CheckConstraint(
            "capability_status IN ('UNVERIFIED', 'SAFE_TRACKNO_ONLY', "
            "'UNSAFE_PLATFORM_SIDE_EFFECT', 'INEFFECTIVE')",
            name="ck_sellfox_writeback_policy_capability",
        ),
        sa.CheckConstraint(
            "mode <> 'SCOPED_BATCH' OR capability_status = 'SAFE_TRACKNO_ONLY'",
            name="ck_sellfox_writeback_policy_scope_gate",
        ),
        )
    else:
        require_columns(
            "shipping_sellfox_writeback_policies",
            {
                "id", "account_id", "mode", "capability_status", "evidence_ref",
                "approved_by", "approved_at", "created_at", "updated_at",
            },
        )
    if "shipping_sellfox_outbox" not in existing:
        op.create_table(
        "shipping_sellfox_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("tracking_number", sa.String(), nullable=False),
        sa.Column("candidate_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="AWAITING_CONFIRMATION"),
        sa.Column("submission_intent_id", sa.Integer(), nullable=True),
        sa.Column("request_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(), nullable=False, server_default=""),
        sa.Column("lease_token", sa.String(), nullable=False, server_default=""),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.String(), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_class", sa.String(), nullable=False, server_default=""),
        sa.Column("last_error_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("conflicts_with_outbox_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.ForeignKeyConstraint(["account_id"], ["shipping_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["package_id"], ["shipping_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["shipping_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_intent_id"], ["shipping_submission_intents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conflicts_with_outbox_id"], ["shipping_sellfox_outbox.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("candidate_key", name="uq_sellfox_outbox_candidate_key"),
        sa.UniqueConstraint("account_id", "package_id", "order_id", "generation", name="uq_sellfox_outbox_generation"),
        sa.CheckConstraint(
            "status IN ('AWAITING_CONFIRMATION', 'PENDING', 'LEASED', "
            "'IN_FLIGHT', 'VERIFY_PENDING', 'VERIFIED', 'RETRYABLE', "
            "'MANUAL_REVIEW', 'UNKNOWN_BLOCKED', 'CONFLICT', 'FAILED_FINAL', 'SUPERSEDED')",
            name="ck_sellfox_outbox_status",
        ),
        sa.CheckConstraint(
            "generation > 0", name="ck_sellfox_outbox_generation_positive"
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_sellfox_outbox_attempt_nonnegative"
        ),
        sa.CheckConstraint(
            "trim(tracking_number) <> ''", name="ck_sellfox_outbox_tracking_nonempty"
        ),
        sa.CheckConstraint(
            "length(candidate_key) = 64", name="ck_sellfox_outbox_candidate_key_sha256"
        ),
        )
    else:
        require_columns(
            "shipping_sellfox_outbox",
            {
                "id", "account_id", "package_id", "order_id", "generation",
                "tracking_number", "candidate_key", "status", "submission_intent_id",
                "request_hash", "attempt_count", "next_attempt_at", "lease_owner",
                "lease_token", "lease_expires_at", "confirmed_by", "confirmed_at",
                "last_error_class", "last_error_summary", "conflicts_with_outbox_id",
                "created_at", "updated_at",
            },
        )
    outbox_indexes = {
        row[1]
        for row in op.get_bind().exec_driver_sql(
            "PRAGMA index_list('shipping_sellfox_outbox')"
        )
    }
    if "ix_sellfox_outbox_status_next" not in outbox_indexes:
        op.create_index("ix_sellfox_outbox_status_next", "shipping_sellfox_outbox", ["status", "next_attempt_at"])
    if "shipping_sellfox_outbox_sources" not in existing:
        op.create_table(
        "shipping_sellfox_outbox_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("outbox_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.ForeignKeyConstraint(["outbox_id"], ["shipping_sellfox_outbox.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("outbox_id", "source_type", "source_id", name="uq_sellfox_outbox_source"),
        )
    else:
        require_columns(
            "shipping_sellfox_outbox_sources",
            {"id", "outbox_id", "source_type", "source_id", "created_at"},
        )


def downgrade() -> None:
    op.drop_table("shipping_sellfox_outbox_sources")
    op.drop_index("ix_sellfox_outbox_status_next", table_name="shipping_sellfox_outbox")
    op.drop_table("shipping_sellfox_outbox")
    op.drop_table("shipping_sellfox_writeback_policies")
