"""Netscape cookie file parser with expiry checking."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def parse_cookies(cookie_file: str) -> tuple[str, list[dict]]:
    """Parse a Netscape-format cookie file.

    Args:
        cookie_file: Path to the cookie file.

    Returns:
        Tuple of (header_string, playwright_cookies_list).
        - header_string: "k1=v1; k2=v2" for httpx
        - playwright_cookies_list: list of dicts for Playwright

    Raises:
        SystemExit: If file is missing or unparseable.
    """
    if not os.path.exists(cookie_file):
        logger.critical("Cookie file not found: %s", cookie_file)
        sys.exit(1)

    cookies: list[dict] = []
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain, _, path, secure, expires, name, value = parts[:7]
                cookies.append(
                    {
                        "domain": domain,
                        "path": path,
                        "secure": secure.upper() == "TRUE",
                        "expires": int(expires) if expires else -1,
                        "name": name,
                        "value": value,
                    }
                )
    except Exception as e:
        logger.critical("Failed to parse cookie file: %s", e)
        sys.exit(1)

    if not cookies:
        logger.critical("No cookies parsed from %s", cookie_file)
        sys.exit(1)

    # Build header string
    header_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    # Build Playwright-compatible cookies (force domain to .zhihu.com)
    playwright_cookies = []
    for c in cookies:
        playwright_cookies.append(
            {
                "name": c["name"],
                "value": c["value"],
                "domain": ".zhihu.com",
                "path": c["path"],
                "secure": c["secure"],
                "expires": c["expires"],
            }
        )

    logger.info("Loaded %d cookies from %s", len(cookies), cookie_file)
    return header_str, playwright_cookies


def check_cookie_expiry(cookie_file: str, threshold_days: int = 7) -> int | None:
    """Check if any cookies expire within threshold_days.

    Args:
        cookie_file: Path to the cookie file.
        threshold_days: Number of days to check ahead.

    Returns:
        Minimum days until expiry if any cookie expires within threshold,
        otherwise None.
    """
    if not os.path.exists(cookie_file):
        return 0

    now = datetime.now(timezone.utc).timestamp()
    threshold_seconds = threshold_days * 86400

    # User specified: Cookies expire in 14 days, use this duration to judge.
    try:
        mtime = os.path.getmtime(cookie_file)
    except OSError:
        return 0

    effective_expiry = mtime + (14 * 86400)
    remaining = effective_expiry - now

    if remaining < threshold_seconds:
        return max(0, int(remaining / 86400))
        
    return None
