"""Repair the resolution evidence foreign key on SQLite databases.

Revision ID: 0019_repair_resolution_evidence_fk
Revises: 0018_resume_fencing_and_evidence_link
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0019_repair_resolution_evidence_fk"
down_revision: Union[str, Sequence[str], None] = (
    "0018_resume_fencing_and_evidence_link"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FOREIGN_KEY_NAME = "fk_label_operations_resolution_evidence"


def _has_evidence_foreign_key(bind) -> bool:
    rows = bind.exec_driver_sql(
        "PRAGMA foreign_key_list('shipping_label_operations')"
    )
    return any(
        row[2] == "shipping_label_investigations"
        and row[3] == "resolution_evidence_id"
        and row[4] == "id"
        and row[6].upper() == "SET NULL"
        for row in rows
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _has_evidence_foreign_key(bind):
        return

    with op.batch_alter_table(
        "shipping_label_operations", recreate="always"
    ) as batch_op:
        batch_op.create_foreign_key(
            FOREIGN_KEY_NAME,
            "shipping_label_investigations",
            ["resolution_evidence_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_evidence_foreign_key(bind):
        return

    with op.batch_alter_table(
        "shipping_label_operations", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint(FOREIGN_KEY_NAME, type_="foreignkey")
