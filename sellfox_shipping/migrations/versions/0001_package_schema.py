"""Initial package-centric schema.

Revision ID: 0001_package_schema
Revises:
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001_package_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sellfox_shipping.package_repository import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from sellfox_shipping.package_repository import Base

    Base.metadata.drop_all(bind=op.get_bind())
