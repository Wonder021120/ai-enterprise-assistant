
import json

from pydantic import BaseModel


# 1. 定义模型应该返回的数据结构
class JDResult(BaseModel):
    job_title: str | None
    required_skills: list[str]
    preferred_skills: list[str]


def main() -> None:
    from app.llm_service import create_llm_client, get_llm_model_name

    # 2. 读取统一的 DeepSeek API 配置
    client = create_llm_client()
    model_name = get_llm_model_name()

    # 3. 调用大模型，并要求结构化输出
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是招聘JD信息提取助手。"
                    "只提取原文明确要求的技能，不要编造。"
                    "只返回合法JSON对象，不要输出Markdown或其他说明。"
                    "JSON示例："
                    '{"job_title":"AI产品经理",'
                    '"required_skills":["Python"],'
                    '"preferred_skills":["RAG","Agent"]}'
                )
            },
            {
                "role": "user",
                "content": (
                    "招聘AI产品经理，要求熟悉Python、RAG和Agent。"
                )
            }
        ],
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
        max_tokens=1500,
    )

    # 4. 检查模型回答
    answer = response.choices[0].message.content

    print("实际模型：", response.model)
    print("结束原因：", response.choices[0].finish_reason)
    print("原始回答：", answer)

    if not answer:
        raise ValueError("模型没有返回正文")

    # 5. 将 JSON 转换为 Python 对象
    data = json.loads(answer)

    # 6. 用 Pydantic 验证字段和类型
    result = JDResult.model_validate(data)

    print("验证成功！")
    print("岗位名称：", result.job_title)
    print("必需技能：", result.required_skills)
    print("加分技能：", result.preferred_skills)


if __name__ == "__main__":
    main()
