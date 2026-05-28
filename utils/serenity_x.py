import html
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

from .local_secrets import serenity_x_config


DATA_DIR = "./data"
TWEETS_CACHE_PATH = os.path.join(DATA_DIR, "serenity_tweets_cache.jsonl")
DEFAULT_PAGE_COUNT = 40

FEATURES = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": False,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

FIELD_TOGGLES = {"withArticlePlainText": False}


def _base_url() -> str:
    return (
        "https://x.com/i/api/graphql/"
        f"{serenity_x_config['operation_id']}/UserTweets"
    )


def _headers() -> Dict[str, str]:
    screen_name = serenity_x_config.get("screen_name", "")
    return {
        "authorization": f"Bearer {serenity_x_config['bearer']}",
        "x-csrf-token": serenity_x_config["ct0"],
        "x-twitter-client-language": "en",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "referer": f"https://x.com/{screen_name}" if screen_name else "https://x.com/",
    }


def _cookies() -> Dict[str, str]:
    return {
        "auth_token": serenity_x_config["auth_token"],
        "ct0": serenity_x_config["ct0"],
    }


def fetch_page(cursor: Optional[str] = None, count: int = DEFAULT_PAGE_COUNT) -> Dict[str, Any]:
    variables = {
        "userId": serenity_x_config["user_id"],
        "count": count,
        "includePromotedContent": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
    }
    if cursor:
        variables["cursor"] = cursor

    params = {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": json.dumps(FEATURES, separators=(",", ":")),
        "fieldToggles": json.dumps(FIELD_TOGGLES, separators=(",", ":")),
    }

    resp = requests.get(_base_url(), headers=_headers(), cookies=_cookies(), params=params)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"X API errors: {data['errors']}")
    return data


def _to_iso(twitter_ts: Optional[str]) -> Optional[str]:
    if not twitter_ts:
        return None
    dt = datetime.strptime(twitter_ts, "%a %b %d %H:%M:%S %z %Y")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tweet_id(tr: Dict[str, Any], legacy: Dict[str, Any]) -> Optional[str]:
    return tr.get("rest_id") or legacy.get("id_str")


def _pick(tr: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not tr:
        return None
    if tr.get("__typename") == "TweetWithVisibilityResults":
        tr = tr.get("tweet", {})

    legacy = tr.get("legacy") or {}
    text = legacy.get("full_text")
    created_at = _to_iso(legacy.get("created_at"))
    if not text or not created_at:
        return None

    return {
        "id": _tweet_id(tr, legacy),
        "user_id": legacy.get("user_id_str"),
        "created_at": created_at,
        "text": html.unescape(text).strip(),
    }


def extract_tweets(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    records: List[Dict[str, Any]] = []
    next_cursor = None

    user_result = data.get("data", {}).get("user", {}).get("result", {})
    timeline = user_result.get("timeline_v2") or user_result.get("timeline")
    if not timeline:
        return records, None

    for ins in timeline.get("timeline", {}).get("instructions", []):
        itype = ins.get("type")

        if itype == "TimelinePinEntry":
            tr = (
                ins.get("entry", {})
                .get("content", {})
                .get("itemContent", {})
                .get("tweet_results", {})
                .get("result")
            )
            record = _pick(tr)
            if record:
                records.append(record)
            continue

        if itype != "TimelineAddEntries":
            continue

        for entry in ins.get("entries", []):
            eid = entry.get("entryId", "")
            content = entry.get("content", {})
            etype = content.get("entryType")

            if etype == "TimelineTimelineItem" or eid.startswith("tweet-"):
                tr = content.get("itemContent", {}).get("tweet_results", {}).get("result")
                record = _pick(tr)
                if record:
                    records.append(record)
            elif etype == "TimelineTimelineModule" or eid.startswith(
                ("profile-conversation-", "home-conversation-")
            ):
                for item in content.get("items", []):
                    tr = (
                        item.get("item", {})
                        .get("itemContent", {})
                        .get("tweet_results", {})
                        .get("result")
                    )
                    record = _pick(tr)
                    if record:
                        records.append(record)
            elif eid.startswith("cursor-bottom") or content.get("cursorType") == "Bottom":
                next_cursor = content.get("value")

    return records, next_cursor


def _record_key(record: Dict[str, Any]) -> str:
    return record.get("id") or f"{record.get('created_at', '')}:{record.get('text', '')}"


def load_tweets_cache(path: str = TWEETS_CACHE_PATH) -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(path):
        return records

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records[_record_key(record)] = record
    return records


def save_tweets_cache(records: Dict[str, Dict[str, Any]], path: str = TWEETS_CACHE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sorted_records = sorted(records.values(), key=lambda r: r.get("created_at", ""), reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in sorted_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def crawl_latest_pages(max_pages: int = 5, sleep_sec: float = 1.5) -> List[Dict[str, Any]]:
    all_records: List[Dict[str, Any]] = []
    seen_cursors = set()
    cursor = None

    for page in range(1, max_pages + 1):
        logger.info(f"抓取 Serenity X 第 {page} 页")
        data = fetch_page(cursor=cursor, count=DEFAULT_PAGE_COUNT)
        records, cursor = extract_tweets(data)
        all_records.extend(records)
        logger.info(f"本页获取 {len(records)} 条，累计 {len(all_records)} 条")

        if not records or not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)
        time.sleep(sleep_sec)

    return all_records


def update_tweets_cache(max_pages: int = 5) -> List[Dict[str, Any]]:
    cached = load_tweets_cache()
    fetched = crawl_latest_pages(max_pages=max_pages)
    for record in fetched:
        cached[_record_key(record)] = record
    save_tweets_cache(cached)
    return sorted(cached.values(), key=lambda r: r.get("created_at", ""), reverse=True)


def parse_iso_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def recent_tweets(records: List[Dict[str, Any]], hours: int = 24) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = []
    for record in records:
        created_at = record.get("created_at")
        if not created_at:
            continue
        try:
            if parse_iso_utc(created_at) >= cutoff:
                recent.append(record)
        except ValueError:
            continue
    return sorted(recent, key=lambda r: r.get("created_at", ""))


def tweets_to_text(records: List[Dict[str, Any]]) -> str:
    lines = []
    screen_name = serenity_x_config.get("screen_name") or "serenity"
    for record in records:
        lines.append(
            f"{record.get('created_at', '')} @{screen_name}: "
            f"{(record.get('text') or '').strip()}"
        )
    return "\n\n".join(lines)
