# 群组消息实时总结

> 让群聊里的高价值信息不再被刷屏淹没。
> 1 分钟追上讨论进度，快速定位共识、分歧与下一步行动 🚀。
> 比特币波动在线预警，**声音**提示，提醒你及时操作

🔗 **线上站点（实时更新）**

👉 https://stock.autoin.me/

## ⏱ 更新规律

站点会根据市场开盘情况自动更新：

- **非交易时段**：每 **3 小时** 生成一次总结  
- **开盘前 1 小时 + 开盘期间**：每 **1 小时** 总结一次  
- **收盘后**：**立刻**总结过去 **24 小时** 的消息记录  

（如果你希望调整策略或频率，欢迎提 issue 讨论）

## 本地部署

### 定时总结

1. 设置local_secrets,其中包含了whop请求的header和访问模型的api密钥

   1. 在utils文件夹下新建local_secrets.py
   2. 在whop网页中打开开发者模式，在**网络**中找到``https://whop.com/api/graphql/MessagesFetchFeedPosts/`` 请求，复制该请求附带的 request headers，整理成 Python 字典后放到 `local_secrets.py`。
   
      注意：
      - 不能只保留少量 header，Whop 对请求环境校验比较严格，缺字段时可能返回 `429`。
      - 除了 `Cookie` 之外，`accept`、`accept-language`、`origin`、`referer`、`user-agent`、`sec-fetch-*`、`sec-ch-ua*`、`sentry-trace`、`baggage`、`traceparent`、`tracestate`、`newrelic`、`x-deployment-id`、`x-whop-force-new-permission-system` 这类头也建议一并保留。
      - 不要把浏览器里的 HTTP/2 伪首部原样抄进来，例如 `:authority`、`:method`、`:path`、`:scheme`，`requests` 不需要这些。
      - `content-length` 也不要手工填写，交给 `requests` 自动生成。
      - 如果后续重新出现 `429`，优先检查 `Cookie`、`cf_clearance`、`whop-core.access-token` 这些会话字段是否已过期。

   ```python
   whom_headers = {
      'accept': '*/*',
      'accept-encoding': 'gzip, deflate, br, zstd',
      'accept-language': 'en,zh-CN;q=0.9,zh;q=0.8',
      'baggage': '',
      'newrelic': '',
      'dpr': '',
      'origin': 'https://whop.com',
      'priority': '',
      'referer': 'https://whop.com/joined/stock-and-option/.../app/',
      'sec-ch-ua': '',
      'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': '"macOS"',
      'sec-fetch-dest': 'empty',
      'sec-fetch-mode': 'cors',
      'sec-fetch-site': 'same-origin',
      'sentry-trace': '',
      'traceparent': '',
      'tracestate': '',
      'user-agent': '',
      'x-deployment-id': '',
      'x-whop-force-new-permission-system': '',
      'Cookie': '',
      'content-type': 'application/json'
   }
   ```

   3. 可以先单独验证 headers 是否有效，再跑完整总结流程。只要下面这段脚本返回 `200`，通常就说明 `MessagesFetchFeedPosts` 至少已经能打通：

   ```python
   import requests
   from utils.local_secrets import whom_headers
   from utils.message_utils import url, get_payload

   resp = requests.post(url, headers=whom_headers, data=get_payload(5, None), timeout=30)
   print(resp.status_code)
   print(resp.text[:300])
   ```

   4. 再设置api密钥，支持google和openai格式的请求，在local_secrets.py中按照如下格式填写

   ```python
      model_key = [
        {
           'model': "Pro/deepseek-ai/DeepSeek-V3.2", #使用的模型，这里是deepseek
           "key": "密钥",
           "base_url": "https://api.siliconflow.cn/v1", # 如果使用了转发，需要填写baseurl，这里是硅基流动
           "app": "openai" # 使用openai库进行访问
        },
        {
           'model': "gemini-2.5-pro", #使用的模型
           'key': "google 密钥",
           'app': "google" # 使用google库进行访问
        },
      ]
   ```

2. 设置程序，每1小时运行仓库中的脚本``sh/run.sh``
3. 运行whop_summary.py即可进行总结

### btc预警

1. 运行crypto_monitor.py即可

## ✨ 这是什么？

这是一个为**群内财经讨论**做**实时总结**的网站。

无论你是：

- 刚进群想补课的新朋友  
- 错过了关键讨论的群成员  
- 想快速回顾重点、整理思路的人  

都可以在这里用极短时间**掌握群聊精华**。

## ✅ 你会看到什么？

每次总结都会输出：

- **讨论的核心结论**（发生了什么、结论是什么）  
- **关键共识 / 分歧点**（大家达成一致的地方 & 争议焦点）  
- **可执行的下一步**（接下来能做什么、该关注什么）  

目标是把群里一小时/一天的聊天，压缩成**好读、好找、好回溯的内容**。  
🌊 聊天流 ➜ 💎 结构化沉淀


## 🧠 为什么你可能会喜欢它？

它解决了社区聊天中最真实的痛点：

- 群聊太快，爬楼太累 😵‍💫  
- 热点话题回头找不到 😭  
- 新人完全不知道从哪补课 🫠  
- 重要结论被无关刷屏冲掉 🤡  

这个站点的目标很简单：

> **让每一段好的讨论都能留下痕迹。**


## ⭐ 支持项目

如果你觉得有用，欢迎点个 Star！  
这会给我很大动力继续优化 ❤️


## 🐛 反馈 & 贡献

遇到问题或有改进建议：

- 欢迎直接提 Issue  
- 也可以提交 PR 一起完善  

你的任何建议都会帮助这个工具变得更好！


## 📌 Roadmap

接下来可能会做的方向：

- xiaozhaoluck的操作思路总结
- 股票点位单独放到一个栏目中，可以更加方便的对比
- 更精准的主题聚类与热点追踪  
- 优化展现形式  
- 针对不同内容分开总结
