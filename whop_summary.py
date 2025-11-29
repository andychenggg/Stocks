import datetime
import pytz
import os
from loguru import logger
from utils import history_list_to_text, summary_prompt, get_response, get_history_posts, save_to_md, get_summary_config, hours_from_open, hours_from_close
def summary_run(summary_limit: int = 300, is_whole_day: bool = False, description: str = ""):
    """
    生成并保存总结
    
    参数：
        summary_limit: 获取消息条数
        is_whole_day: 是否只获取过去24小时的消息
    """
    history_items, username_dict = get_history_posts(summary_limit, is_whole_day=is_whole_day)
    big_text = history_list_to_text(history_items, username_dict)
    to_summary_text = summary_prompt + big_text
    model = "gemini-2.5-pro"
    summary = get_response(to_summary_text, model=model)

    save_to_md(
        summary=summary,
        description=description,
        model=model,
        output_dir="docs",
    )
    
    now_pst = datetime.datetime.now(pytz.UTC).astimezone(pytz.timezone('America/Los_Angeles'))
    # Git 推送
    os.system(f'cd . && git add docs/ && git commit -m "Auto update: ' + now_pst.strftime("%Y-%m-%d %H:%M:%S PST") + '" && git push origin master')


if __name__ == "__main__":
    
    hours_open = hours_from_open()
    hours_close = hours_from_close()
    
    # 判断是否应该执行
    if 0 <= hours_close < 1:
        # 收盘总结
        pass
    elif -1 <= hours_open < 7 and hours_close < 1:
        # 盘前/盘中总结
        pass
    else:
        # 休市，检查是否是美东9点
        now_et = datetime.datetime.now(pytz.timezone('America/New_York'))
        logger.info(f"当前美东时间小时：{now_et.hour}")
        if now_et.hour != 9:
            exit(0)
    
    limit, is_whole_day, description = get_summary_config()
    summary_run(summary_limit=limit, is_whole_day=is_whole_day, description=description)
