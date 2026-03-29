"""End-to-end test: fetch from Zhihu API, send to Feishu webhook."""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["COOKIE_FILE"] = "/Users/yangjunjie/workspace/monitor-maqianzu/zhihu.com_cookies.txt"
os.environ["DATA_DIR"] = "/tmp/zhihu-monitor-test/data"
os.environ["LOG_DIR"] = "/tmp/zhihu-monitor-test/logs"
os.environ["DEBUG_MODE"] = "false"


async def test_config():
    from config import load_settings
    settings = load_settings()
    print(f"✅ Config: {len(settings.monitor_targets)} targets")
    for t in settings.monitor_targets:
        print(f"   {t.display_name} ({t.user_id}) → ...{t.webhook_url[-15:]}")
    return settings


async def test_cookies():
    from utils.cookies import parse_cookies, check_cookie_expiry
    cookie_file = os.environ["COOKIE_FILE"]
    header_str, pw_cookies = parse_cookies(cookie_file)
    print(f"✅ Cookies: {len(pw_cookies)} parsed")
    days = check_cookie_expiry(cookie_file)
    if days is not None:
        print(f"   ⚠️  Expires in {days} days")
    return header_str, pw_cookies


async def test_zhihu_api(cookie_header):
    from services.zhihu import ZhihuClient
    client = ZhihuClient(cookie_header)
    all_items = []
    for uid in ["shui-qian-xiao-xi", "toyama"]:
        print(f"\n--- {uid} ---")
        items, errors = await client.fetch_all(uid)
        if errors:
            for e in errors:
                print(f"   ⚠️  {e}")
        a = sum(1 for i in items if i.content_type.value == "answer")
        p = sum(1 for i in items if i.content_type.value == "pin")
        r = sum(1 for i in items if i.content_type.value == "article")
        print(f"✅ {a} answers, {p} pins, {r} articles")
        for item in items[:2]:
            print(f"   [{item.content_type.value}] {item.title[:45]} (hash:{item.content_hash[:8]})")
        all_items.extend(items)
    return all_items


async def test_content_history(items):
    from services.history import ContentHistory
    history = ContentHistory(os.environ["DATA_DIR"])

    uid = "test-history"

    # Run 1: all new
    new, updated = history.record_batch(uid, items[:5])
    print(f"✅ Run 1 (fresh): {len(new)} new, {len(updated)} updated")
    assert len(new) == 5 and len(updated) == 0

    # Run 2: same items → no changes
    new, updated = history.record_batch(uid, items[:5])
    print(f"✅ Run 2 (same):  {len(new)} new, {len(updated)} updated")
    assert len(new) == 0 and len(updated) == 0

    # Run 3: 3 new items added
    new, updated = history.record_batch(uid, items[:8])
    print(f"✅ Run 3 (+3):    {len(new)} new, {len(updated)} updated")
    assert len(new) == 3

    # Check version count
    v = history.get_version_count(uid, items[0].id)
    print(f"   Item {items[0].id}: {v} version(s)")

    # Verify files exist on disk
    import os as _os
    history_dir = _os.path.join(os.environ["DATA_DIR"], "history", uid)
    files = _os.listdir(history_dir)
    print(f"   {len(files)} history files on disk (permanent)")


async def test_feishu(items):
    from services import webhook
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/5a8b0c08-76ad-4891-a3ec-fea4ac6c88a9"

    print("\n--- New content card (马前卒) ---")
    maqianzu_items = [i for i in items if i.content_type.value == "answer"][:2]
    await webhook.send_new_content(url, maqianzu_items, {}, "马前卒")
    print("✅ Sent")

    print("--- Updated content card (远山) ---")
    toyama_items = [i for i in items if i.content_type.value == "article"][:2]
    await webhook.send_updated_content(url, toyama_items, "远山")
    print("✅ Sent")


async def main():
    print("=" * 55)
    print("Zhihu Monitor — Full E2E Test")
    print("=" * 55)

    print("\n[1/5] Config")
    await test_config()

    print("\n[2/5] Cookies")
    header, _ = await test_cookies()

    print("\n[3/5] Zhihu API")
    items = await test_zhihu_api(header)

    print("\n[4/5] Content History (diff detection)")
    await test_content_history(items)

    print("\n[5/5] Feishu Webhook")
    await test_feishu(items)

    print("\n" + "=" * 55)
    print("All tests passed! ✅")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
