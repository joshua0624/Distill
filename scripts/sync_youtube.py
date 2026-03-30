"""
One-time / on-demand: sync your YouTube subscriptions into the DB.
Run this before the first fetch job, and whenever you want to update
the channel list.

Usage:
    uv run python scripts/sync_youtube.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.services.youtube import sync_subscriptions

if __name__ == "__main__":
    channels = sync_subscriptions()
    print(f"Synced {len(channels)} subscriptions.")
