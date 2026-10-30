import json


def main() -> None:
    from app.llm_service import create_llm_client, get_llm_model_name

    # 创建模型 API 客户端
    client = create_llm_client()
    model_name = get_llm_model_name()

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
                    "JSON示例："
                    '{"job_title":"AI产品经理",'
                    '"required_skills":["Python"],'
                    '"preferred_skills":["RAG","Agent"]}'
                ),
            },
            {
                "role": "user",
                "content": "招聘 AI 产品经理，要求熟悉 Python、RAG 和 Agent。请列出岗位要求的技术技能。",
            },
        ],
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
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


if __name__ == "__main__":
    main()
