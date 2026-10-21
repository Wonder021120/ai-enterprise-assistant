import os
import json

from dotenv import load_dotenv
from openai import OpenAI


# 读取 .env 文件中的配置
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
model_name = os.getenv("OPENROUTER_MODEL", "openrouter/free")

if not api_key:
    raise ValueError("没有找到 OPENROUTER_API_KEY，请检查 .env 文件")


# 创建模型 API 客户端
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
    timeout=60.0,
    max_retries=0,
)


# 向模型发送一次请求
response = client.chat.completions.create(
    model=model_name,
    messages=[
        {
            "role": "system",
            "content": (
                "你是招聘JD信息提取助手。"
                "只能提取JD原文明确提供的信息，不允许补充或猜测。"
                "只返回合法JSON，不要解释或Markdown代码块。"
                "返回字段：job_title、required_skills、preferred_skills。"
                "无法确定的岗位名称使用null，缺失的技能列表使用[]。"
            ),
        },
        {
            "role": "user",
            "content": "招聘 AI 产品经理，要求熟悉 Python、RAG 和 Agent。请列出岗位要求的技术技能。",
        },
    ],
    temperature=0,
    max_tokens=1500,
)


# 输出模型回答
print("实际使用模型：", response.model)
print("结束原因：", response.choices[0].finish_reason)
print("Token 使用情况：", response.usage)
print("AI 分析结果：")
print(response.choices[0].message.content)

answer = response.choices[0].message.content
data = json.loads(answer)

print("数据类型：", type(data))
print("岗位名称：", data["job_title"])
print("必需技能：", data["required_skills"])
print("加分技能：", data["preferred_skills"])