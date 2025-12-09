import datetime
import os
from typing import Optional
from openai import OpenAI
from google import genai
from loguru import logger
import pytz
from .local_secrets import model_key
# client = OpenAI(
#     api_key=openai_api_key,
#     base_url=openai_base_url
# )

# client = genai.Client(api_key=openai_api_key)   


def get_response(to_summary_text: str, model: str = "gemini-2.5-pro") -> str:
    logger.info(f"正在使用模型 {model} 生成总结...")
    selected_config = next((item for item in model_key if item['model'] == model), None)
    app = selected_config['app']
    client = None
    
    if app == "openai":
        client = OpenAI(
            api_key=selected_config['key'],
            base_url=selected_config['base_url']
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": to_summary_text}
            ]
        )
        response = response.choices[0].message.content
    elif app == "google":
        client = genai.Client(api_key=selected_config['key'])
    
        response = client.models.generate_content(
            model=model, contents=to_summary_text
        )
        response = response.text
    logger.info("模型生成总结完成。")
    return response

def save_to_md(
    summary: str,
    description: str,
    model: str,
    title: Optional[str] = None,
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
    readme_content = f"""# 财经聊天总结 - {description}

    > 北京时间：{now_cst.strftime("%Y-%m-%d %H:%M:%S CST")}

    > 美西时间：{now_pst.strftime("%Y-%m-%d %H:%M:%S PST")}

    > 美东时间：{now_est.strftime("%Y-%m-%d %H:%M:%S EST")}

    > 模型：{model}

代码仓库：[GitHub - finance-community-summary](https://github.com/andychenggg/Stocks) 可以star一下，方便后续获取更新内容！有问题欢迎提 issue。

{summary}

    [查看历史总结](/summaries/)
    """

    summary_dir = os.path.join(output_dir, "summaries")
    os.makedirs(summary_dir, exist_ok=True)
    with open(f'{output_dir}/index.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)

    datetime_str = now_cst.strftime("%Y-%m-%d %H:%M:%S")
    if title is None:
        with open(f'{summary_dir}/{datetime_str}.md', 'w', encoding='utf-8') as f:
            f.write(f"# {now_cst.strftime('%Y-%m-%d %H:%M:%S CST')} 总结 - {description}\n\n> 美西时间：{now_pst.strftime('%Y-%m-%d %H:%M:%S PST')}\n\n> 美东时间：{now_est.strftime('%Y-%m-%d %H:%M:%S EST')}\n\n{summary}")
    else:
        with open(f'{summary_dir}/{datetime_str}-{title}.md', 'w', encoding='utf-8') as f:
            f.write(f"# {now_cst.strftime('%Y-%m-%d %H:%M:%S CST')} 总结 - {description}\n\n> 美西时间：{now_pst.strftime('%Y-%m-%d %H:%M:%S PST')}\n\n> 美东时间：{now_est.strftime('%Y-%m-%d %H:%M:%S EST')}\n\n{summary}")
