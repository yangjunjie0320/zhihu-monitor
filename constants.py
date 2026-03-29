"""Enums for content types and notification types."""

from enum import Enum


class ContentType(str, Enum):
    """Type of Zhihu content."""

    ANSWER = "answer"
    PIN = "pin"
    ARTICLE = "article"


class NotificationType(str, Enum):
    """Type of notification to send."""

    NEW_CONTENT = "new_content"
    SILENCE = "silence"
    ERROR = "error"
    COOKIE_EXPIRY = "cookie_expiry"
    DEBUG = "debug"
