"""End-to-end test: fetch Zhihu API, test diff detection, send Feishu cards."""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["COOKIE_FILE"] = "/Users/yangjunjie/workspace/monitor-maqianzu/zhihu.com_cookies.txt"
os.environ["DATA_DIR"] = "/tmp/zhihu-monitor-test/data"
os.environ["LOG_DIR"] = "/Users/yangjunjie/workspace/zhihu-monitor/logs"
os.environ["DEBUG_MODE"] = "false"

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/5a8b0c08-76ad-4891-a3ec-fea4ac6c88a9"


async def test_config():
    from config import load_settings
    s = load_settings()
    print(f"✅ {len(s.monitor_targets)} targets, SILENCE_HOURS={s.silence_hours}")
    for t in s.monitor_targets:
        print(f"   {t.display_name} ({t.user_id})")
    return s


async def test_cookies():
    from utils.cookies import parse_cookies, check_cookie_expiry
    h, c = parse_cookies(os.environ["COOKIE_FILE"])
    days = check_cookie_expiry(os.environ["COOKIE_FILE"])
    status = f"⚠️ expires in {days}d" if days is not None else "OK"
    print(f"✅ {len(c)} cookies ({status})")
    return h


async def test_api(cookie_header):
    from services.zhihu import ZhihuClient
    client = ZhihuClient(cookie_header)
    all_items = []
    for uid in ["shui-qian-xiao-xi", "toyama"]:
        items, errors = await client.fetch_all(uid)
        a = sum(1 for i in items if i.content_type.value == "answer")
        p = sum(1 for i in items if i.content_type.value == "pin")
        r = sum(1 for i in items if i.content_type.value == "article")
        err = f" ({len(errors)} errors)" if errors else ""
        print(f"✅ {uid}: {a}回答 {p}想法 {r}文章{err}")
        all_items.extend(items)
    return all_items


async def test_history(items):
    from services.history import ContentHistory
    h = ContentHistory(os.environ["DATA_DIR"])
    uid = "test-hist"

    new, upd = h.record_batch(uid, items[:5])
    assert len(new) == 5 and len(upd) == 0
    print(f"✅ Run 1: {len(new)} new, {len(upd)} updated")

    new, upd = h.record_batch(uid, items[:5])
    assert len(new) == 0 and len(upd) == 0
    print(f"✅ Run 2: {len(new)} new, {len(upd)} updated (unchanged)")

    new, upd = h.record_batch(uid, items[:8])
    assert len(new) == 3
    print(f"✅ Run 3: {len(new)} new (incremental)")

    files = os.listdir(os.path.join(os.environ["DATA_DIR"], "history", uid))
    print(f"   {len(files)} permanent history files on disk")


async def test_cards(items):
    from services import webhook

    # Test new content card — grouped layout
    print("\n--- New content card (马前卒) ---")
    maqianzu_items = []
    # Mix different types to showcase the grouped layout properly
    types_found = set()
    for item in items:
        if item.content_type not in types_found:
            maqianzu_items.append(item)
            types_found.add(item.content_type)
        if len(types_found) == 3:
            break
            
    await webhook.send_new_content(WEBHOOK, maqianzu_items, {}, "马前卒")
    print("✅ Sent: grouped by type with summary counts")

    # Test updated content card
    print("--- Updated content card (远山) ---")
    toyama_items = []
    # Extract mix from the second half (Toyama's real items)
    types_found_t = set()
    for item in reversed(items):
        if item.content_type not in types_found_t:
            toyama_items.append(item)
            types_found_t.add(item.content_type)
        if len(types_found_t) == 3:
            break
            
    await webhook.send_updated_content(WEBHOOK, toyama_items, "远山")
    print("✅ Sent: updated content")

    # Test heartbeat card
    print("--- Heartbeat card ---")
    await webhook.send_heartbeat(WEBHOOK, "shui-qian-xiao-xi", "马前卒")
    print("✅ Sent: 72h heartbeat")


async def main():
    print("=" * 50)
    print("Zhihu Monitor — E2E Test")
    print("=" * 50)

    print("\n[1/5] Config")
    await test_config()

    print("\n[2/5] Cookies")
    header = await test_cookies()

    print("\n[3/5] API Fetch")
    items = await test_api(header)

    print("\n[4/5] Content History")
    await test_history(items)

    print("\n[5/5] Feishu Cards")
    await test_cards(items)

    print("\n" + "=" * 50)
    print("All tests passed! ✅")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
