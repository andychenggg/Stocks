
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

def format_timestamp(ts_ms: str | int) -> str:
    """
    把毫秒时间戳转成可读时间字符串，例如：2025-11-26 12:34:56
    """
    ts_ms_int = int(ts_ms)
    dt = datetime.fromtimestamp(ts_ms_int / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_user_name(post: Dict[str, Any], username_dict: Dict[str, str]) -> str:
    """
    优先用 post['user']['name']，没有的话退回 userId。
    """
    user = post.get("user")
    if isinstance(user, dict):
        return user.get("name") or user.get("username") or username_dict.get(post.get("userId"), "未知用户")
    return username_dict.get(post.get("userId"), "未知用户")


def get_reply_target(post: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """
    从 replyingToPost 里取一个“回复对象”的描述。
    优先用原帖用户名字，其次内容（可按需截断）。
    """
    replying = post.get("replyingToPost")
    if not replying:
        return None, ""

    # 先尝试用户名
    user = replying.get("user")
    content = replying.get("content") or ""
    contetn = content.strip()
    content = content[:25] + "..." if len(content) > 25 else content
    if isinstance(user, dict):
        name = user.get("name") or user.get("username")
        if name:
            return name, content
    return None, content


def history_list_to_text(items: List[Dict[str, Any]], username_dict: Dict[str, str]) -> str:
    """
    把一整个 history list 转成一大段文本，供 LLM 做 summaries 使用。
    每条格式：时间 [管理员]姓名 说(回复xxx): 内容
    """
    # 尽量按时间排序
    items_sorted = sorted(
        items,
        key=lambda x: int(x.get("createdAt", 0))
    )

    lines: List[str] = []

    for post in items_sorted:
        # 时间
        time_str = format_timestamp(post["createdAt"])

        # 是否管理员
        is_admin = post.get("isPosterAdmin", False)
        admin_tag = "[管理员]" if is_admin else ""

        # 发言人
        name = get_user_name(post, username_dict)

        # 回复对象
        reply_target, content_preview = get_reply_target(post)
        if reply_target:
            reply_part = f"(回复{reply_target}之前的发言: {content_preview})"
        else:
            reply_part = ""

        # 内容
        content = (post.get("content") or "").strip()

        # 最终一行
        # 示例：2025-11-26 12:34:56 [管理员]阿佳 (回复赵哥之前的发言: 内容预览)说: 下周大
        line = f"{time_str} {admin_tag}{name} {reply_part}说: {content}"
        lines.append(line)

    # 用换行拼起来
    return "\n".join(lines)