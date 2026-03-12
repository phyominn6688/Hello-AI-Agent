"""Expand agent_actions table with booking audit fields.

Revision ID: 003
Revises: 002
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_actions",
        sa.Column("agent_type", sa.String(32), nullable=False, server_default="main"),
    )
    op.add_column(
        "agent_actions",
        sa.Column("tool_name", sa.String(128), nullable=True),
    )
    op.add_column(
        "agent_actions",
        sa.Column("input_snapshot", JSONB, nullable=True),
    )
    op.add_column(
        "agent_actions",
        sa.Column("output_snapshot", JSONB, nullable=True),
    )
    op.add_column(
        "agent_actions",
        sa.Column("status", sa.String(32), nullable=False, server_default="success"),
    )
    op.add_column(
        "agent_actions",
        sa.Column("booking_token_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "agent_actions",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_actions", "duration_ms")
    op.drop_column("agent_actions", "booking_token_hash")
    op.drop_column("agent_actions", "status")
    op.drop_column("agent_actions", "output_snapshot")
    op.drop_column("agent_actions", "input_snapshot")
    op.drop_column("agent_actions", "tool_name")
    op.drop_column("agent_actions", "agent_type")
