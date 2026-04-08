import logging

from fastapi import APIRouter, HTTPException

from backend.db import db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{item_id}/read")
def mark_read(item_id: str):
    with db() as conn:
        result = conn.execute(
            "UPDATE content_items SET is_read = 1 WHERE id = ?", (item_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@router.post("/{item_id}/unread")
def mark_unread(item_id: str):
    with db() as conn:
        result = conn.execute(
            "UPDATE content_items SET is_read = 0 WHERE id = ?", (item_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@router.post("/{item_id}/dismiss")
def dismiss_item(item_id: str):
    """Dismiss a discovery item (marks as read). Identical effect to /read."""
    with db() as conn:
        result = conn.execute(
            "UPDATE content_items SET is_read = 1 WHERE id = ?", (item_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@router.post("/{item_id}/save")
def save_item(item_id: str):
    with db() as conn:
        result = conn.execute(
            "UPDATE content_items SET is_saved = 1 WHERE id = ?", (item_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@router.post("/{item_id}/unsave")
def unsave_item(item_id: str):
    with db() as conn:
        result = conn.execute(
            "UPDATE content_items SET is_saved = 0 WHERE id = ?", (item_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


@router.post("/{item_id}/promote")
def promote_source(item_id: str):
    """
    Promote a discovery item's source to the whitelist.
    For videos: adds the channel to the channels table.
    For posts: adds the subreddit to subreddits.yaml.
    Also marks the item as read.
    """
    with db() as conn:
        row = conn.execute(
            "SELECT id, type, source_id, source_name FROM content_items WHERE id = ?",
            (item_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    item_type = row["type"]
    source_id = row["source_id"]
    source_name = row["source_name"]

    try:
        if item_type == "video":
            from backend.services.youtube import promote_channel
            promote_channel(source_id, source_name)
        else:
            from backend.services.reddit import promote_subreddit
            promote_subreddit(source_id)
    except Exception as e:
        logger.exception("Failed to promote source %s (%s)", source_id, item_type)
        raise HTTPException(status_code=500, detail=f"Promotion failed: {e}")

    with db() as conn:
        conn.execute(
            "UPDATE content_items SET is_read = 1 WHERE id = ?", (item_id,)
        )

    return {"ok": True, "source_id": source_id, "type": item_type}
