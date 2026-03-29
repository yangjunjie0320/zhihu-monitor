"""Frozen dataclass models for monitor targets and content items."""

from dataclasses import dataclass
from datetime import datetime

from constants import ContentType


@dataclass(frozen=True)
class MonitorTarget:
    """A Zhihu user to monitor with their notification webhook."""

    user_id: str
    webhook_url: str


@dataclass(frozen=True)
class Item:
    """A piece of Zhihu content (answer or pin)."""

    id: str
    content_type: ContentType
    title: str
    url: str
    summary: str
    created_time: datetime
    has_images: bool = False
