"""Zhihu API v4 client: fetch answers and pins for a user."""

from __future__ import annotations

import hashlib
import json
import logging

import httpx

from constants import ContentType
from models import Item
from utils.text import strip_html, extract_summary
from utils.time import timestamp_to_beijing

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.zhihu.com/api/v4"

_ANSWER_INCLUDE = (
    "data[*].content,excerpt,created_time,updated_time,"
    "voteup_count,comment_count,question.title"
)

_PIN_INCLUDE = (
    "data[*].content,created,updated,comment_count,reaction_count"
)

_ARTICLE_INCLUDE = (
    "data[*].content,excerpt,created,updated,voteup_count,"
    "comment_count,image_url,title"
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class ZhihuClient:
    """Async HTTP client for Zhihu API v4."""

    def __init__(self, cookie_header: str) -> None:
        """Initialize with cookie header string.

        Args:
            cookie_header: Cookies as "k1=v1; k2=v2" string.
        """
        self._cookie_header = cookie_header

    def _headers(self, uid: str) -> dict[str, str]:
        """Build request headers for a given user."""
        return {
            "User-Agent": _USER_AGENT,
            "Referer": f"https://www.zhihu.com/people/{uid}",
            "x-requested-with": "fetch",
            "Cookie": self._cookie_header,
        }

    async def fetch_answers(self, uid: str) -> list[Item]:
        """Fetch recent answers for a Zhihu user.

        Args:
            uid: Zhihu user url_token (e.g. "shui-qian-xiao-xi").

        Returns:
            List of Item objects for answers.
        """
        url = f"{_BASE_URL}/members/{uid}/answers"
        params = {
            "include": _ANSWER_INCLUDE,
            "limit": "5",
            "offset": "0",
            "sort_by": "created",
        }

        items = []
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url, params=params, headers=self._headers(uid)
            )
            resp.raise_for_status()
            data = resp.json()

        for raw in data.get("data", []):
            try:
                answer_id = str(raw["id"])
                question = raw.get("question", {})
                question_id = str(question.get("id", ""))
                title = question.get("title", "无标题")
                excerpt = raw.get("excerpt", "")
                content = raw.get("content", "")
                created_ts = raw.get("created_time", 0)

                answer_url = (
                    f"https://www.zhihu.com/question/{question_id}"
                    f"/answer/{answer_id}"
                )

                # Hash plain text to avoid endless updates from HTML image tracker changes
                clean_content = strip_html(content)
                clean_excerpt = strip_html(excerpt)
                hash_src = f"{title}|{clean_content}|{clean_excerpt}"
                content_hash = hashlib.md5(hash_src.encode()).hexdigest()

                item = Item(
                    id=answer_id,
                    content_type=ContentType.ANSWER,
                    title=title,
                    url=answer_url,
                    summary=extract_summary(strip_html(excerpt)),
                    created_time=timestamp_to_beijing(created_ts),
                    has_images="<img" in content,
                    content_hash=content_hash,
                )
                items.append(item)
            except (KeyError, TypeError, ValueError) as e:
                snippet = json.dumps(raw, ensure_ascii=False)[:200]
                logger.error(
                    "Failed to parse answer for %s: %s — raw: %s",
                    uid, e, snippet,
                )

        logger.info("Fetched %d answers for %s", len(items), uid)
        return items

    async def fetch_pins(self, uid: str) -> list[Item]:
        """Fetch recent pins (想法) for a Zhihu user.

        Args:
            uid: Zhihu user url_token.

        Returns:
            List of Item objects for pins.
        """
        url = f"{_BASE_URL}/members/{uid}/pins"
        params = {
            "include": _PIN_INCLUDE,
            "limit": "5",
            "offset": "0",
        }

        items = []
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url, params=params, headers=self._headers(uid)
            )
            resp.raise_for_status()
            data = resp.json()

        for raw in data.get("data", []):
            try:
                pin_id = str(raw["id"])
                created_ts = raw.get("created", 0)
                content_blocks = raw.get("content", [])

                # content is a JSON array of blocks
                if isinstance(content_blocks, str):
                    try:
                        content_blocks = json.loads(content_blocks)
                    except json.JSONDecodeError:
                        content_blocks = []

                # Extract title and summary from first text block
                title = "想法"
                summary_text = ""
                has_images = False

                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "")

                    if block_type == "text":
                        text_content = block.get("content", "")
                        clean_text = strip_html(text_content)
                        if not summary_text:
                            summary_text = clean_text
                            # Use first line as title if short enough
                            first_line = clean_text.split("\n")[0]
                            if len(first_line) <= 50:
                                title = first_line
                    elif block_type == "image":
                        has_images = True
                    elif block_type in ("link", "video"):
                        pass  # Known types, skip
                    else:
                        # Unknown block type — skip, not crash
                        logger.debug(
                            "Unknown pin block type '%s' for pin %s",
                            block_type, pin_id,
                        )

                pin_url = f"https://www.zhihu.com/pin/{pin_id}"

                # Hash content for diff detection
                hash_src = f"{title}|{summary_text}"
                content_hash = hashlib.md5(hash_src.encode()).hexdigest()

                item = Item(
                    id=pin_id,
                    content_type=ContentType.PIN,
                    title=title,
                    url=pin_url,
                    summary=extract_summary(summary_text),
                    created_time=timestamp_to_beijing(created_ts),
                    has_images=has_images,
                    content_hash=content_hash,
                )
                items.append(item)
            except (KeyError, TypeError, ValueError) as e:
                snippet = json.dumps(raw, ensure_ascii=False)[:200]
                logger.error(
                    "Failed to parse pin for %s: %s — raw: %s",
                    uid, e, snippet,
                )

        logger.info("Fetched %d pins for %s", len(items), uid)
        return items

    async def fetch_articles(self, uid: str) -> list[Item]:
        """Fetch recent articles (文章) for a Zhihu user.

        Args:
            uid: Zhihu user url_token.

        Returns:
            List of Item objects for articles.
        """
        url = f"{_BASE_URL}/members/{uid}/articles"
        params = {
            "include": _ARTICLE_INCLUDE,
            "limit": "5",
            "offset": "0",
            "sort_by": "created",
        }

        items = []
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url, params=params, headers=self._headers(uid)
            )
            resp.raise_for_status()
            data = resp.json()

        for raw in data.get("data", []):
            try:
                article_id = str(raw["id"])
                title = raw.get("title", "无标题")
                excerpt = raw.get("excerpt", "")
                content = raw.get("content", "")
                created_ts = raw.get("created", 0)

                article_url = f"https://zhuanlan.zhihu.com/p/{article_id}"

                # Hash plain text to avoid endless updates from HTML image tracker changes
                clean_content = strip_html(content)
                clean_excerpt = strip_html(excerpt)
                hash_src = f"{title}|{clean_content}|{clean_excerpt}"
                content_hash = hashlib.md5(hash_src.encode()).hexdigest()

                item = Item(
                    id=article_id,
                    content_type=ContentType.ARTICLE,
                    title=title,
                    url=article_url,
                    summary=extract_summary(strip_html(excerpt)),
                    created_time=timestamp_to_beijing(created_ts),
                    has_images="<img" in content if content else False,
                    content_hash=content_hash,
                )
                items.append(item)
            except (KeyError, TypeError, ValueError) as e:
                snippet = json.dumps(raw, ensure_ascii=False)[:200]
                logger.error(
                    "Failed to parse article for %s: %s — raw: %s",
                    uid, e, snippet,
                )

        logger.info("Fetched %d articles for %s", len(items), uid)
        return items

    async def fetch_all(self, uid: str) -> tuple[list[Item], list[str]]:
        """Fetch answers, pins, and articles for a user.

        Args:
            uid: Zhihu user url_token.

        Returns:
            Tuple of (items, errors). Items is the combined list,
            errors is a list of error messages from failed fetches.
        """
        all_items: list[Item] = []
        errors: list[str] = []

        try:
            answers = await self.fetch_answers(uid)
            all_items.extend(answers)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403, 400):
                msg = f"Cookie 已失效 ({e.response.status_code})，请更新 Cookie 文件"
            else:
                msg = f"Answers API error for {uid}: {e.response.status_code}"
            logger.warning(msg)
            errors.append(msg)
        except Exception as e:
            msg = f"Answers fetch error for {uid}: {e}"
            logger.warning(msg)
            errors.append(msg)

        try:
            pins = await self.fetch_pins(uid)
            all_items.extend(pins)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403, 400):
                msg = f"Cookie 已失效 ({e.response.status_code})，请更新 Cookie 文件"
            else:
                msg = f"Pins API error for {uid}: {e.response.status_code}"
            logger.warning(msg)
            errors.append(msg)
        except Exception as e:
            msg = f"Pins fetch error for {uid}: {e}"
            logger.warning(msg)
            errors.append(msg)

        try:
            articles = await self.fetch_articles(uid)
            all_items.extend(articles)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403, 400):
                msg = f"Cookie 已失效 ({e.response.status_code})，请更新 Cookie 文件"
            else:
                msg = f"Articles API error for {uid}: {e.response.status_code}"
            logger.warning(msg)
            errors.append(msg)
        except Exception as e:
            msg = f"Articles fetch error for {uid}: {e}"
            logger.warning(msg)
            errors.append(msg)

        return all_items, errors
