"""Persistent content history: stores full content versions as JSON files.

Organized as: {data_dir}/history/{user_id}/{item_id}.json

Each file contains a list of versions, each with timestamp, content_hash,
title, summary, and url. Never deleted — permanent record.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta

from models import Item

_BEIJING_TZ = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


class ContentHistory:
    """Manages permanent content version history on disk.

    File structure:
        {data_dir}/history/{user_id}/{item_id}.json

    Each JSON file is a dict with:
        - item_id, content_type, url
        - versions: list of {timestamp, content_hash, title, summary}
    """

    def __init__(self, data_dir: str) -> None:
        self._history_dir = os.path.join(data_dir, "history")
        os.makedirs(self._history_dir, exist_ok=True)

    def _item_path(self, uid: str, item_id: str) -> str:
        """Get the file path for an item's history."""
        user_dir = os.path.join(self._history_dir, uid)
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, f"{item_id}.json")

    def _load(self, uid: str, item_id: str) -> dict | None:
        """Load existing history record for an item."""
        path = self._item_path(uid, item_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load history %s: %s", path, e)
            return None

    def _save(self, uid: str, item_id: str, data: dict) -> None:
        """Save history record for an item."""
        path = self._item_path(uid, item_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("Failed to save history %s: %s", path, e)

    def record(self, uid: str, item: Item) -> bool:
        """Record a content version. Returns True if content changed.

        Args:
            uid: Zhihu user_id.
            item: The content item to record.

        Returns:
            True if this is a new version (content changed or first time).
            False if the content hash matches the latest version.
        """
        existing = self._load(uid, item.id)
        now = datetime.now(_BEIJING_TZ).isoformat()

        version_entry = {
            "timestamp": now,
            "content_hash": item.content_hash,
            "title": item.title,
            "summary": item.summary,
        }

        if existing is None:
            # First time seeing this item
            data = {
                "item_id": item.id,
                "content_type": item.content_type.value,
                "url": item.url,
                "first_seen": now,
                "versions": [version_entry],
            }
            self._save(uid, item.id, data)
            logger.debug("New history record: %s/%s", uid, item.id)
            return True

        # Check if content actually changed
        versions = existing.get("versions", [])
        if versions:
            latest = versions[-1]
            if latest.get("content_hash") == item.content_hash:
                # No change
                return False

        # Content changed — append new version
        versions.append(version_entry)
        existing["versions"] = versions
        existing["url"] = item.url  # URL may change
        self._save(uid, item.id, existing)

        version_count = len(versions)
        logger.info(
            "Content updated: %s/%s (version %d)",
            uid, item.id, version_count,
        )
        return True

    def get_versions(self, uid: str, item_id: str) -> list[dict]:
        """Get all recorded versions for an item.

        Returns:
            List of version dicts, or empty list if no history.
        """
        existing = self._load(uid, item_id)
        if existing is None:
            return []
        return existing.get("versions", [])

    def get_version_count(self, uid: str, item_id: str) -> int:
        """Get the number of recorded versions for an item."""
        return len(self.get_versions(uid, item_id))

    def record_batch(
        self, uid: str, items: list[Item]
    ) -> tuple[list[Item], list[Item]]:
        """Record a batch of items and return new/updated lists.

        This is the primary API for the pipeline. For each item:
        - If first seen → new
        - If content_hash changed → updated
        - If unchanged → skip

        Args:
            uid: Zhihu user_id.
            items: All fetched items.

        Returns:
            (new_items, updated_items)
        """
        new_items = []
        updated_items = []

        for item in items:
            existing = self._load(uid, item.id)

            if existing is None:
                # Brand new item
                self.record(uid, item)
                new_items.append(item)
            else:
                # Existing item — check for changes
                versions = existing.get("versions", [])
                if versions:
                    latest_hash = versions[-1].get("content_hash", "")
                    if item.content_hash and item.content_hash != latest_hash:
                        # Content changed
                        self.record(uid, item)
                        updated_items.append(item)
                    # else: unchanged, skip

        return new_items, updated_items
