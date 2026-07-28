"""
Identity API — user profile and summary endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_chroma_client
from app.core.vectordb.client import COLLECTIONS
from app.models.schemas import UserProfile

router = APIRouter(prefix="/api/identity", tags=["Identity"])


@router.get("/{user_id}", response_model=UserProfile)
async def get_identity(user_id: str):
    """
    Get a user's profile summary including top skills and entity counts.
    """
    chroma = get_chroma_client()
    total = 0
    top_skills: list[str] = []

    for col_name in COLLECTIONS:
        if col_name == "raw_chunks":
            continue
        try:
            result = chroma.get_all(
                collection_name=col_name,
                where={"user_id": user_id},
                limit=500,
            )
            if result and result.get("ids"):
                count = len(result["ids"])
                total += count

                # Extract skill names
                if col_name == "skills" and result.get("metadatas"):
                    for meta in result["metadatas"]:
                        title = meta.get("title", "")
                        if title:
                            top_skills.append(title)
        except Exception:
            continue

    if total == 0:
        raise HTTPException(status_code=404, detail="No data found for this user")

    return UserProfile(
        user_id=user_id,
        name=user_id,
        summary=f"Professional profile with {total} extracted entities",
        top_skills=top_skills[:15],
        total_entities=total,
    )
