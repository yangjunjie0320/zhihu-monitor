# Zhihu Monitor

异步 Python 服务，监控知乎用户的回答、想法、文章，通过飞书 Webhook 推送通知。

## 功能

- **多用户监控** — 同一用户可推送到多个飞书群
- **三种内容类型** — 回答、想法（Pin）、专栏文章
- **差量更新** — 内容变更检测，已有内容被修改也会通知
- **内容历史** — 永久保存每个内容的所有版本（JSON 文件）
- **全页截图** — Playwright Chromium 自动截图
- **Cookie 过期提醒** — 7天内过期自动飞书提醒

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

# 手动触发一次
docker compose run --rm monitor python main.py
```

## 配置

`MONITOR_TARGETS` JSON 数组示例：

```json
[
  {"user_id": "shui-qian-xiao-xi", "user_name": "马前卒", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"},
  {"user_id": "toyama", "user_name": "远山", "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/yyy"}
]
```

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MONITOR_TARGETS` | 必填 | 监控目标 JSON |
| `COOKIE_FILE` | `/app/cookies/zhihu.com_cookies.txt` | Cookie 文件路径 |
| `DATA_DIR` | `/app/data` | 数据目录 |
| `SILENCE_HOURS` | `24` | 静默提醒阈值 |
| `ARCHIVE_MAX_DAYS` | `30` | 归档保留天数 |
| `DEBUG_MODE` | `false` | 调试模式 |

## 架构

```
zhihu-monitor/
├── main.py              # 入口：异步循环处理每个监控目标
├── config.py            # 环境变量配置（唯一 os.environ 读取点）
├── models.py            # MonitorTarget, Item 数据类
├── constants.py         # ContentType, NotificationType 枚举
├── services/
│   ├── zhihu.py         # 知乎 API v4 客户端
│   ├── webhook.py       # 飞书消息卡片构建 + 推送
│   ├── history.py       # 内容版本历史（永久 JSON 存储）
│   ├── screenshot.py    # Playwright 全页截图
│   └── archive.py       # 原始数据归档 + 过期清理
├── utils/
│   ├── state.py         # diskcache 运行状态管理
│   ├── cookies.py       # Netscape Cookie 解析
│   ├── cache.py         # diskcache 工厂
│   ├── text.py          # HTML 清理
│   ├── time.py          # 时区转换
│   └── logging.py       # 日志配置
├── Dockerfile           # 两阶段构建：supercronic + Python 3.12
├── docker-compose.yml   # 单容器部署
└── crontab              # 每 11 分钟执行
```

## 通知类型

| 类型 | 触发条件 | 频率 |
|---|---|---|
| 📢 新内容 | 新回答/想法/文章 | 每次 |
| ✏️ 内容更新 | 已有内容被修改 | 每次 |
| 🔇 静默提醒 | 超过 24h 无新内容 | 每触发一次 |
| ⚠️ 错误报告 | API 请求失败 | 每用户 24h 一次 |
| 🍪 Cookie 过期 | 7天内过期 | 5天一次 |
