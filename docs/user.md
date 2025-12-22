# 用户文档

本项目提供加密行情实时监控与告警推送能力，通过 WebSocket 输出价格与告警信息。

## 快速开始

1. 配置 `.env`（参考 `.env.example`）
2. 初始化数据库（Postgres）
3. 使用 Daphne 启动服务
4. 连接 WebSocket 接收行情与告警

## 必需配置

`.env` 需要包含以下数据库配置：

```bash
DB_ENGINE=django.db.backends.postgresql
DB_NAME=crypto_monitor
DB_USER=crypto_monitor
DB_PASSWORD=change-me
DB_HOST=127.0.0.1
DB_PORT=5432
```

## 数据库建表

执行 SQL：

```bash
psql -d crypto_monitor -f sql/create-database-01-crypt.sql
```

也可以在 `.env` 中开启自动建表：

```bash
CRYPTO_SCHEMA_AUTO_CREATE=true
```

## 启动服务

推荐使用 Daphne（支持 WebSocket）：

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

如果需要自动启动行情监控任务：

```bash
CRYPTO_MONITOR_AUTOSTART=true
```

## WebSocket 使用

- 连接地址：`ws://<host>:8000/ws/crypt/`
- 初次连接返回 `snapshot`（快照+告警）
- 后续持续推送 `price` / `alert`

## 健康检查

- 接口：`GET /health/db/`
- 若 `missing` 为空表示建表完成
