"""Frozen dataclass models for monitor targets and content items."""

from dataclasses import dataclass
from datetime import datetime

from constants import ContentType


@dataclass(frozen=True)
class MonitorTarget:
    """A Zhihu user to monitor with their notification webhook."""

    user_id: str
    webhook_url: str
    user_name: str = ""

    @property
    def display_name(self) -> str:
        """Human-readable name for logging and notifications."""
        return self.user_name or self.user_id


@dataclass(frozen=True)
class Item:
    """A piece of Zhihu content (answer, pin, or article)."""

    id: str
    content_type: ContentType
    title: str
    url: str
    summary: str
    created_time: datetime
    has_images: bool = False
    content_hash: str = ""  # MD5 of content for diff detection
