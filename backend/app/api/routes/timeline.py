"""
Timeline API — chronological journey endpoint.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import get_timeline_builder
from app.models.schemas import TimelineResponse

router = APIRouter(prefix="/api/timeline", tags=["Timeline"])


@router.get("/{user_id}", response_model=TimelineResponse)
async def get_timeline(
    user_id: str,
    year: Optional[str] = Query(None, description="Filter by year, e.g. 2023"),
    category: Optional[str] = Query(
        None,
        description="Filter by category: skill, project, certification, internship, achievement",
    ),
):
    """
    Get the full chronological journey timeline for a user.

    Supports optional filters:
    - `?year=2023` — show only milestones from that year
    - `?category=projects` — show only a specific entity type
    """
    builder = get_timeline_builder()
    return builder.build(user_id=user_id, year=year, category=category)
