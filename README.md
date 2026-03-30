# Zhihu Monitor

异步 Python 服务，监控知乎用户的回答、想法、文章，通过飞书 Webhook 推送通知。

## 功能

- **多用户监控** — 同一用户可推送到多个飞书群（按 `user_id` 去重抓取，广播通知）
- **三种内容类型** — 回答、想法（Pin）、专栏文章
- **增量检测** — 基于 `title|excerpt` 哈希，仅推送真正新增的内容
- **内容版本历史** — `data/history/` 永久保存每条内容的所有版本哈希
- **消息发送记录** — `data/sent/` 永久保存每条 webhook 发送的完整 JSON payload
- **原始数据归档** — `data/archive/` 保存内容快照，默认保留 30 天
- **Cookie 过期提醒** — 基于文件修改时间计算 14 天生命周期，到期前 7 天发送提醒
- **Cookie 失效检测** — API 返回 401/403 时立即向所有飞书群发送告警

## 快速开始

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env 填入 MONITOR_TARGETS 和飞书 Webhook

# 2. 放置知乎 Cookie（Netscape 格式）
mkdir -p cookies
cp your_cookies.txt cookies/zhihu.com_cookies.txt

# 3. 启动
docker compose up --build -d

# 4. 手动触发一次（验证配置）
docker compose run --rm monitor python main.py

# 5. 查看日志
cat ../logs/zhihu_monitor.log
```

## 测试

所有测试通过 Docker 执行，确保与生产环境一致。

### 完整测试流程

```bash
# 1. 清除所有缓存和历史数据（从干净状态开始）
rm -rf data/cache data/history data/archive data/screenshots data/sent

# 2. 重建镜像并启动
docker compose up --build -d

# 3. 清空日志
truncate -s 0 ../logs/zhihu_monitor.log

# 4. 手动触发一次
docker compose run --rm monitor python main.py

# 5. 检查日志（确认无重复行、无错误）
cat ../logs/zhihu_monitor.log

# 6. 检查发送记录
ls data/sent/$(date +%Y-%m-%d)/
cat data/sent/$(date +%Y-%m-%d)/*.json | head -50

# 7. 再次手动触发（应显示 "No changes"，不发送新通知）
docker compose run --rm monitor python main.py
cat ../logs/zhihu_monitor.log
```

### 验证要点

| 检查项 | 预期结果 |
|---|---|
| 日志无重复行 | 每条日志只出现一次 |
| 马前卒推送到两个群 | 日志显示 `for 2 webhooks`，两次 `Webhook sent successfully` |
| 第二次运行无新通知 | 日志显示 `No changes` |
| `data/sent/` 有文件 | 每次发送都保存了完整的飞书卡片 JSON |
| `data/history/` 有记录 | 每个用户的每条内容都有 JSON 文件 |
| 无 `Content updated` 误报 | 不应出现 version 持续递增 |

### 查看容器状态

```bash
# 容器是否在运行
docker ps --filter "name=zhihu"

# 查看容器日志（含 supercronic 调度信息）
docker logs zhihu-monitor --tail 50

# 检查 cron 执行间隔
docker logs zhihu-monitor 2>&1 | grep "job succeeded"
```

## 配置

`MONITOR_TARGETS` JSON 数组示例：

```json
[
  {"user_id": "shui-qian-xiao-xi", "user_name": "马前卒", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"},
  {"user_id": "shui-qian-xiao-xi", "user_name": "马前卒", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/yyy"},
  {"user_id": "toyama", "user_name": "远山", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"}
]
```

> 同一 `user_id` 配置多个 webhook 时，API 只请求一次，通知广播到所有对应的群。

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MONITOR_TARGETS` | 必填 | 监控目标 JSON |
| `COOKIE_FILE` | `/app/cookies/zhihu.com_cookies.txt` | Cookie 文件路径 |
| `DATA_DIR` | `/app/data` | 数据目录 |
| `LOG_DIR` | `/app/data/logs` | 日志目录 |
| `SILENCE_HOURS` | `72` | 静默提醒阈值（小时） |
| `ARCHIVE_MAX_DAYS` | `30` | 归档保留天数 |
| `ERROR_REPORT_INTERVAL_HOURS` | `24` | 错误报告间隔（小时） |
| `COOKIE_REMINDER_INTERVAL_DAYS` | `5` | Cookie 提醒间隔（天） |
| `DEBUG_MODE` | `false` | 调试模式 |

## 架构

```
zhihu-monitor/
├── main.py              # 入口：按 user_id 分组处理，广播通知到所有 webhook
├── config.py            # 环境变量 -> frozen dataclass（唯一 os.environ 读取点）
├── models.py            # MonitorTarget, Item 数据类
├── constants.py         # ContentType, NotificationType 枚举
├── services/
│   ├── zhihu.py         # 知乎 API v4 客户端（回答/想法/文章）
│   ├── webhook.py       # 飞书卡片构建 + 发送前持久化 + HTTP POST
│   ├── history.py       # 内容版本历史（永久 JSON 存储，增量检测核心）
│   ├── screenshot.py    # Playwright 全页截图（当前已禁用）
│   └── archive.py       # 原始数据归档 + 过期清理
├── utils/
│   ├── state.py         # diskcache 运行状态（seen_ids, last_check, errors）
│   ├── cookies.py       # Netscape Cookie 解析 + 14天过期检测
│   ├── cache.py         # diskcache 工厂
│   ├── text.py          # HTML 清理、摘要提取
│   ├── time.py          # 北京时区转换
│   └── logging.py       # TimedRotatingFileHandler + 控制台日志
├── Dockerfile           # 两阶段构建：supercronic + Python 3.12-slim
├── docker-compose.yml   # 单容器部署，挂载 data/ 和 cookies/
└── crontab              # */11 * * * *（每 11 分钟执行）
```

## 数据目录

| 路径 | 保留策略 | 说明 |
|---|---|---|
| `data/history/` | 永久 | 每条内容的版本哈希记录，用于增量检测 |
| `data/sent/` | 永久 | 每条 webhook 发送的完整 JSON payload |
| `data/archive/` | 30 天 | 内容快照（标题、摘要、链接、hash） |
| `data/cache/` | 运行期 | diskcache 运行状态（seen_ids、计时器等） |
| `../logs/` | 7 天轮转 | 日志文件（TimedRotatingFileHandler） |

## 通知类型

| 类型 | 触发条件 | 频率 | 目标 |
|---|---|---|---|
| [NEW] 新内容 | 新回答/想法/文章 | 每次检测 | 对应用户的所有 webhook |
| [OK] 静默提醒 | 超过 72h 无新内容 | 每触发一次 | 对应用户的所有 webhook |
| [ERROR] 错误报告 | API 请求失败 | 每用户 24h 一次 | 对应用户的所有 webhook |
| [COOKIE] Cookie 过期 | 14天生命周期即将到期 | 5天一次 | 所有唯一 webhook |
| [COOKIE] Cookie 已过期 | API 返回 401/403 | 立即 | 所有唯一 webhook |

> 内容更新（hash 变化）仅归档，不发送通知。
