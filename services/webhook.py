"""Feishu webhook notifications: card builder + HTTP POST."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from constants import ContentType, NotificationType
from models import Item

logger = logging.getLogger(__name__)


def _content_type_label(ct: ContentType) -> str:
    """Human-readable label for content type."""
    labels = {
        ContentType.ANSWER: "回答",
        ContentType.PIN: "想法",
        ContentType.ARTICLE: "文章",
    }
    return labels.get(ct, "内容")


def _build_new_content_card(
    items: list[Item],
    screenshots: dict[str, str],
    user_name: str = "",
) -> dict:
    """Build a Feishu interactive card for new content items.

    Args:
        items: List of new content items.
        screenshots: Dict mapping item.id to screenshot file URL (if any).
        user_name: Display name of the monitored user.
    """
    elements = []

    for item in items:
        type_label = _content_type_label(item.content_type)
        time_str = item.created_time.strftime("%Y-%m-%d %H:%M")
        image_tag = " 📷" if item.has_images else ""

        # Title + link
        elements.append({
            "tag": "markdown",
            "content": (
                f"**[{type_label}] [{item.title}]({item.url})**"
                f"{image_tag}"
            ),
        })

        # Summary
        if item.summary:
            elements.append({
                "tag": "markdown",
                "content": item.summary,
            })

        # Time
        elements.append({
            "tag": "markdown",
            "content": f"🕐 {time_str}",
        })

        # Screenshot image if available
        screenshot_url = screenshots.get(item.id)
        if screenshot_url:
            elements.append({
                "tag": "img",
                "img_key": screenshot_url,
                "alt": {"tag": "plain_text", "content": "页面截图"},
            })

        # Divider between items
        elements.append({"tag": "hr"})

    # Remove trailing hr
    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    name_suffix = f" — {user_name}" if user_name else ""
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📢 知乎新内容 ({len(items)}条){name_suffix}",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }
    return card


def _build_silence_card(uid: str, hours: int) -> dict:
    """Build a silence reminder card."""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🔇 静默提醒",
                },
                "template": "yellow",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"用户 **{uid}** 已超过 **{hours}小时** 没有新内容。\n"
                        f"最后检查时间: 当前"
                    ),
                },
            ],
        },
    }


def _build_error_card(uid: str, errors: list[str]) -> dict:
    """Build an error report card."""
    error_text = "\n".join(f"• {e}" for e in errors[-10:])
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "⚠️ 监控错误报告",
                },
                "template": "red",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"用户 **{uid}** 出现以下错误:\n\n{error_text}"
                    ),
                },
            ],
        },
    }


def _build_cookie_card(days_left: int) -> dict:
    """Build a cookie expiry reminder card."""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🍪 Cookie 即将过期",
                },
                "template": "orange",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"知乎 Cookie 将在 **{days_left}天** 内过期。\n"
                        f"请及时更新 Cookie 文件以避免监控中断。"
                    ),
                },
            ],
        },
    }


def _build_debug_card(uid: str, info: dict) -> dict:
    """Build a debug info card."""
    info_lines = "\n".join(f"• **{k}**: {v}" for k, v in info.items())
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🐛 调试信息",
                },
                "template": "grey",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"用户: **{uid}**\n\n{info_lines}",
                },
            ],
        },
    }


async def send_webhook(webhook_url: str, payload: dict) -> None:
    """POST a payload to a Feishu webhook.

    Args:
        webhook_url: The Feishu bot webhook URL.
        payload: The card payload dict.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code != 200:
            logger.error(
                "Webhook POST failed: %d — %s",
                resp.status_code, resp.text[:200],
            )
            resp.raise_for_status()

    logger.info("Webhook notification sent successfully")


async def send_new_content(
    webhook_url: str,
    items: list[Item],
    screenshots: dict[str, str] | None = None,
    user_name: str = "",
) -> None:
    """Send a new content notification.

    Args:
        webhook_url: Feishu webhook URL.
        items: New content items.
        screenshots: Optional dict of item_id → screenshot image key.
        user_name: Display name of the monitored user.
    """
    if not items:
        return
    card = _build_new_content_card(items, screenshots or {}, user_name)
    await send_webhook(webhook_url, card)


def _build_updated_content_card(
    items: list[Item],
    user_name: str = "",
) -> dict:
    """Build a Feishu card for content that has been modified.

    Args:
        items: List of updated items.
        user_name: Display name for the user.
    """
    elements = []

    for item in items:
        type_label = _content_type_label(item.content_type)
        time_str = item.created_time.strftime("%Y-%m-%d %H:%M")

        elements.append({
            "tag": "markdown",
            "content": (
                f"**[{type_label}] [{item.title}]({item.url})**"
            ),
        })

        if item.summary:
            elements.append({
                "tag": "markdown",
                "content": item.summary,
            })

        elements.append({
            "tag": "markdown",
            "content": f"🕐 创建于 {time_str}",
        })

        elements.append({"tag": "hr"})

    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    name_suffix = f" — {user_name}" if user_name else ""
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"✏️ 内容更新 ({len(items)}条){name_suffix}",
                },
                "template": "orange",
            },
            "elements": elements,
        },
    }
    return card


async def send_updated_content(
    webhook_url: str,
    items: list[Item],
    user_name: str = "",
) -> None:
    """Send an updated content notification.

    Args:
        webhook_url: Feishu webhook URL.
        items: Updated content items.
        user_name: Display name for the user.
    """
    if not items:
        return
    card = _build_updated_content_card(items, user_name)
    await send_webhook(webhook_url, card)


async def send_silence_reminder(
    webhook_url: str, uid: str, hours: int
) -> None:
    """Send a silence reminder notification."""
    card = _build_silence_card(uid, hours)
    await send_webhook(webhook_url, card)


async def send_error_report(
    webhook_url: str, uid: str, errors: list[str]
) -> None:
    """Send an error report notification."""
    if not errors:
        return
    card = _build_error_card(uid, errors)
    await send_webhook(webhook_url, card)


async def send_cookie_reminder(
    webhook_url: str, days_left: int
) -> None:
    """Send a cookie expiry reminder."""
    card = _build_cookie_card(days_left)
    await send_webhook(webhook_url, card)


async def send_debug(
    webhook_url: str, uid: str, info: dict
) -> None:
    """Send debug info notification."""
    card = _build_debug_card(uid, info)
    await send_webhook(webhook_url, card)
