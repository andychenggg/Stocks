# Repository Guidelines

## Project Overview
This repository is a mixed system with two production-facing workflows:

- Whop chat ingestion, LLM summarization, and static site publishing for finance community discussions.
- Real-time Binance crypto monitoring, alert persistence, and downstream WebSocket/HTTP serving.

Do not treat this repo as a single script. It combines content generation, scheduled publishing, static site deployment, and a live market alert service.

## Core Runtime Map

### Whop Summary Pipeline
- `whop_summary.py` is the main scheduled entrypoint for summary generation.
- It decides which summary mode to run based on U.S. market timing from `utils/market_date.py`.
- It fetches Whop messages via `utils/message_utils.py`.
- It converts chat history into promptable text with `utils/parse_utils.py`.
- It calls LLMs and writes markdown output through `utils/agent.py`.
- It writes the latest landing content to `docs/index.md`, appends history files under `docs/summaries/`, and then runs `git add docs/ && git commit && git push origin master`.

### Summary Support Modules
- `utils/message_utils.py` owns the Whop GraphQL request, pagination, local cache usage, post de-duplication, and username cache updates.
- `utils/market_date.py` uses the NASDAQ calendar to decide market-open state and choose summary modes such as pre-market, intraday, after-close, and off-hours.
- `utils/agent.py` owns model selection from `utils/local_secrets.py`, OpenAI/Google client dispatch, retry behavior, markdown sanitization, and markdown file output.
- `utils/prompt.py` contains the long-form prompts for summary and trading-experience extraction. Do not duplicate those prompts into agent docs unless needed for a task.

### Crypto Alert Pipeline
- `crypto_monitor.py` is the main runtime entrypoint for Binance monitoring.
- It loads runtime configuration from `.env`, initializes SQLite storage, starts retention cleanup, starts the client WebSocket server, starts the HTTP server, and then connects to Binance combined streams unless stub mode is enabled.
- `utils/crypt/market.py` maintains in-memory price state, rolling windows, daily open tracking by timezone, and alert emission logic.
- `utils/crypt/db.py` persists klines, rolling window stats, and alerts into SQLite, and exposes recent alert reads for downstream consumers.
- `utils/crypt/ws.py` manages outbound WebSocket clients and Binance stream consumption.
- `utils/crypt/http_server.py` exposes a lightweight HTTP endpoint for recent alerts.

## Site, Deployment, and Outputs
- The static site lives under `docs/` and is built with VitePress.
- VitePress config is in `docs/.vitepress/config.mts`.
- Historical summaries are generated into `docs/summaries/`.
- The latest summary landing page is regenerated into `docs/index.md`.
- `docs/summaries/` is high-churn generated output. Be careful when changing naming, write location, landing-page overwrite behavior, or summary cadence.
- GitHub Pages deployment is driven by `.github/workflows/deploy.yml`.
- The workflow triggers on pushes to `master` when `docs/**` changes.
- The front-end alert WebSocket URL is injected in CI via `VITE_ALERT_WS_URL`; do not hardcode deployment secrets into tracked files.

## Configuration and Secrets
- Local secrets for Whop headers and model credentials live in `utils/local_secrets.py`.
- Runtime environment for crypto monitoring lives in `.env`.
- Never commit real secrets from `.env` or `utils/local_secrets.py`.
- When discussing configuration, refer to categories of settings, not secret values.

## Local Commands
- Install Python deps with `pip install -r requirements.txt`.
- Install site deps with `npm ci`.
- Run the docs site locally with `npm run docs:dev`.
- Build the docs site with `npm run docs:build`.
- Run scheduled summary generation manually with `python whop_summary.py`.
- The existing scheduler wrapper is `sh/run.sh`.
- Run crypto monitoring with `python crypto_monitor.py`.

## Data and Runtime Artifacts
- Whop message caches live in `data/posts_cache.jsonl` and `data/users_cache.json`.
- Crypto alert persistence currently uses `crypto_monitor.db`.
- Generated site output and history live in `docs/`.
- Treat caches, databases, and generated markdown as runtime artifacts unless a task explicitly targets them.

## Collaboration Constraints
- The worktree may already be dirty. Do not revert unrelated user changes.
- At the time this context was established, local modifications existed in `.env`, `utils/agent.py`, and `whop_summary.py`, with additional untracked files such as `.vscode/`, `first_week_returns_last20y.csv`, `first_week_windows_last20y.csv`, and `test.py`.
- `whop_summary.py` performs direct Git mutations. Any change around summary generation must account for dirty-worktree behavior, branch assumptions, and auto-commit side effects.
- `utils/agent.py` already strips `<think>` and `<thinking>` tags before writing markdown because those can break VitePress/Vue compilation. Preserve that behavior unless a task explicitly replaces it.
- Current automated test coverage is minimal. `python -m unittest discover test -v` currently reports `Ran 0 tests`.

## Working Assumptions For Future Tasks
- Use `AGENTS.md` as the persistent repository context file. `agent.md` is not the canonical filename here.
- Default scope for future work includes both the summary pipeline and the crypto alert pipeline unless the task explicitly narrows scope.
- Prefer reading actual module code before making architectural claims because the repository mixes generated content, deployment assets, runtime caches, and hand-written application code.
