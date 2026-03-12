"""Add Stripe customer fields to users table.

Revision ID: 004
Revises: 003
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("default_payment_method_id", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "default_payment_method_id")
    op.drop_column("users", "stripe_customer_id")
