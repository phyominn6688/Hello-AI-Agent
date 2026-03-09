"""Location endpoint — accepts user GPS coordinates during active trips."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user
from app.db.database import get_db
from app.deps import write_limiter
from app.models.trip import Trip
from app.models.user import User

router = APIRouter()


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.post(
    "/trips/{trip_id}/location",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_limiter)],
)
async def update_location(
    trip_id: int,
    body: LocationUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's current GPS coordinates.

    Only accepted when the trip is active — ignored otherwise to avoid
    stale coordinates persisting after a trip ends.
    """
    # Resolve user
    result = await db.execute(select(User).where(User.cognito_sub == current.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify trip ownership and active status
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    user.current_lat = body.lat
    user.current_lng = body.lng
    user.location_updated_at = datetime.now(timezone.utc)
    await db.flush()
