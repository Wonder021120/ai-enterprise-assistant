import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.llm_service import (
    LLMOutputError,
    create_llm_client,
    get_llm_model_name,
)
from app.schemas import (
    JDLLMResult,
    ResumeMatchingResponse,
    SkillMatchItem,
)


logger = logging.getLogger(__name__)


class ResumeMatchingLLMSkillItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    status: Literal["evidence_found", "not_found_in_resume"]
    evidence: str | None


class ResumeMatchingLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_skill_matches: list[ResumeMatchingLLMSkillItem]
    preferred_skill_matches: list[ResumeMatchingLLMSkillItem]
    match_summary: str
    resume_improvement_suggestions: list[str]
    learning_practice_suggestions: list[str]


def _reconcile_skill_matches(
    expected_skills: list[str],
    llm_matches: list[ResumeMatchingLLMSkillItem],
    resume_text: str,
) -> list[SkillMatchItem]:
    first_match_by_skill = {}

    for item in llm_matches:
        skill_key = item.skill.casefold()
        if skill_key not in first_match_by_skill:
            first_match_by_skill[skill_key] = item

    reconciled_matches = []

    for expected_skill in expected_skills:
        llm_match = first_match_by_skill.get(expected_skill.casefold())

        if llm_match is None:
            reconciled_matches.append(
                SkillMatchItem(
                    skill=expected_skill,
                    status="not_found_in_resume",
                    evidence=None,
                )
            )
            continue

        if (
            llm_match.status == "evidence_found"
            and llm_match.evidence
            and llm_match.evidence.strip()
            and llm_match.evidence in resume_text
        ):
            reconciled_matches.append(
                SkillMatchItem(
                    skill=expected_skill,
                    status="evidence_found",
                    evidence=llm_match.evidence,
                )
            )
            continue

        reconciled_matches.append(
            SkillMatchItem(
                skill=expected_skill,
                status="not_found_in_resume",
                evidence=None,
            )
        )

    return reconciled_matches


def _parse_llm_output(response) -> ResumeMatchingLLMOutput:
    if not response.choices:
        logger.error("service=resume_matching error_code=no_candidate")
        raise LLMOutputError("模型没有返回候选结果")

    choice = response.choices[0]
    message = choice.message

    if choice.finish_reason == "length":
        logger.error(
            "service=resume_matching error_code=output_truncated"
        )
        raise LLMOutputError("模型输出因长度限制被截断")

    if choice.finish_reason != "stop":
        logger.error(
            "service=resume_matching "
            "error_code=abnormal_finish_reason"
        )
        raise LLMOutputError("模型响应未正常结束")

    if message.refusal:
        logger.error("service=resume_matching error_code=model_refusal")
        raise LLMOutputError("模型拒绝处理该请求")

    answer = message.content

    if not answer or not answer.strip():
        logger.error("service=resume_matching error_code=empty_output")
        raise LLMOutputError(
            f"模型没有返回有效内容，结束原因：{choice.finish_reason}"
        )

    try:
        data = json.loads(answer)
    except json.JSONDecodeError as exc:
        logger.error("service=resume_matching error_code=invalid_json")
        raise LLMOutputError(
            "模型返回的内容不是合法 JSON"
        ) from exc

    try:
        return ResumeMatchingLLMOutput.model_validate(data)
    except ValidationError as exc:
        logger.error(
            "service=resume_matching "
            "error_code=schema_validation_failed"
        )
        raise LLMOutputError(
            "模型返回的 JSON 不符合简历匹配数据结构"
        ) from exc


def match_resume_to_jd(
    jd_analysis: JDLLMResult,
    resume_text: str,
) -> ResumeMatchingResponse:
    client = create_llm_client()
    model_name = get_llm_model_name()

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是专业的简历与岗位技能匹配助手。"
                    "只分析输入中明确给出的必需技能和加分技能，"
                    "不得添加其他技能，也不得混淆两个技能类别。"
                    "必须逐项覆盖JD中全部必需技能和加分技能，"
                    "不得为了缩短输出而遗漏任何技能。"
                    "请结合简历中的项目、职责、技术使用和成果进行语义判断，"
                    "不要只做关键词搜索。"
                    "如果简历存在足以支持技能的证据，status返回evidence_found，"
                    "evidence必须使用简历原文中简短、连续、逐字一致的证据片段。"
                    "如果证据不足，status返回not_found_in_resume且evidence返回null。"
                    "证据不足只表示简历中未找到证据，不能断言候选人不会该技能。"
                    "不得编造经历、项目、数字或证据。"
                    "摘要和建议也不得把未体现的技能表述为候选人不具备的能力。"
                    "输出必须简洁且不得重复内容。"
                    "match_summary不超过120个中文字符。"
                    "resume_improvement_suggestions最多3条，"
                    "每条不超过50个中文字符。"
                    "learning_practice_suggestions最多3条，"
                    "每条不超过50个中文字符。"
                    "所有输出字段都必须返回。"
                    "只返回合法JSON对象，不要输出Markdown或其他说明文字。"
                    "JSON示例："
                    '{"required_skill_matches":[{"skill":"Python",'
                    '"status":"evidence_found",'
                    '"evidence":"使用Python开发后端服务"}],'
                    '"preferred_skill_matches":[{"skill":"Docker",'
                    '"status":"not_found_in_resume","evidence":null}],'
                    '"match_summary":"已找到Python项目证据。",'
                    '"resume_improvement_suggestions":["补充项目成果"],'
                    '"learning_practice_suggestions":["完成容器化练习"]}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "required_skills": jd_analysis.required_skills,
                        "preferred_skills": jd_analysis.preferred_skills,
                        "resume_text": resume_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_format={"type": "json_object"},
        extra_body={
            "thinking": {"type": "disabled"},
        },
        max_tokens=2500,
    )

    llm_output = _parse_llm_output(response)

    required_matches = _reconcile_skill_matches(
        expected_skills=jd_analysis.required_skills,
        llm_matches=llm_output.required_skill_matches,
        resume_text=resume_text,
    )
    preferred_matches = _reconcile_skill_matches(
        expected_skills=jd_analysis.preferred_skills,
        llm_matches=llm_output.preferred_skill_matches,
        resume_text=resume_text,
    )

    return ResumeMatchingResponse(
        required_skill_matches=required_matches,
        preferred_skill_matches=preferred_matches,
        match_summary=llm_output.match_summary,
        resume_improvement_suggestions=(
            llm_output.resume_improvement_suggestions
        ),
        learning_practice_suggestions=(
            llm_output.learning_practice_suggestions
        ),
    )
