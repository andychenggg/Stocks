import datetime
import pytz
import os
from utils import history_list_to_text, summary_prompt, get_response, get_history_posts, save_to_md

# 生成总结
history_items, username_dict = get_history_posts(320)
big_text = history_list_to_text(history_items, username_dict)
to_summary_text = summary_prompt + big_text
model = "gemini-2.5-pro"
summary = get_response(to_summary_text, model=model)

save_to_md(
    summary=summary,
    model=model,
    output_dir="docs",
)
now_pst = datetime.datetime.now(pytz.UTC).astimezone(pytz.timezone('America/Los_Angeles'))
# Git 推送
os.system(f'cd . && git add docs/ && git commit -m "Auto update: ' + now_pst.strftime("%Y-%m-%d %H:%M:%S PST") + '" && git push origin master')
