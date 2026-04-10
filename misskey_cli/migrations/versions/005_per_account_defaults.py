"""Move default_visibility and default_timeline to accounts table

Revision ID: 005
Revises: 004
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "accounts",
        sa.Column("default_visibility", sa.String, nullable=False, server_default="public"),
    )
    op.add_column(
        "accounts",
        sa.Column("default_timeline", sa.String, nullable=False, server_default="home"),
    )

    # Copy current global defaults onto every existing account so users keep
    # whatever they had configured before the split.
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT default_visibility, default_timeline FROM settings LIMIT 1")
    ).first()
    if row:
        conn.execute(
            sa.text(
                "UPDATE accounts SET default_visibility = :v, default_timeline = :t"
            ),
            {"v": row[0], "t": row[1]},
        )

    op.drop_table("settings")


def downgrade():
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("default_visibility", sa.String, nullable=False, server_default="public"),
        sa.Column("default_timeline", sa.String, nullable=False, server_default="home"),
    )

    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT default_visibility, default_timeline FROM accounts WHERE active = 1 LIMIT 1"
        )
    ).first()
    if row is None:
        row = conn.execute(
            sa.text(
                "SELECT default_visibility, default_timeline FROM accounts LIMIT 1"
            )
        ).first()
    conn.execute(
        sa.text(
            "INSERT INTO settings (default_visibility, default_timeline) VALUES (:v, :t)"
        ),
        {"v": (row[0] if row else "public"), "t": (row[1] if row else "home")},
    )

    op.drop_column("accounts", "default_timeline")
    op.drop_column("accounts", "default_visibility")
