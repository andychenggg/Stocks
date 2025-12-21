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
    posts = sorted(posts.values(), key=lambda p: p.get('createdAt', 0), reverse=True)
    with open(POSTS_CACHE_PATH, 'w', encoding='utf-8') as f:
        for post in posts:
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

def get_history_posts(limit: int, before: Optional[int] = None, is_whole_day: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    获取历史消息（带缓存 + 分页 + 自动去重 + 智能拼接）。
    """
    posts_cache = _load_posts_cache()     # {post_id: post}
    users_cache = _load_users_cache()     # {user_id: username}
    
    logger.info(f"加载帖子缓存 {len(posts_cache)} 条，用户缓存 {len(users_cache)} 条")
    logger.info(f"准备获取历史消息，limit={limit}，before={before}")

    history_items: List[Dict[str, Any]] = []
    seen_ids = set()

    # --- 核心逻辑修复开始 ---
    
    # 判断是否需要强制刷新（即：before为None表示要最新的，必须走API；before为旧时间戳则可先信缓存）
    should_fetch_fresh = (before is None)

    # 1. 如果不是强制刷新最新消息，先尝试从缓存获取
    if not should_fetch_fresh:
        def _match_time_range(post: Dict[str, Any]) -> bool:
            try:
                created = int(post.get('createdAt', 0))
            except Exception:
                return False
            if before is None:
                return True
            return created < before

        cached_posts = [p for p in posts_cache.values() if _match_time_range(p)]
        cached_posts.sort(key=lambda p: int(p.get('createdAt', 0)), reverse=True)
        
        for p in cached_posts:
            if len(history_items) >= limit:
                break
            pid = p.get('id')
            if not pid or pid in seen_ids:
                continue
            history_items.append(p)
            seen_ids.add(pid)
            
        logger.info(f"从缓存中命中 {len(history_items)} 条消息")

    # 2. 循环获取（如果缓存不够，或者强制需要最新数据）
    next_before = before
    
    while len(history_items) < limit:
        
        remaining = limit - len(history_items)
        page_limit = max(min(100, remaining), 50) # 稍微多取一点防止过滤后不够，或者直接用 remaining

        logger.info(f"请求API获取消息，page_limit={page_limit}，next_before={next_before}")

        # --- 构造请求 ---
        try:
            payload = get_payload(page_limit, next_before) 
            resp = requests.request("POST", url, headers=headers, data=payload)
            resp.raise_for_status()
            data = resp.json()['data']['feedPosts']
            user_json = data['users']
            posts_page = data['posts']
        except Exception as e:
            logger.error(f"API请求失败: {e}")
            break

        if not posts_page:
            logger.warning("API未返回更多消息")
            break

        # 更新用户缓存
        for u in user_json:
            uid = u.get('id')
            uname = u.get('username')
            if uid and uname:
                users_cache[uid] = uname

        min_created_this_page: Optional[int] = None
        overlap_found = False # 标记是否撞到了缓存中的旧数据

        for post in posts_page:
            pid = post.get('id')
            if not pid:
                continue

            # --- 检测重合---
            # 如果我们在 API 拿到的数据，本地缓存里已经有了，说明我们“接上”了历史数据
            # 只有在“获取最新”模式下，这个重合检测才最有价值，意味着可以停止 API 请求转而用缓存了
            if should_fetch_fresh and pid in posts_cache:
                overlap_found = True
            posts_cache[pid] = post

            # 解析时间
            try:
                created = int(post.get('createdAt', 0))
            except Exception:
                created = 0

            # 维护翻页游标
            if min_created_this_page is None or created < min_created_this_page:
                min_created_this_page = created

            if before is not None and created >= before:
                continue

            if pid in seen_ids:
                continue

            history_items.append(post)
            seen_ids.add(pid)

            if len(history_items) >= limit:
                break
        
        next_before = min_created_this_page

        # --- 如果已经接上了缓存，且我们需要更多数据，可以直接从缓存补齐 ---
        if overlap_found and len(history_items) < limit and min_created_this_page:
            logger.info(f"检测到数据与缓存重合，尝试从缓存补齐剩余 {limit - len(history_items)} 条")
            
            # 从缓存里找比 next_before 更早的帖子
            cached_rest = [
                p for p in posts_cache.values() 
                if int(p.get('createdAt', 0)) < next_before
            ]
            cached_rest.sort(key=lambda p: int(p.get('createdAt', 0)), reverse=True)
            
            for p in cached_rest:
                if len(history_items) >= limit:
                    break
                pid = p.get('id')
                if pid not in seen_ids:
                    history_items.append(p)
                    seen_ids.add(pid)
            
            # 补齐尝试后，无论够不够，都认为本次获取结束
            break
            
        if min_created_this_page is None:
            break
            
        time.sleep(1) # 稍微防抖

    # 3. 收尾工作
    # 再次排序确保顺序正确（因为混合了 API 和 缓存）
    history_items = sorted(
        history_items,
        key=lambda p: int(p.get('createdAt', 0)),
        reverse=True
    )[:limit]

    _save_posts_cache(posts_cache)
    _save_users_cache(users_cache)

    # 处理整天逻辑
    if is_whole_day:
        current_ms = int(time.time() * 1000)

        last_created = current_ms - 24 * 60 * 60 * 1000
        history_items = [p for p in history_items if int(p.get('createdAt', 0)) >= last_created]
        logger.info(f"过滤整天消息，剩余 {len(history_items)} 条")

    logger.info(f"最终返回消息数量：{len(history_items)}")
    return history_items, users_cache
