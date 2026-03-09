"""Add GPS location fields to users table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("current_lat", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("current_lng", sa.Float(), nullable=True))
    op.add_column(
        "users",
        sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "location_updated_at")
    op.drop_column("users", "current_lng")
    op.drop_column("users", "current_lat")
