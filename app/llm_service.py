
import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from app.schemas import JDLLMResult


load_dotenv()


class LLMOutputError(Exception):
    """模型返回的内容为空、格式错误或不符合预期结构。"""


def create_llm_client() -> OpenAI:
    """创建连接 DeepSeek 的 LLM 客户端。"""

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise ValueError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件")

    client = OpenAI(
        base_url="https://api.deepseek.com",
        api_key=api_key,
        timeout=60.0,
        max_retries=2,
    )

    return client


def get_llm_model_name() -> str:
    """返回三个 LLM 阶段统一使用的 DeepSeek 模型名称。"""

    return os.getenv("DEEPSEEK_MODEL", "deepseek-flash")


def analyze_jd_with_llm(job_description: str) -> JDLLMResult:
    """调用大模型分析招聘 JD，并验证结构化结果。"""

    client = create_llm_client()

    model_name = get_llm_model_name()

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是专业的招聘JD信息提取助手。"
                    "请严格根据用户提供的招聘信息提取字段，不允许编造。"

                    "company是公司名称。"
                    "如果公司名称只是某公司、某互联网公司、某企业等泛称，"
                    "而不是明确的具体公司名称，company必须返回null。"

                    "job_title是招聘岗位名称。"
                    "location是工作地点。"
                    "recruitment_type是招聘类型，例如校招或社招。"
                    "education是学历要求。"
                    "graduation_requirement是毕业时间或毕业届别要求。"

                    "experience_requirement只记录明确的工作年限、"
                    "工作经历或一般性的项目经验要求。"
                    "普通的技能掌握要求，例如熟悉Python、掌握SQL，"
                    "不得放入experience_requirement。"
                    "如果某项技能明确标注优先、加分或具有该技能的"
                    "相关经验者优先，应优先将该技能归入preferred_skills。"
                    "如果原文没有明确的工作年限、工作经历或一般性的"
                    "项目经验要求，experience_requirement必须返回null。"

                    "salary是原文明确提供的薪资信息。"

                    "required_skills只包含明确要求必须掌握的技能。"
                    "preferred_skills只包含明确标注优先、加分或最好具备的技能。"
                    "同一个技能不得同时出现在两个技能列表中。"
                    "技能名称尽量使用简洁的标准名称，不要附加熟练程度或整句描述。"
                    "学历、地点、薪资、毕业时间和工作经验不是技能，"
                    "不得放入技能列表。"

                    "对于公司、岗位、地点等单值字段，"
                    "如果原文没有提供信息，返回null。"
                    "对于技能列表，如果没有明确相关信息，返回空数组。"
                    "不得根据常识猜测原文没有提供的信息。"
                    "只返回合法JSON对象，不要输出Markdown或其他说明文字。"
                    "JSON示例："
                    '{"company":null,"job_title":"Python工程师",'
                    '"location":null,"recruitment_type":null,'
                    '"education":null,"graduation_requirement":null,'
                    '"experience_requirement":null,"salary":null,'
                    '"required_skills":["Python"],'
                    '"preferred_skills":["Docker"]}'
                ),
            },
            {
                "role": "user",
                "content": job_description,
            },
        ],
        response_format={"type": "json_object"},
        extra_body={
            "thinking": {"type": "disabled"},
        },
        max_tokens=1500,
    )

    if not response.choices:
        raise LLMOutputError("模型没有返回候选结果")

    choice = response.choices[0]

    if choice.finish_reason == "length":
        raise LLMOutputError("模型输出因长度限制被截断")

    if choice.finish_reason != "stop":
        raise LLMOutputError("模型响应未正常结束")

    message = choice.message

    if message.refusal:
        raise LLMOutputError("模型拒绝处理该请求")

    answer = message.content

    if not answer or not answer.strip():
        raise LLMOutputError(
            f"模型没有返回有效内容，结束原因：{choice.finish_reason}"
        )

    try:
        data = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise LLMOutputError(
            "模型返回的内容不是合法 JSON"
        ) from exc

    try:
        result = JDLLMResult.model_validate(data)
    except ValidationError as exc:
        raise LLMOutputError(
            "模型返回的 JSON 不符合 JD 数据结构"
        ) from exc

    return result
