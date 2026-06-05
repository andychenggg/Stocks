# 财经社区总结与预警站

线上站点：https://stock.autoin.me/

这个仓库维护三个生产流程：

- Whop 财经群聊天抓取、LLM 总结、静态站点发布。
- Serenity X 博主发帖抓取、原文归档、LLM 总结、静态站点发布。
- Binance 加密货币实时监控、预警持久化、HTTP/WebSocket 服务。

静态站点使用 VitePress，内容主要写入 `docs/`，GitHub Pages 部署由 `.github/workflows/deploy.yml` 触发。

## 更新规律

Whop 群聊总结由 `whop_summary.py` 根据美股市场时段决定总结模式：

- 非交易时段：约每 3 小时生成一次总结。
- 开盘前 1 小时和开盘期间：约每 1 小时生成一次总结。
- 收盘后：总结过去 24 小时消息。

Serenity X 总结由外部 cron 控制，每天美东时间 9:00 运行一次即可，不依赖美股是否开盘。

Crypto 预警服务是常驻进程，运行期间持续监听 Binance 行情并向前端/HTTP 接口提供最近预警。

## 站点输出

- Whop 最新总结：`docs/index.md`
- Whop 历史总结：`docs/summaries/`
- Serenity 历史总结：`docs/serenity-summaries/`
- 交易经验总结：`docs/trading-experiences/`
- Crypto 预警页面：`docs/alerts/`

Serenity 顶部导航只使用一个 tab：`serenity总结`，直接进入 `docs/serenity-summaries/`。每篇 Serenity 总结页先展示原文记录，每条原文包含北京时间、美西时间、美东时间和 tweet text，然后展示 AI 总结。

## 本地安装

Python 依赖：

```bash
pip install -r requirements.txt
```

站点依赖：

```bash
npm ci
```

本地预览站点：

```bash
npm run docs:dev
```

构建站点：

```bash
npm run docs:build
```

## 配置密钥

本地密钥放在 `utils/local_secrets.py`。该文件已被 `.gitignore` 忽略，不要提交真实密钥。

### 模型密钥

`utils/agent.py` 通过 `model_key` 选择 OpenAI 兼容接口或 Google Gemini：

```python
model_key = [
    {
        "model": "deepseek-v4-flash",
        "key": "密钥",
        "base_url": "https://example.com/v1",
        "app": "openai",
    },
    {
        "model": "gemini-2.5-pro",
        "key": "google 密钥",
        "app": "google",
    },
]
```

### Whop 请求配置

在 Whop 网页中打开开发者工具，在 Network 中找到：

```text
https://whop.com/api/graphql/MessagesFetchFeedPosts/
```

复制该请求的 request headers，整理成 Python 字典后写入 `utils/local_secrets.py`：

```python
whom_headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
    "baggage": "",
    "newrelic": "",
    "dpr": "",
    "origin": "https://whop.com",
    "priority": "",
    "referer": "https://whop.com/joined/stock-and-option/.../app/",
    "sec-ch-ua": "",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sentry-trace": "",
    "traceparent": "",
    "tracestate": "",
    "user-agent": "",
    "x-deployment-id": "",
    "x-whop-force-new-permission-system": "",
    "Cookie": "",
    "content-type": "application/json",
}
```

注意：

- Whop 对请求环境校验较严格，缺少浏览器请求头时可能返回 `429`。
- `Cookie`、`cf_clearance`、`whop-core.access-token` 等会话字段过期后需要重新捕获。
- 不要复制 HTTP/2 伪首部，例如 `:authority`、`:method`、`:path`、`:scheme`。
- 不要手工填写 `content-length`，让 `requests` 自动生成。

可以用下面脚本验证 Whop headers：

```python
import requests
from utils.local_secrets import whom_headers
from utils.message_utils import url, get_payload

resp = requests.post(url, headers=whom_headers, data=get_payload(5, None), timeout=30)
print(resp.status_code)
print(resp.text[:300])
```

### Serenity X 请求配置

Serenity 抓取使用 X GraphQL `UserTweets` 接口。将浏览器会话中捕获到的配置写入 `utils/local_secrets.py`：

```python
serenity_x_config = {
    "auth_token": "X auth_token cookie",
    "ct0": "X ct0 cookie / csrf token",
    "bearer": "X web bearer token",
    "user_id": "目标账号 user id",
    "operation_id": "UserTweets operation id",
    "screen_name": "aleabitoreddit",
}
```

这些值可能随 X 前端版本或会话过期而失效。若抓取失败，优先重新捕获 `auth_token`、`ct0`、`bearer` 和 `operation_id`。

## 运行流程

### Whop 总结

手动运行：

```bash
python whop_summary.py
```

定时任务 wrapper：

```bash
sh/run.sh
```

该脚本会写入 `docs/index.md` 和 `docs/summaries/`，然后执行 `git add docs/ && git commit && git push origin master`。

### Serenity X 总结

手动运行：

```bash
python serenity_summary.py
```

定时任务 wrapper：

```bash
sh/serenity_run.sh
```

推荐 cron 使用美东时间：

```cron
TZ=America/New_York
0 9 * * * /root/code/stocks-deploy/sh/serenity_run.sh
```

该脚本会更新 `docs/serenity-summaries/`，然后执行 `git add docs/ && git commit && git push origin master`。

Serenity 抓取缓存写入：

```text
data/serenity_tweets_cache.jsonl
```

缓存属于运行时数据，不应提交。

### Crypto 预警

运行：

```bash
python crypto_monitor.py
```

运行配置来自 `.env`。预警持久化默认使用 `crypto_monitor.db`，前端 WebSocket 地址在 CI 中通过 `VITE_ALERT_WS_URL` 注入，不要把部署密钥硬编码进 tracked 文件。

## 数据与缓存

- Whop posts cache：`data/posts_cache.jsonl`
- Whop users cache：`data/users_cache.json`
- Serenity tweets cache：`data/serenity_tweets_cache.jsonl`
- Crypto SQLite DB：`crypto_monitor.db`
- 站点构建产物：`docs/.vitepress/dist/`

这些都是运行时或构建产物，除非明确需要，否则不要提交。

## 测试与验证

Python 编译检查：

```bash
python -m py_compile whop_summary.py serenity_summary.py crypto_monitor.py utils/*.py
```

VitePress 构建：

```bash
npm run docs:build
```

当前自动化测试覆盖较少，`python -m unittest discover test -v` 可能没有有效测试用例。涉及发布逻辑时，应至少验证：

- 没有提交 `.env`、`utils/local_secrets.py`、`data/`、数据库或日志。
- VitePress 构建通过。
- 新生成的 markdown 不包含 `<think>` 或 `<thinking>` 标签。

## 贡献与反馈

欢迎提交 Issue 或 PR。修改总结、抓取、发布相关逻辑时，注意该仓库会自动提交并推送 `docs/`，需要确认当前分支、工作树状态和运行时缓存不会污染提交。
