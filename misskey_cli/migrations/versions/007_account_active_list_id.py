"""Add active_list_id to accounts

Revision ID: 007
Revises: 006
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "accounts",
        sa.Column("active_list_id", sa.String, nullable=True),
    )


def downgrade():
    op.drop_column("accounts", "active_list_id")
