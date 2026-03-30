"""Reset all scoring fields so the score job re-processes everything."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend.db import db
with db() as conn:
    n = conn.execute("UPDATE content_items SET scored_at=NULL, relevance_score=NULL, summary=NULL, is_low_density=NULL").rowcount
print(f"Cleared scores for {n} items.")
