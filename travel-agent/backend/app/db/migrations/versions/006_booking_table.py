"""Create bookings table.

Revision ID: 006
Revises: 005
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("itinerary_items.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(128), nullable=True),
        sa.Column("stripe_charge_id", sa.String(128), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("booking_ref", sa.String(256), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("raw_provider_response", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_trip_id", "bookings", ["trip_id"])
    op.create_index("ix_bookings_item_id", "bookings", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_bookings_item_id", table_name="bookings")
    op.drop_index("ix_bookings_trip_id", table_name="bookings")
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_table("bookings")
