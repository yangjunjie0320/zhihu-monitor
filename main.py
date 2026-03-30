"""Zhihu Monitor entrypoint.

Loops through monitoring targets, fetches new content,
archives and screenshots, sends notifications.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from config import Settings, load_settings
from models import MonitorTarget
from services.archive import ArchiveService
from services.history import ContentHistory
from services.screenshot import ScreenshotService
from services.zhihu import ZhihuClient
from services import webhook
from utils.cache import get_cache
from utils.cookies import check_cookie_expiry, parse_cookies
from utils.logging import setup_logging
from utils.state import StateManager
from utils.time import now_beijing

logger = logging.getLogger(__name__)


async def process_user_targets(
    uid: str,
    targets: list[MonitorTarget],
    settings: Settings,
    zhihu_client: ZhihuClient,
    state: StateManager,
    history: ContentHistory,
    archive: ArchiveService,
    screenshot_svc: ScreenshotService,
) -> None:
    """Process monitoring for a single user and broadcast to all configured targets.

    Args:
        uid: The Zhihu user url_token.
        targets: List of MonitorTargets that subscribe to this user.
        settings: Application settings.
        zhihu_client: Zhihu API client.
        state: State manager.
        history: Content history (persistent diff detection).
        archive: Archive service.
        screenshot_svc: Screenshot service.
    """
    display = targets[0].display_name
    logger.info("Processing user: %s (%s) for %d webhooks", uid, display, len(targets))

    # Fetch all content
    items, errors = await zhihu_client.fetch_all(uid)

    # Record errors
    cookie_invalid = False
    for err in errors:
        state.add_error(uid, err)
        if "Cookie 已失效" in err:
            cookie_invalid = True

    # If cookie invalidation is detected mid-flight, send immediate alert
    if cookie_invalid:
        if state.should_send_cookie_reminder(settings.cookie_reminder_interval_days):
            logger.warning("Cookie invalidation detected via API 401/403, sending immediate reminder")
            unique_webhooks = list(dict.fromkeys(t.webhook_url for t in settings.monitor_targets))
            for wh_url in unique_webhooks:
                await webhook.send_cookie_reminder(wh_url, 0)
            state.set_last_cookie_reminder()

    # Differential detection via persistent content history
    new_items, updated_items = history.record_batch(uid, items)

    if new_items:
        logger.info(
            "Found %d new items for %s (%s)",
            len(new_items), display, uid,
        )

        # Archive and screenshot each new item
        screenshots: dict[str, str] = {}
        for item in new_items:
            archive.save(item, {
                "id": item.id,
                "type": item.content_type.value,
                "title": item.title,
                "url": item.url,
                "summary": item.summary,
                "created_time": item.created_time.isoformat(),
                "content_hash": item.content_hash,
            })

            # TEMPORARILY DISABLED: Screenshot currently takes too long (30s timeouts)
            # screenshot_path = await screenshot_svc.capture(
            #     item.url, f"{uid}_{item.id}"
            # )
            # if screenshot_path:
            #     screenshots[item.id] = screenshot_path

        # Send new content notification to all targets subscribing to this user
        for t in targets:
            await webhook.send_new_content(
                t.webhook_url, new_items, screenshots, t.display_name
            )

        # Update seen_ids for silence tracking
        new_ids = {item.id for item in new_items}
        state.update_seen_ids(uid, new_ids)
        state.set_last_new_content(uid)

    if updated_items:
        logger.info(
            "Found %d updated items for %s (%s)",
            len(updated_items), display, uid,
        )

        # Archive updated items
        for item in updated_items:
            version_count = history.get_version_count(uid, item.id)
            archive.save(item, {
                "id": item.id,
                "type": item.content_type.value,
                "title": item.title,
                "url": item.url,
                "summary": item.summary,
                "created_time": item.created_time.isoformat(),
                "content_hash": item.content_hash,
                "version": version_count,
            })

        # TEMPORARILY DISABLED: User requested to only archive updates without sending notifications
        # await webhook.send_updated_content(
        #     target.webhook_url, updated_items, display
        # )

    if not new_items and not updated_items:
        logger.info("No changes for %s (%s)", display, uid)

        # Heartbeat: send alive confirmation if no content for 72h
        if state.should_send_silence_reminder(uid, settings.silence_hours):
            logger.info("Sending heartbeat for %s", display)
            for t in targets:
                await webhook.send_heartbeat(
                    t.webhook_url, uid, t.display_name
                )
            # Reset the timer so next heartbeat is in another 72h
            state.set_last_new_content(uid)

    # Update last check time
    state.set_last_check(uid)

    # Error report (rate limited)
    if state.should_send_error_report(
        uid, settings.error_report_interval_hours
    ):
        user_errors = state.get_errors(uid)
        logger.info("Sending error report for %s (%d errors)", uid, len(user_errors))
        for t in targets:
            await webhook.send_error_report(
                t.webhook_url, uid, user_errors
            )
        state.set_last_error_report(uid)
        state.clear_errors(uid)

    # Debug notification
    if settings.debug_mode:
        for t in targets:
            await webhook.send_debug(
                t.webhook_url,
                uid,
                {
                    "total_items": len(items),
                    "new_items": len(new_items),
                    "seen_ids_count": len(state.get_seen_ids(uid)),
                    "errors": len(errors),
                    "time": now_beijing().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )


async def main() -> None:
    """Main entrypoint: load config, check cookies, process all targets."""
    # Load settings
    settings = load_settings()

    # Setup logging
    setup_logging(settings.log_dir)
    logger.info("=== Zhihu Monitor started ===")

    # Load cookies
    cookie_header, playwright_cookies = parse_cookies(settings.cookie_file)

    # Initialize shared services
    cache = get_cache(settings.data_dir)
    state = StateManager(cache)
    history = ContentHistory(settings.data_dir)
    archive = ArchiveService(settings.data_dir)
    screenshot_svc = ScreenshotService(playwright_cookies, settings.data_dir)
    zhihu_client = ZhihuClient(cookie_header)
    webhook.init_webhook_dir(settings.data_dir)

    # Check cookie expiry and send reminder if needed
    days_left = check_cookie_expiry(settings.cookie_file)
    if days_left is not None:
        if state.should_send_cookie_reminder(
            settings.cookie_reminder_interval_days
        ):
            # Send to all unique webhooks
            unique_webhooks = list(dict.fromkeys(
                t.webhook_url for t in settings.monitor_targets
            ))
            logger.info(
                "Cookie expires in %d days, sending reminder to %d webhooks",
                days_left, len(unique_webhooks),
            )
            for wh_url in unique_webhooks:
                await webhook.send_cookie_reminder(wh_url, days_left)
            state.set_last_cookie_reminder()

    # Group targets by user_id
    targets_by_uid: dict[str, list[MonitorTarget]] = {}
    for target in settings.monitor_targets:
        targets_by_uid.setdefault(target.user_id, []).append(target)

    # Process each user_id independently
    for uid, targets in targets_by_uid.items():
        try:
            await process_user_targets(
                uid, targets, settings, zhihu_client, state, history,
                archive, screenshot_svc
            )
        except Exception as e:
            logger.error(
                "Failed to process user %s: %s", uid, e,
                exc_info=True,
            )
            continue

    # Archive cleanup
    removed = archive.cleanup(settings.archive_max_days)
    if removed:
        logger.info("Cleaned up %d old archive files", removed)

    # Close cache
    cache.close()
    logger.info("=== Zhihu Monitor finished ===")


if __name__ == "__main__":
    asyncio.run(main())
