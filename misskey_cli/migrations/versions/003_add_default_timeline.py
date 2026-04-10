"""Add default_timeline column to settings

Revision ID: 003
Revises: 002
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("settings", sa.Column("default_timeline", sa.String, nullable=False, server_default="home"))


def downgrade():
    op.drop_column("settings", "default_timeline")
