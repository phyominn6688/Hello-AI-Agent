"""Alter itinerary_items.wallet_pass_url from TEXT to JSONB.

Stores as {"apple": "...", "google": "..."} to support both wallet providers.

Revision ID: 005
Revises: 004
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cast existing TEXT values to JSONB (NULL values pass through; existing string
    # URLs are wrapped as plain strings — the worker will overwrite with proper JSON)
    op.execute(
        "ALTER TABLE itinerary_items "
        "ALTER COLUMN wallet_pass_url TYPE JSONB "
        "USING CASE WHEN wallet_pass_url IS NULL THEN NULL "
        "ELSE to_jsonb(wallet_pass_url) END"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE itinerary_items "
        "ALTER COLUMN wallet_pass_url TYPE TEXT "
        "USING wallet_pass_url::text"
    )
