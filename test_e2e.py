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
    print(f"   Header preview: {header_str[:80]}...")
    
    days_left = check_cookie_expiry(cookie_file)
    if days_left is not None:
        print(f"   ⚠️  Cookie expires in {days_left} days")
    else:
        print(f"   Cookie expiry: OK (not expiring soon)")
    
    return header_str, pw_cookies


async def test_zhihu_api(cookie_header: str):
    """Test Zhihu API fetching for both users."""
    from services.zhihu import ZhihuClient
    
    client = ZhihuClient(cookie_header)
    
    for uid in ["ma-qian-zu", "toyama"]:
        print(f"\n--- Fetching for {uid} ---")
        
        items, errors = await client.fetch_all(uid)
        
        if errors:
            for err in errors:
                print(f"   ⚠️  {err}")
        
        print(f"✅ {uid}: fetched {len(items)} items total")
        
        for item in items[:3]:  # Show first 3
            print(f"   [{item.content_type.value}] {item.title[:40]}")
            print(f"     URL: {item.url}")
            print(f"     Time: {item.created_time}")
            print(f"     Summary: {item.summary[:60]}...")
    
    return items  # Return last batch for webhook test


async def test_webhook(items):
    """Test sending a Feishu webhook notification."""
    from services import webhook
    
    webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/5a8b0c08-76ad-4891-a3ec-fea4ac6c88a9"
    
    if items:
        # Send only first 2 items as a test
        test_items = items[:2]
        print(f"\n--- Sending Feishu test ({len(test_items)} items) ---")
        await webhook.send_new_content(webhook_url, test_items)
        print("✅ Feishu new content notification sent!")
    else:
        print("⚠️  No items to send")


async def test_config():
    """Test config loading."""
    from config import load_settings
    
    settings = load_settings()
    print(f"✅ Config: {len(settings.monitor_targets)} targets")
    for t in settings.monitor_targets:
        print(f"   {t.user_id} → {t.webhook_url[-20:]}")
    return settings


async def test_state():
    """Test state management."""
    from utils.cache import get_cache
    from utils.state import StateManager
    
    cache = get_cache(os.environ["DATA_DIR"])
    state = StateManager(cache)
    
    # Test basic operations
    state.set_last_check("test-user")
    last = state.get_last_check("test-user")
    print(f"✅ State: last_check = {last}")
    
    state.update_seen_ids("test-user", {"id1", "id2", "id3"})
    seen = state.get_seen_ids("test-user")
    print(f"✅ State: seen_ids = {seen}")
    
    cache.close()


async def main():
    print("=" * 50)
    print("Zhihu Monitor — End-to-End Test")
    print("=" * 50)
    
    # 1. Config
    print("\n[1/5] Config Loading")
    settings = await test_config()
    
    # 2. Cookies
    print("\n[2/5] Cookie Parsing")
    cookie_header, pw_cookies = await test_cookies()
    
    # 3. State
    print("\n[3/5] State Management")
    await test_state()
    
    # 4. Zhihu API
    print("\n[4/5] Zhihu API Fetch")
    items = await test_zhihu_api(cookie_header)
    
    # 5. Feishu Webhook
    print("\n[5/5] Feishu Webhook")
    await test_webhook(items)
    
    print("\n" + "=" * 50)
    print("All tests passed! ✅")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
