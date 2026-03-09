"""Add date_of_birth and age_declaration_method to users table.

Revision ID: 001
Revises:
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("date_of_birth", sa.Date(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("age_declaration_method", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "age_declaration_method")
    op.drop_column("users", "date_of_birth")
