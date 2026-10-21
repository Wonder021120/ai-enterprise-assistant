from openai import OpenAI
from dotenv import load_dotenv
from app.schemas import JDLLMResult
import os
import json

load_dotenv()

def create_llm_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise ValueError("未找到 OPENROUTER_API_KEY")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=60.0,
        max_retries=0,
    )

    return client


def analyze_jd_with_llm(job_description: str) -> JDLLMResult:
    client = create_llm_client()

    model_name = os.getenv(
        "OPENROUTER_MODEL",
        "liquid/lfm-2.5-2.6b:free"
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是专业的招聘JD信息提取助手。"
                    "请严格根据JD原文提取岗位名称和技能。"
                    "必须遵守以下规则："
                    "1. required_skills只包含明确要求必须掌握的技能。"
                    "2. preferred_skills只包含明确标注优先、加分、最好具备的技能。"
                    "3. 同一个技能不得同时出现在两个列表中。"
                    "4. 学历、工作地点、薪资、毕业时间、工作年限不是技能，不得加入技能列表。"
                    "5. 技能名称只保留标准名称，不附加熟练程度或原文描述。"
                    "6. 不允许推测JD没有明确提到的技能。"
                    "7. 没有相关信息时，技能列表返回空数组。"
                )
            },
            {
                "role": "user",
                "content": job_description
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "jd_analysis",
                "strict": True,
                "schema": JDLLMResult.model_json_schema()
            }
        },
        extra_body={
            "provider": {
                "require_parameters": True
            }
        },
        max_tokens=1500
    )

    answer = response.choices[0].message.content

    if not answer:
        raise ValueError("模型没有返回有效内容")

    data = json.loads(answer)

    result = JDLLMResult.model_validate(data)

    return result
