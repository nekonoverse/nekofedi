"""Add app_config key/value table

Revision ID: 006
Revises: 005
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_config",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", sa.String),
    )


def downgrade():
    op.drop_table("app_config")
