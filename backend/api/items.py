from fastapi import APIRouter, HTTPException

from backend.db import db

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
