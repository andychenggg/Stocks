import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import requests
from loguru import logger
from .local_secrets import whom_headers as headers

url = "https://whop.com/api/graphql/MessagesFetchFeedPosts/"

data_dir = './data'
os.makedirs(data_dir, exist_ok=True)
POSTS_CACHE_PATH = os.path.join(data_dir, 'posts_cache.jsonl')
USERS_CACHE_PATH = os.path.join(data_dir, 'users_cache.json')

def _load_posts_cache() -> Dict[str, Dict[str, Any]]:
    """加载帖子缓存，返回 {post_id: post_dict}"""
    posts: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(POSTS_CACHE_PATH):
        return posts

    with open(POSTS_CACHE_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                post = json.loads(line)
                pid = post.get('id')
                if pid:
                    posts[pid] = post
            except Exception:
                continue
    return posts
def _save_posts_cache(posts: Dict[str, Dict[str, Any]]) -> None:
    """整体写回帖子缓存（简单粗暴一点，量不大没关系）"""
    with open(POSTS_CACHE_PATH, 'w', encoding='utf-8') as f:
        for post in posts.values():
            f.write(json.dumps(post, ensure_ascii=False) + '\n')
            
def _load_users_cache() -> Dict[str, str]:
    """加载用户缓存，返回 {user_id: username}"""
    if not os.path.exists(USERS_CACHE_PATH):
        return {}
    try:
        with open(USERS_CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_users_cache(users: Dict[str, str]) -> None:
    """保存用户缓存"""
    with open(USERS_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
        
def get_payload(limit: int, before: int = None) -> str:
    before_str = "null" if before is None else str(before)
    return "{\"query\":\"query MessagesFetchFeedPosts($feedType: FeedTypes!, $after: BigInt, $before: BigInt, $aroundId: ID, $feedId: ID!, $includeDeleted: Boolean, $includeReactions: Boolean, $limit: Int, $direction: Direction) {\\n  feedPosts(\\n    feedType: $feedType\\n    after: $after\\n    before: $before\\n    aroundId: $aroundId\\n    feedId: $feedId\\n    includeDeleted: $includeDeleted\\n    includeReactions: $includeReactions\\n    limit: $limit\\n    direction: $direction\\n  ) {\\n    posts {\\n      __typename\\n      ...DmsPostFragment\\n    }\\n    users {\\n      ...BasicUserProfileDetails\\n    }\\n    reactions {\\n      ...ReactionFragment\\n    }\\n  }\\n}\\n\\nfragment DmsPostFragment on DmsPost {\\n  id\\n  createdAt\\n  updatedAt\\n  isDeleted\\n  sortKey\\n  isPosterAdmin\\n  mentionedUserIds\\n  content\\n  feedId\\n  feedType\\n  attachments {\\n    ...Attachment\\n  }\\n  gifs {\\n    height\\n    provider\\n    originalUrl\\n    previewUrl\\n    provider\\n    slug\\n    title\\n    width\\n  }\\n  isEdited\\n  isEveryoneMentioned\\n  isPinned\\n  linkEmbeds {\\n    description\\n    favicon\\n    image\\n    processing\\n    title\\n    url\\n    footer {\\n      title\\n      description\\n      icon\\n    }\\n  }\\n  richContent\\n  userId\\n  viewCount\\n  reactionCounts {\\n    reactionType\\n    userCount\\n    value\\n  }\\n  messageType\\n  embed\\n  replyingToPostId\\n  replyingToPost {\\n    id\\n    richContent\\n    content\\n    gifs {\\n      __typename\\n    }\\n    isDeleted\\n    linkEmbeds {\\n      __typename\\n    }\\n    mentionedUserIds\\n    isEveryoneMentioned\\n    messageType\\n    attachments {\\n      contentType\\n    }\\n    user {\\n      id\\n      name\\n      username\\n      roles\\n      profilePicSm: profileImageSrcset(style: s32) {\\n        double\\n      }\\n    }\\n  }\\n  poll {\\n    options {\\n      id\\n      text\\n    }\\n  }\\n  customAuthor {\\n    displayName\\n    profilePicture {\\n      sourceUrl\\n    }\\n  }\\n}\\n\\nfragment Attachment on AttachmentInterface {\\n  __typename\\n  id\\n  signedId\\n  analyzed\\n  byteSizeV2\\n  filename\\n  contentType\\n  source(variant: original) {\\n    url\\n  }\\n  ... on ImageAttachment {\\n    height\\n    width\\n    blurhash\\n    aspectRatio\\n  }\\n  ... on VideoAttachment {\\n    height\\n    width\\n    duration\\n    aspectRatio\\n    preview(variant: original) {\\n      url\\n    }\\n  }\\n  ... on AudioAttachment {\\n    duration\\n    waveformUrl\\n  }\\n}\\n\\nfragment BasicUserProfileDetails on PublicProfileUser {\\n  id\\n  name\\n  createdAt\\n  bannerImageLg: bannerImageSrcset(style: s600x200) {\\n    double\\n  }\\n  profilePicLg: profileImageSrcset(style: s128) {\\n    double\\n  }\\n  profilePicSm: profileImageSrcset(style: s32) {\\n    double\\n  }\\n  username\\n  createdAt\\n  roles\\n  lastSeenAt\\n  isPlatformPolice\\n}\\n\\nfragment ReactionFragment on Reaction {\\n  id\\n  isDeleted\\n  createdAt\\n  updatedAt\\n  feedId\\n  feedType\\n  postId\\n  postType\\n  userId\\n  reactionType\\n  score\\n  value\\n}\",\"variables\":{\"feedId\":\"chat_feed_1CTr5VAdNHtbZAFaTitvoT\",\"feedType\":\"chat_feed\"," + \
        "\"limit\":"+ str(limit) + ",\"before\":"+ before_str + ",\"direction\":\"desc\",\"includeDeleted\":false}}"

def get_history_posts(limit: int, before: Optional[int] = None) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    获取历史消息（带缓存 + 分页）。

    参数：
      limit: 想要的消息条数
      before: 毫秒时间戳
        - None: 表示“从现在往回翻最新的 limit 条”
        - 非 None: 表示“获取 before 之前的 limit 条”

    返回：
      (history_items, username_dict)
        history_items: 按 createdAt 降序排列的帖子列表
        username_dict: {user_id: username}
    """
    posts_cache = _load_posts_cache()     # {post_id: post}
    users_cache = _load_users_cache()     # {user_id: username}
    logger.info(f"加载帖子缓存 {len(posts_cache)} 条，用户缓存 {len(users_cache)} 条")
    logger.info(f"准备获取历史消息，limit={limit}，before={before}")
    def _match_time_range(post: Dict[str, Any]) -> bool:
        """是否满足当前 before 条件"""
        try:
            created = int(post.get('createdAt', 0))
        except Exception:
            return False
        if before is None:
            return True
        return created < before

    # 先从缓存里查符合时间条件的
    cached_posts = [p for p in posts_cache.values() if _match_time_range(p)]
    cached_posts.sort(key=lambda p: int(p.get('createdAt', 0)), reverse=True)
    logger.info(f"缓存中符合时间条件的帖子数量：{len(cached_posts)}")
    history_items: List[Dict[str, Any]] = []
    seen_ids = set()

    for p in cached_posts:
        if len(history_items) >= limit:
            break
        pid = p.get('id')
        if not pid or pid in seen_ids:
            continue
        history_items.append(p)
        seen_ids.add(pid)

    need_remote = len(history_items) < limit

    # 用于分页请求的 before 游标：
    # - 第一页：用用户传入的 before（可能是 None）
    next_before = before

    while need_remote:
        remaining = limit - len(history_items)
        if remaining <= 0:
            break

        page_limit = min(100, remaining)
        logger.info(f"请求网站获取更多历史消息，page_limit={page_limit}，next_before={next_before}")
        # 构造 payload（你已有 get_payload / url / headers）
        # 当 next_before=None 时，API 会返回“最新的 page_limit 条”
        payload = get_payload(page_limit, next_before)
        resp = requests.request("POST", url, headers=headers, data=payload)
        resp.raise_for_status()
        data = resp.json()['data']['feedPosts']

        user_json = data['users']
        posts_page = data['posts']

        if not posts_page:
            logger.warning("请求网站未获取到更多历史消息，结束翻页")
            break

        for u in user_json:
            uid = u.get('id')
            uname = u.get('username')
            if uid and uname:
                users_cache[uid] = uname

        min_created_this_page: Optional[int] = None

        for post in posts_page:
            pid = post.get('id')
            if not pid:
                continue

            # 放入缓存（覆盖旧的）
            posts_cache[pid] = post

            try:
                created = int(post.get('createdAt', 0))
            except Exception:
                created = 0

            # 记录本页最早的 createdAt，用于下一页 before
            if min_created_this_page is None or created < min_created_this_page:
                min_created_this_page = created

            # 和缓存数据一样，统一用 _match_time_range 判时间范围
            if not _match_time_range(post):
                continue

            if pid in seen_ids:
                continue

            history_items.append(post)
            seen_ids.add(pid)

        # 更新下一页的 before 游标：继续往更早时间翻
        if min_created_this_page is None:
            logger.warning("本页未获取到有效的 createdAt，结束翻页")
            break
        next_before = min_created_this_page

        # 数量够了就结束，否则继续翻页
        if len(history_items) >= limit:
            logger.info(f"已获取到足够的历史消息，数量={len(history_items)}，结束翻页")
            break

        time.sleep(2)

    # 最终按时间从新到旧排序，并截断到 limit 条
    history_items = sorted(
        history_items,
        key=lambda p: int(p.get('createdAt', 0)),
        reverse=True
    )[:limit]

    _save_posts_cache(posts_cache)
    _save_users_cache(users_cache)

    return history_items, users_cache
