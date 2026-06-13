"""add_is_active_to_users

Revision ID: 2b4c8a1e3f5d
Revises: 9ac72f2643fd
Create Date: 2026-06-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2b4c8a1e3f5d"
down_revision: Union[str, Sequence[str], None] = "9ac72f2643fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
