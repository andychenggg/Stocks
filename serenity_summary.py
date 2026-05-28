import datetime
import html
import os
import subprocess
from typing import Any, Dict, List, Optional

import pytz
from loguru import logger

from utils import get_response, serenity_summary_prompt
from utils.agent import _sanitize_summary_markdown
from utils.serenity_x import parse_iso_utc, recent_tweets, tweets_to_text, update_tweets_cache


MODEL = "deepseek-v4-flash"
OUTPUT_DIR = "docs"
SERENITY_HISTORY_DIR = os.path.join(OUTPUT_DIR, "serenity-summaries")
SUMMARY_WINDOW_HOURS = 24
CRAWL_MAX_PAGES = 5


def _time_context() -> dict:
    now_utc = datetime.datetime.now(pytz.UTC)
    return {
        "utc": now_utc,
        "pst": now_utc.astimezone(pytz.timezone("America/Los_Angeles")),
        "est": now_utc.astimezone(pytz.timezone("America/New_York")),
        "cst": now_utc.astimezone(pytz.timezone("Asia/Shanghai")),
    }


def _tweet_time_context(created_at: str) -> dict:
    dt_utc = parse_iso_utc(created_at)
    return {
        "pst": dt_utc.astimezone(pytz.timezone("America/Los_Angeles")),
        "est": dt_utc.astimezone(pytz.timezone("America/New_York")),
        "cst": dt_utc.astimezone(pytz.timezone("Asia/Shanghai")),
    }


def _render_tweet_time(created_at: str) -> str:
    if not created_at:
        return ""
    try:
        times = _tweet_time_context(created_at)
    except ValueError:
        return html.escape(created_at)

    return (
        f"北京时间：{times['cst'].strftime('%Y-%m-%d %H:%M:%S CST')}"
        f"<br>美西时间：{times['pst'].strftime('%Y-%m-%d %H:%M:%S PST')}"
        f"<br>美东时间：{times['est'].strftime('%Y-%m-%d %H:%M:%S EST')}"
    )


def _render_original_tweets(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "- 过去 24 小时未抓取到新的 X 发帖。\n"

    lines = []
    for idx, record in enumerate(records, start=1):
        timestamp = _render_tweet_time(record.get("created_at") or "")
        text = html.escape((record.get("text") or "").strip())
        text = text.replace("\n", "<br>")
        lines.append(
            f'<article class="serenity-tweet">'
            f'<div class="serenity-tweet-index">#{idx}</div>'
            f'<div class="serenity-tweet-time">{timestamp}</div>'
            f'<div class="serenity-tweet-text">{text}</div>'
            f"</article>"
        )
    return "\n\n".join(lines) + "\n"


def _render_summary_page(
    summary: str,
    model: str,
    records: List[Dict[str, Any]],
    times: Optional[dict] = None,
) -> str:
    times = times or _time_context()
    summary = _sanitize_summary_markdown(summary)
    tweet_count = len(records)
    original_tweets = _render_original_tweets(records)
    return f"""# Serenity 总结

> 北京时间：{times["cst"].strftime("%Y-%m-%d %H:%M:%S CST")}

> 美西时间：{times["pst"].strftime("%Y-%m-%d %H:%M:%S PST")}

> 美东时间：{times["est"].strftime("%Y-%m-%d %H:%M:%S EST")}

> 模型：{model}

> 覆盖范围：过去 {SUMMARY_WINDOW_HOURS} 小时，抓取到 {tweet_count} 条 X 发帖

代码仓库：[GitHub - finance-community-summary](https://github.com/andychenggg/Stocks) 可以 star 一下，方便后续获取更新内容！有问题欢迎提 issue。

## 原文记录

{original_tweets}

## AI 总结

{summary}
"""


def save_serenity_summary(summary: str, model: str, records: List[Dict[str, Any]]) -> str:
    os.makedirs(SERENITY_HISTORY_DIR, exist_ok=True)

    content = _render_summary_page(summary, model, records)
    now_cst = _time_context()["cst"]
    history_name = f"{now_cst.strftime('%Y-%m-%d %H:%M:%S')}-serenity总结.md"
    history_path = os.path.join(SERENITY_HISTORY_DIR, history_name)
    with open(history_path, "w", encoding="utf-8") as f:
        f.write(content)

    history_index = os.path.join(SERENITY_HISTORY_DIR, "index.md")
    with open(history_index, "w", encoding="utf-8") as f:
        f.write("# Serenity 历史总结\n\n这里是 Serenity X 总结的历史列表，请从侧边栏选择具体日期查看。\n")

    return history_path


def build_summary_text() -> tuple[str, List[Dict[str, Any]]]:
    all_records = update_tweets_cache(max_pages=CRAWL_MAX_PAGES)
    records = recent_tweets(all_records, hours=SUMMARY_WINDOW_HOURS)
    logger.info(f"过去 {SUMMARY_WINDOW_HOURS} 小时内 Serenity X 发帖 {len(records)} 条")

    if not records:
        return (
            "## 核心总结\n"
            f"- 过去 {SUMMARY_WINDOW_HOURS} 小时未抓取到新的 X 发帖。\n\n"
            "## 涉及标的与方向\n"
            "- 暂无。\n\n"
            "## 催化剂与时间线\n"
            "- 暂无。\n\n"
            "## 风险与不确定性\n"
            "- 暂无。\n\n"
            "## 后续可跟踪事项\n"
            "- 等待下一次更新。",
            records,
        )

    prompt = serenity_summary_prompt + tweets_to_text(records)
    return get_response(prompt, model=MODEL), records


def publish_docs(paths: Optional[List[str]] = None) -> None:
    now_pst = _time_context()["pst"]
    message = f"Auto update serenity: {now_pst.strftime('%Y-%m-%d %H:%M:%S PST')}"

    subprocess.run(["git", "add", "docs/"], check=True)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        logger.info("docs/ 没有变更，跳过 commit 和 push")
        return

    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push", "origin", "master"], check=True)


def summary_run(publish: bool = True) -> None:
    summary, records = build_summary_text()
    history_path = save_serenity_summary(summary, MODEL, records)
    logger.info(f"Serenity 总结已保存：{history_path}")

    if publish:
        publish_docs()


if __name__ == "__main__":
    summary_run()
