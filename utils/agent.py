from datetime import datetime
import os
from typing import Optional
from openai import OpenAI
from loguru import logger
import pytz
from .secrets import openai_api_key, openai_base_url
client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_base_url
)

def get_response(to_summary_text: str, model: str = "gemini-2.5-pro") -> str:
    logger.info(f"正在使用模型 {model} 生成总结...")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": to_summary_text}
        ]
    )
    logger.info("模型生成总结完成。")
    return response.choices[0].message.content

def save_to_md(
    summary: str,
    model: str,
    output_dir: str = "docs",
) -> str:
    # 获取当前时间
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    datetime_str = now.strftime("%Y-%m-%d %H:%M:%S")

    now_utc = datetime.datetime.now(pytz.UTC)
    now_pst = now_utc.astimezone(pytz.timezone('America/Los_Angeles'))  # 美西时间
    now_est = now_utc.astimezone(pytz.timezone('America/New_York'))     # 美东时间
    now_cst = now_utc.astimezone(pytz.timezone('Asia/Shanghai'))        # 北京时间
    readme_content = f"""# 财经社区聊天记录总结

    > 北京时间：{now_cst.strftime("%Y-%m-%d %H:%M:%S CST")}

    > 美西时间：{now_pst.strftime("%Y-%m-%d %H:%M:%S PST")}

    > 美东时间：{now_est.strftime("%Y-%m-%d %H:%M:%S EST")}
    > 模型：{model}

    {summary}

    [查看历史总结](/summaries/)
    """

    summary_dir = os.path.join(output_dir, "summaries")
    os.makedirs(summary_dir, exist_ok=True)
    with open(f'{output_dir}/index.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)

    datetime_str = now_pst.strftime("%Y-%m-%d %H:%M:%S")
    with open(f'{summary_dir}/{datetime_str}.md', 'w', encoding='utf-8') as f:
        f.write(f"# {now_pst.strftime('%Y-%m-%d %H:%M:%S PST')} 总结\n\n> 美西时间：{now_pst.strftime('%Y-%m-%d %H:%M:%S PST')}\n\n> 美东时间：{now_est.strftime('%Y-%m-%d %H:%M:%S EST')}\n\n{summary}")

