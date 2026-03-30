"""Feishu webhook notifications: card builder + HTTP POST."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta

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


def _build_new_content_card(
    items: list[Item],
    screenshots: dict[str, str],
    user_name: str = "",
) -> dict:
    """Build a Feishu card: summary counts first, then items grouped by type.

    Layout:
        Header: [NEW] 知乎新内容 (N条) -- 用户名
        Summary: 3条回答 | 2条想法 | 1条文章
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
                f"{len(group)}条{_content_type_label(ct)}"
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
            image_tag = " [IMG]" if item.has_images else ""

            elements.append({
                "tag": "markdown",
                "content": (
                    f"**[{_content_type_label(ct)}]** "
                    f"[{item.title}]({item.url}){image_tag}\n"
                    f"{item.summary}\n"
                    f"{time_str}"
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

    name_suffix = f" -- {user_name}" if user_name else ""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"[NEW] 知乎新内容 ({len(items)}条){name_suffix}",
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
                f"{len(group)}条{_content_type_label(ct)}"
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
                f"创建于 {time_str}"
            ),
        })
        elements.append({"tag": "hr"})

    if elements and elements[-1].get("tag") == "hr":
        elements.pop()

    name_suffix = f" -- {user_name}" if user_name else ""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"[UPDATE] 内容更新 ({len(items)}条){name_suffix}",
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
                    "content": "[OK] 监控服务正常运行",
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
    error_text = "\n".join(f"- {e}" for e in errors[-10:])
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "[ERROR] 监控错误报告",
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
    if days_left <= 0:
        title = "[COOKIE] Cookie 已过期"
        template = "red"
        content = (
            "知乎 Cookie 已过期，监控可能无法正常获取数据。\n"
            "请立即更新 Cookie 文件。"
        )
    else:
        title = "[COOKIE] Cookie 即将过期"
        template = "orange"
        content = (
            f"知乎 Cookie 将在 **{days_left}天** 内过期。\n"
            f"请及时更新 Cookie 文件以避免监控中断。"
        )
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": template,
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                },
            ],
        },
    }


def _build_debug_card(uid: str, info: dict) -> dict:
    """Build a debug info card."""
    info_lines = "\n".join(f"- **{k}**: {v}" for k, v in info.items())
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "[DEBUG] 调试信息",
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


# Module-level data directory, set via init_webhook_dir()
_data_dir: str = "/app/data"


def init_webhook_dir(data_dir: str) -> None:
    """Set the base data directory for saving sent payloads."""
    global _data_dir
    _data_dir = data_dir


def _save_payload(payload: dict, header_title: str) -> str:
    """Save webhook payload to data/sent/{date}/{timestamp}_{slug}.json.

    Returns:
        Absolute path to the saved file.
    """
    beijing = timezone(timedelta(hours=8))
    now = datetime.now(beijing)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    # Create a filesystem-safe slug from the header title
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "_", header_title)[:60].strip("_")
    if not slug:
        slug = "webhook"

    sent_dir = os.path.join(_data_dir, "sent", date_str)
    os.makedirs(sent_dir, exist_ok=True)

    filename = f"{time_str}_{slug}.json"
    filepath = os.path.join(sent_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filepath


async def send_webhook(webhook_url: str, payload: dict) -> None:
    """Save payload to disk, then POST it to a Feishu webhook.

    The payload is first written to data/sent/ as a permanent record,
    then read back from disk and sent via HTTP POST.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    # Extract card info for logging
    card = payload.get("card", {})
    header_title = card.get("header", {}).get("title", {}).get("content", "")
    elements = card.get("elements", [])
    content_parts = []
    for el in elements:
        if el.get("tag") == "markdown":
            content_parts.append(el.get("content", ""))
    content_summary = " | ".join(content_parts)[:300]

    # Save payload to disk first
    filepath = _save_payload(payload, header_title)
    logger.info(
        "Saved webhook payload: %s",
        os.path.basename(filepath),
    )

    # Read back from disk to send (ensures sent content matches saved file)
    with open(filepath, "r", encoding="utf-8") as f:
        saved_payload = json.load(f)

    logger.info(
        "Sending webhook [%s] -> %s",
        header_title, webhook_url[-20:],
    )
    logger.info("Webhook content: %s", content_summary)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook_url, json=saved_payload)
        if resp.status_code != 200:
            logger.error(
                "Webhook POST failed: %d -- %s",
                resp.status_code, resp.text[:200],
            )
            resp.raise_for_status()

    logger.info("Webhook sent successfully")


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
