"""Feishu webhook notifications: card builder + HTTP POST."""

from __future__ import annotations

import logging

import httpx

from constants import ContentType
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


def _content_type_emoji(ct: ContentType) -> str:
    """Emoji for content type."""
    emojis = {
        ContentType.ANSWER: "💬",
        ContentType.PIN: "💡",
        ContentType.ARTICLE: "📝",
    }
    return emojis.get(ct, "📄")


def _build_new_content_card(
    items: list[Item],
    screenshots: dict[str, str],
    user_name: str = "",
) -> dict:
    """Build a Feishu card: summary counts first, then items grouped by type.

    Layout:
        Header: 📢 知乎新内容 (N条) — 用户名
        Summary: 💬 3条回答 | 💡 2条想法 | 📝 1条文章
        ---
        [回答] section with items
        ---
        [想法] section with items
        ...
    """
    elements = []

    # Group items by content type
    grouped: dict[ContentType, list[Item]] = {}
    for item in items:
        grouped.setdefault(item.content_type, []).append(item)

    # Summary line: counts per type
    type_order = [ContentType.ANSWER, ContentType.PIN, ContentType.ARTICLE]
    summary_parts = []
    for ct in type_order:
        group = grouped.get(ct, [])
        if group:
            summary_parts.append(
                f"{_content_type_emoji(ct)} {len(group)}条{_content_type_label(ct)}"
            )

    if summary_parts:
        elements.append({
            "tag": "markdown",
            "content": " | ".join(summary_parts),
        })
        elements.append({"tag": "hr"})

    # Items grouped by type
    for ct in type_order:
        group = grouped.get(ct, [])
        if not group:
            continue

        for item in group:
            time_str = item.created_time.strftime("%m-%d %H:%M")
            image_tag = " 📷" if item.has_images else ""

            elements.append({
                "tag": "markdown",
                "content": (
                    f"**[{_content_type_label(ct)}]** "
                    f"[{item.title}]({item.url}){image_tag}\n"
                    f"{item.summary}\n"
                    f"🕐 {time_str}"
                ),
            })

            screenshot_url = screenshots.get(item.id)
            if screenshot_url:
                elements.append({
                    "tag": "img",
                    "img_key": screenshot_url,
                    "alt": {"tag": "plain_text", "content": "截图"},
                })

        elements.append({"tag": "hr"})

    # Remove trailing hr
    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    name_suffix = f" — {user_name}" if user_name else ""
    return {
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


def _build_updated_content_card(
    items: list[Item],
    user_name: str = "",
) -> dict:
    """Build a Feishu card for modified content."""
    elements = []

    # Summary
    grouped: dict[ContentType, list[Item]] = {}
    for item in items:
        grouped.setdefault(item.content_type, []).append(item)

    type_order = [ContentType.ANSWER, ContentType.PIN, ContentType.ARTICLE]
    summary_parts = []
    for ct in type_order:
        group = grouped.get(ct, [])
        if group:
            summary_parts.append(
                f"{_content_type_emoji(ct)} {len(group)}条{_content_type_label(ct)}"
            )
    if summary_parts:
        elements.append({
            "tag": "markdown",
            "content": " | ".join(summary_parts),
        })
        elements.append({"tag": "hr"})

    for item in items:
        time_str = item.created_time.strftime("%m-%d %H:%M")
        elements.append({
            "tag": "markdown",
            "content": (
                f"**[{_content_type_label(item.content_type)}]** "
                f"[{item.title}]({item.url})\n"
                f"{item.summary}\n"
                f"🕐 创建于 {time_str}"
            ),
        })
        elements.append({"tag": "hr"})

    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    name_suffix = f" — {user_name}" if user_name else ""
    return {
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


def _build_heartbeat_card(uid: str, user_name: str = "") -> dict:
    """Build a heartbeat card confirming the service is running."""
    display = user_name or uid
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "💚 监控服务正常运行",
                },
                "template": "green",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"用户 **{display}** 的监控服务运行正常。\n"
                        f"过去 72 小时内未检测到新内容或变更。"
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
                    "content": f"用户 **{uid}** 出现以下错误:\n\n{error_text}",
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
    """Send a new content notification."""
    if not items:
        return
    card = _build_new_content_card(items, screenshots or {}, user_name)
    await send_webhook(webhook_url, card)


async def send_updated_content(
    webhook_url: str,
    items: list[Item],
    user_name: str = "",
) -> None:
    """Send an updated content notification."""
    if not items:
        return
    card = _build_updated_content_card(items, user_name)
    await send_webhook(webhook_url, card)


async def send_heartbeat(
    webhook_url: str, uid: str, user_name: str = ""
) -> None:
    """Send a heartbeat confirming service is alive."""
    card = _build_heartbeat_card(uid, user_name)
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
