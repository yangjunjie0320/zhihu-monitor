"""End-to-end test: fetch from Zhihu API, send to Feishu webhook."""

from __future__ import annotations

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Override env for local testing
os.environ["COOKIE_FILE"] = "/Users/yangjunjie/workspace/monitor-maqianzu/zhihu.com_cookies.txt"
os.environ["DATA_DIR"] = "/tmp/zhihu-monitor-test/data"
os.environ["LOG_DIR"] = "/tmp/zhihu-monitor-test/logs"
os.environ["DEBUG_MODE"] = "false"


async def test_cookies():
    """Test cookie parsing."""
    from utils.cookies import parse_cookies, check_cookie_expiry

    cookie_file = os.environ["COOKIE_FILE"]
    header_str, pw_cookies = parse_cookies(cookie_file)
    print(f"✅ Cookies: parsed {len(pw_cookies)} cookies")

    days_left = check_cookie_expiry(cookie_file)
    if days_left is not None:
        print(f"   ⚠️  Cookie expires in {days_left} days")
    else:
        print(f"   Cookie expiry: OK")

    return header_str, pw_cookies


async def test_config():
    """Test config loading with user_name."""
    from config import load_settings

    settings = load_settings()
    print(f"✅ Config: {len(settings.monitor_targets)} targets")
    for t in settings.monitor_targets:
        print(f"   {t.display_name} ({t.user_id}) → ...{t.webhook_url[-15:]}")
    return settings


async def test_zhihu_api(cookie_header: str):
    """Test Zhihu API fetching for both users."""
    from services.zhihu import ZhihuClient

    client = ZhihuClient(cookie_header)
    all_items = []

    for uid in ["ma-qian-zu", "toyama"]:
        print(f"\n--- Fetching for {uid} ---")
        items, errors = await client.fetch_all(uid)

        if errors:
            for err in errors:
                print(f"   ⚠️  {err}")

        answers = [i for i in items if i.content_type.value == "answer"]
        pins = [i for i in items if i.content_type.value == "pin"]
        articles = [i for i in items if i.content_type.value == "article"]
        print(f"✅ {uid}: {len(answers)} answers, {len(pins)} pins, {len(articles)} articles")

        for item in items[:2]:
            print(f"   [{item.content_type.value}] {item.title[:50]}")
            print(f"     hash: {item.content_hash[:12]}...")

        all_items.extend(items)

    return all_items


async def test_diff_detection(items):
    """Test differential update detection."""
    from utils.cache import get_cache
    from utils.state import StateManager

    cache = get_cache(os.environ["DATA_DIR"])
    state = StateManager(cache)

    uid = "test-diff-user"

    # First run: all items are new
    new_items, updated_items = state.detect_changes(uid, items[:5])
    print(f"✅ First run: {len(new_items)} new, {len(updated_items)} updated")
    assert len(new_items) == 5, f"Expected 5 new, got {len(new_items)}"
    assert len(updated_items) == 0, f"Expected 0 updated, got {len(updated_items)}"

    # Save state
    state.update_seen_ids(uid, {i.id for i in items[:5]})
    hashes = {i.id: i.content_hash for i in items[:5]}
    state.update_content_hashes(uid, hashes)

    # Second run: same items → no changes
    new_items, updated_items = state.detect_changes(uid, items[:5])
    print(f"✅ Second run (unchanged): {len(new_items)} new, {len(updated_items)} updated")
    assert len(new_items) == 0
    assert len(updated_items) == 0

    # Third run: simulate content change by modifying a hash
    hashes[items[0].id] = "fake_changed_hash"
    state.update_content_hashes(uid, hashes)
    new_items, updated_items = state.detect_changes(uid, items[:5])
    print(f"✅ Third run (1 changed): {len(new_items)} new, {len(updated_items)} updated")
    assert len(new_items) == 0
    assert len(updated_items) == 1

    # Fourth run: 3 new items added
    new_items, updated_items = state.detect_changes(uid, items[:8])
    print(f"✅ Fourth run (3 added): {len(new_items)} new, {len(updated_items)} updated")
    assert len(new_items) == 3

    cache.close()


async def test_webhook_notifications(items):
    """Test sending both new and updated content to Feishu."""
    from services import webhook

    webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/5a8b0c08-76ad-4891-a3ec-fea4ac6c88a9"

    # Test new content notification
    print("\n--- Sending new content notification ---")
    await webhook.send_new_content(webhook_url, items[:2])
    print("✅ New content notification sent")

    # Test updated content notification
    print("--- Sending updated content notification ---")
    await webhook.send_updated_content(webhook_url, items[2:4], "马前卒")
    print("✅ Updated content notification sent")


async def main():
    print("=" * 55)
    print("Zhihu Monitor — E2E Test (with diff detection)")
    print("=" * 55)

    # 1. Config
    print("\n[1/5] Config Loading")
    settings = await test_config()

    # 2. Cookies
    print("\n[2/5] Cookie Parsing")
    cookie_header, pw_cookies = await test_cookies()

    # 3. Zhihu API
    print("\n[3/5] Zhihu API Fetch")
    items = await test_zhihu_api(cookie_header)

    # 4. Differential Detection
    print("\n[4/5] Differential Detection")
    await test_diff_detection(items)

    # 5. Feishu Webhook
    print("\n[5/5] Feishu Webhook")
    await test_webhook_notifications(items)

    print("\n" + "=" * 55)
    print("All tests passed! ✅")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
