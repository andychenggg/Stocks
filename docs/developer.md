# 开发者文档

本文面向二次开发与部署工程师，描述当前 Django + Channels + Postgres 的重构后结构与运行方式。

## 目录结构

- `config/`：Django 配置与 ASGI 入口
- `apps/crypts/`：加密行情监控逻辑（WebSocket、Binance 监听、告警）
- `apps/health/`：健康检查接口
- `sql/create-database-01-crypt.sql`：Postgres 建表 SQL（含 IF NOT EXISTS）
- `requirements/crypt.requirement.txt`：Python 依赖
- `.env`：运行时环境变量（参考 `.env.example`）

## 依赖安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/crypt.requirement.txt
```

## 数据库

### Postgres 连接

`.env` 至少需要如下配置：

```bash
DB_ENGINE=django.db.backends.postgresql
DB_NAME=crypto_monitor
DB_USER=crypto_monitor
DB_PASSWORD=change-me
DB_HOST=127.0.0.1
DB_PORT=5432
```

### 建表

手动执行 SQL：

```bash
psql -d crypto_monitor -f sql/create-database-01-crypt.sql
```

如需在应用启动时自动应用 SQL，可设置：

```bash
CRYPTO_SCHEMA_AUTO_CREATE=true
```

## 运行方式

### 推荐：Daphne（支持 WebSocket）

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

### 监控任务自动启动

在 `.env` 中启用：

```bash
CRYPTO_MONITOR_AUTOSTART=true
```

默认情况下，监控任务会在第一个 WebSocket 客户端连接时启动（`/ws/crypt/`）。

## WebSocket

- 入口：`ws://<host>:8000/ws/crypt/`
- 首次连接返回：
  - `type: "snapshot"`：当前价格快照 + 近期告警
- 后续推送：
  - `type: "price"`：价格与涨跌信息
  - `type: "alert"`：告警事件

## 健康检查

- `GET /health/db/`：检查 `klines`、`window_stats`、`alerts` 是否存在

## 可选：Redis Channel Layer

多进程/多实例时建议使用 Redis：

```bash
CHANNEL_LAYER_BACKEND=channels_redis.core.RedisChannelLayer
REDIS_URL=redis://127.0.0.1:6379/0
```

并安装依赖：

```bash
pip install channels-redis
```

## 运行参数（常用）

```bash
CRYPTO_SYMBOLS=btcusdt,ethusdt
BINANCE_STREAM_URL=wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/ethusdt@kline_1m/btcusdt@miniTicker/ethusdt@miniTicker
WINDOW_SIZE_MINUTES=5
ALERT_THRESHOLDS=0.01,0.005
ALERT_DEDUP_SECONDS=180
RETENTION_SECONDS=86400
RECENT_ALERT_LIMIT=50
STUB_MODE=false
```
