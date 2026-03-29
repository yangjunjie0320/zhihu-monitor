"""Archive service: save article JSON and age-based cleanup."""

import json
import logging
import os
import time
from datetime import datetime

from models import Item

logger = logging.getLogger(__name__)


class ArchiveService:
    """Saves raw API response JSON and performs age-based cleanup."""

    def __init__(self, data_dir: str) -> None:
        """Initialize archive service.

        Args:
            data_dir: Base data directory. Archives go to {data_dir}/archive/.
        """
        self._archive_dir = os.path.join(data_dir, "archive")
        os.makedirs(self._archive_dir, exist_ok=True)

    def save(self, item: Item, raw_json: dict) -> str:
        """Save raw JSON for an item to the archive.

        Args:
            item: The parsed Item.
            raw_json: The raw API response dict for this item.

        Returns:
            Path to the saved JSON file.
        """
        # Organize by date/content_type
        date_str = item.created_time.strftime("%Y-%m-%d")
        type_dir = os.path.join(
            self._archive_dir, date_str, item.content_type.value
        )
        os.makedirs(type_dir, exist_ok=True)

        filename = f"{item.id}.json"
        filepath = os.path.join(type_dir, filename)

        archive_data = {
            "item_id": item.id,
            "content_type": item.content_type.value,
            "title": item.title,
            "url": item.url,
            "archived_at": datetime.now().isoformat(),
            "raw": raw_json,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)

        logger.debug("Archived %s to %s", item.id, filepath)
        return filepath

    def cleanup(self, max_age_days: int) -> int:
        """Remove archived files older than max_age_days.

        Args:
            max_age_days: Maximum age in days for archived files.

        Returns:
            Number of files removed.
        """
        if not os.path.exists(self._archive_dir):
            return 0

        cutoff = time.time() - (max_age_days * 86400)
        removed = 0

        for root, dirs, files in os.walk(self._archive_dir, topdown=False):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    if os.path.getmtime(filepath) < cutoff:
                        os.remove(filepath)
                        removed += 1
                except OSError as e:
                    logger.warning("Failed to remove %s: %s", filepath, e)

            # Remove empty directories
            for dirname in dirs:
                dirpath = os.path.join(root, dirname)
                try:
                    if not os.listdir(dirpath):
                        os.rmdir(dirpath)
                except OSError:
                    pass

        if removed:
            logger.info(
                "Archive cleanup: removed %d files older than %d days",
                removed, max_age_days,
            )
        return removed
