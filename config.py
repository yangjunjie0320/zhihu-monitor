"""Configuration from environment variables. Sole os.environ reader."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from models import MonitorTarget

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application settings parsed from environment variables."""

    monitor_targets: list[MonitorTarget] = field(default_factory=list)
    cookie_file: str = "/app/cookies/zhihu.com_cookies.txt"
    data_dir: str = "/app/data"
    log_dir: str = "/app/data/logs"
    debug_mode: bool = False
    archive_max_days: int = 30
    silence_hours: int = 72
    error_report_interval_hours: int = 24
    cookie_reminder_interval_days: int = 5


def load_settings() -> Settings:
    """Load settings from environment variables."""
    targets_raw = os.environ.get("MONITOR_TARGETS")
    if not targets_raw:
        raise ValueError("MONITOR_TARGETS environment variable is required")

    targets_json = json.loads(targets_raw)
    targets = [
        MonitorTarget(
            user_id=t["user_id"],
            webhook_url=t["webhook_url"],
            user_name=t.get("user_name", ""),
        )
        for t in targets_json
    ]

    return Settings(
        monitor_targets=targets,
        cookie_file=os.environ.get(
            "COOKIE_FILE", "/app/cookies/zhihu.com_cookies.txt"
        ),
        data_dir=os.environ.get("DATA_DIR", "/app/data"),
        log_dir=os.environ.get("LOG_DIR", "/app/data/logs"),
        debug_mode=os.environ.get("DEBUG_MODE", "false").lower() == "true",
        archive_max_days=int(os.environ.get("ARCHIVE_MAX_DAYS", "30")),
        silence_hours=int(os.environ.get("SILENCE_HOURS", "24")),
        error_report_interval_hours=int(
            os.environ.get("ERROR_REPORT_INTERVAL_HOURS", "24")
        ),
        cookie_reminder_interval_days=int(
            os.environ.get("COOKIE_REMINDER_INTERVAL_DAYS", "5")
        ),
    )
