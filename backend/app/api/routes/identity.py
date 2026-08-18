"""
Identity API — user profile and summary endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_chroma_client
from app.core.vectordb.client import collection_for_category
from app.models.schemas import EntityCategory, UserProfile

router = APIRouter(prefix="/api/identity", tags=["Identity"])


@router.get("/{user_id}", response_model=UserProfile)
async def get_identity(user_id: str):
    """
    Get a user's profile summary including top skills and entity counts.
    """
    chroma = get_chroma_client()
    total = 0
    top_skills: list[str] = []
    # Seed every category at 0 so the response shape is stable and the
    # dashboard can render a real "0" instead of a blank card.
    category_counts: dict[str, int] = {c.value: 0 for c in EntityCategory}

    for category in EntityCategory:
        # collection_for_category is the single source of truth for names —
        # deriving them inline is what stranded academics in "academicss".
        col_name = collection_for_category(category)
        try:
            result = chroma.get_all(
                collection_name=col_name,
                where={"user_id": user_id},
                limit=500,
            )
            if result and result.get("ids"):
                count = len(result["ids"])
                total += count
                category_counts[category.value] = count

                # Extract skill names
                if category is EntityCategory.SKILL and result.get("metadatas"):
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
        category_counts=category_counts,
    )
