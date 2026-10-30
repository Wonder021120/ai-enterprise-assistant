import json
from dataclasses import dataclass
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from app.llm_service import (
    LLMOutputError,
    create_llm_client,
    get_llm_model_name,
)
from app.schemas import (
    JDLLMResult,
    LearningPlanItem,
    LearningPlanResponse,
    ResumeMatchingResponse,
    SkillMatchItem,
)


SkillCategory = Literal["required", "preferred"]
MatchStatus = Literal["evidence_found", "not_found_in_resume"]
PlanBasis = Literal[
    "resume_evidence_missing",
    "existing_evidence_to_strengthen",
]
PlanPriority = Literal["high", "medium", "low"]


class LearningPlanInputError(ValueError):
    """学习计划输入没有可处理的技能范围。"""


class LearningPlanConsistencyError(ValueError):
    """JD 与简历匹配结果之间存在结构化数据不一致。"""


class LearningPlanLLMItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str = Field(min_length=1, max_length=100)
    task_type: Literal[
        "learning",
        "project_practice",
        "resume_revision",
    ]
    rationale: str = Field(min_length=1, max_length=500)
    learning_objective: str = Field(min_length=1, max_length=500)
    action_steps: list[str] = Field(min_length=1, max_length=8)
    practice_task: str = Field(min_length=1, max_length=500)
    deliverable: str = Field(min_length=1, max_length=500)
    completion_criteria: list[str] = Field(min_length=1, max_length=8)
    estimated_hours: int = Field(ge=1, le=40)

    @field_validator(
        "skill",
        "rationale",
        "learning_objective",
        "practice_task",
        "deliverable",
    )
    @classmethod
    def reject_blank_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace characters")
        return value

    @field_validator("action_steps", "completion_criteria")
    @classmethod
    def validate_list_items(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError(
                    "list items must contain non-whitespace characters"
                )
            if len(value) > 300:
                raise ValueError(
                    "list items must contain at most 300 characters"
                )
        return values


class LearningPlanLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_summary: str = Field(min_length=1, max_length=1_000)
    plan_items: list[LearningPlanLLMItem] = Field(
        min_length=1,
        max_length=40,
    )

    @field_validator("plan_summary")
    @classmethod
    def reject_blank_plan_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "plan_summary must contain non-whitespace characters"
            )
        return value


@dataclass(frozen=True)
class _SkillPlanContext:
    skill: str
    skill_category: SkillCategory
    status: MatchStatus
    evidence: str | None
    basis: PlanBasis
    priority: PlanPriority


def _normalize_skill(skill: str) -> str:
    return skill.strip().casefold()


def _index_skill_matches(
    matches: list[SkillMatchItem],
    skill_category: SkillCategory,
) -> dict[str, SkillMatchItem]:
    indexed_matches = {}

    for match in matches:
        skill_key = _normalize_skill(match.skill)
        if skill_key in indexed_matches:
            raise LearningPlanConsistencyError(
                "resume_matching contains duplicate "
                f"{skill_category} skill matches"
            )
        indexed_matches[skill_key] = match

    return indexed_matches


def _build_category_contexts(
    skills: list[str],
    matches: list[SkillMatchItem],
    skill_category: SkillCategory,
) -> list[_SkillPlanContext]:
    indexed_matches = _index_skill_matches(matches, skill_category)
    contexts = []

    for skill in skills:
        match = indexed_matches.get(_normalize_skill(skill))
        if match is None:
            raise LearningPlanConsistencyError(
                "resume_matching is missing "
                f"{skill_category} skill: {skill}"
            )

        if match.status == "not_found_in_resume":
            basis: PlanBasis = "resume_evidence_missing"
            priority: PlanPriority = (
                "high" if skill_category == "required" else "medium"
            )
        else:
            basis = "existing_evidence_to_strengthen"
            priority = (
                "medium" if skill_category == "required" else "low"
            )

        contexts.append(
            _SkillPlanContext(
                skill=skill,
                skill_category=skill_category,
                status=match.status,
                evidence=match.evidence,
                basis=basis,
                priority=priority,
            )
        )

    return sorted(
        contexts,
        key=lambda context: context.status == "evidence_found",
    )


def _build_skill_contexts(
    jd_analysis: JDLLMResult,
    resume_matching: ResumeMatchingResponse,
) -> list[_SkillPlanContext]:
    skill_count = (
        len(jd_analysis.required_skills)
        + len(jd_analysis.preferred_skills)
    )
    if skill_count == 0:
        raise LearningPlanInputError(
            "learning plan requires at least one JD skill"
        )
    if skill_count > 20:
        raise LearningPlanInputError(
            "learning plan supports at most 20 JD skills"
        )

    all_skill_keys = [
        _normalize_skill(skill)
        for skill in (
            jd_analysis.required_skills + jd_analysis.preferred_skills
        )
    ]
    if len(all_skill_keys) != len(set(all_skill_keys)):
        raise LearningPlanConsistencyError(
            "JD contains duplicate skills after normalization"
        )

    required_contexts = _build_category_contexts(
        skills=jd_analysis.required_skills,
        matches=resume_matching.required_skill_matches,
        skill_category="required",
    )
    preferred_contexts = _build_category_contexts(
        skills=jd_analysis.preferred_skills,
        matches=resume_matching.preferred_skill_matches,
        skill_category="preferred",
    )
    return required_contexts + preferred_contexts


def _parse_llm_output(response) -> LearningPlanLLMOutput:
    if not response.choices:
        raise LLMOutputError("模型没有返回候选结果")

    choice = response.choices[0]
    message = choice.message

    if choice.finish_reason == "length":
        raise LLMOutputError("模型输出因长度限制被截断")

    if choice.finish_reason != "stop":
        raise LLMOutputError("模型响应未正常结束")

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
        raise LLMOutputError("模型返回的内容不是合法 JSON") from exc

    try:
        return LearningPlanLLMOutput.model_validate(data)
    except ValidationError as exc:
        raise LLMOutputError(
            "模型返回的 JSON 不符合学习计划数据结构"
        ) from exc


def _reconcile_plan_items(
    skill_contexts: list[_SkillPlanContext],
    llm_items: list[LearningPlanLLMItem],
) -> list[LearningPlanItem]:
    llm_items_by_skill = {}

    for item in llm_items:
        skill_key = _normalize_skill(item.skill)
        if skill_key in llm_items_by_skill:
            raise LLMOutputError("模型返回了重复的学习技能任务")
        llm_items_by_skill[skill_key] = item

    plan_items = []
    for priority_order, context in enumerate(skill_contexts, start=1):
        llm_item = llm_items_by_skill.get(_normalize_skill(context.skill))
        if llm_item is None:
            raise LLMOutputError(
                f"模型遗漏了技能的学习任务：{context.skill}"
            )

        if (
            context.basis == "resume_evidence_missing"
            and llm_item.task_type == "resume_revision"
        ):
            raise LLMOutputError(
                "缺少简历证据的技能不能直接生成简历改写任务"
            )

        plan_items.append(
            LearningPlanItem(
                skill=context.skill,
                skill_category=context.skill_category,
                priority=context.priority,
                priority_order=priority_order,
                basis=context.basis,
                task_type=llm_item.task_type,
                rationale=llm_item.rationale,
                learning_objective=llm_item.learning_objective,
                action_steps=llm_item.action_steps,
                practice_task=llm_item.practice_task,
                deliverable=llm_item.deliverable,
                completion_criteria=llm_item.completion_criteria,
                estimated_hours=llm_item.estimated_hours,
            )
        )

    return plan_items


def generate_learning_plan(
    jd_analysis: JDLLMResult,
    resume_matching: ResumeMatchingResponse,
) -> LearningPlanResponse:
    skill_contexts = _build_skill_contexts(
        jd_analysis,
        resume_matching,
    )
    client = create_llm_client()
    model_name = get_llm_model_name()

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是专业的求职学习计划助手。"
                    "请为输入中的每一项技能生成且只生成一个学习任务，"
                    "必须逐项覆盖，不得遗漏、重复或添加其他技能。"
                    "skill必须原样使用输入中的技能名称。"
                    "只生成task_type、rationale、learning_objective、"
                    "action_steps、practice_task、deliverable、"
                    "completion_criteria和estimated_hours内容。"
                    "技能类别、证据依据、优先级和执行顺序由系统确定，"
                    "不要在输出中生成这些字段。"
                    "match_status为not_found_in_resume时，只表示简历中"
                    "没有找到证据，不代表候选人不会或不具备该技能。"
                    "此时应建议学习或项目实践，通过真实产出建立证据，"
                    "不得生成resume_revision任务，不得编造已有经历。"
                    "match_status为evidence_found时，应深化真实实践，"
                    "可以完善现有项目成果或优化真实经历的简历呈现。"
                    "不得编造经历、成果、数字或证据。"
                    "建议必须具体、可执行，并提供可验证的完成标准。"
                    "action_steps和completion_criteria各生成2至4条，"
                    "内容简洁且避免重复。"
                    "estimated_hours必须是1至40之间的整数。"
                    "plan_summary应简洁概括优先学习顺序。"
                    "所有输出字段都必须返回。"
                    "只返回合法JSON对象，不要输出Markdown或其他说明文字。"
                    "JSON示例："
                    '{"plan_summary":"先补强必需技能。","plan_items":['
                    '{"skill":"Python","task_type":"project_practice",'
                    '"rationale":"通过实践形成真实证据。",'
                    '"learning_objective":"完成可测试的后端功能。",'
                    '"action_steps":["实现接口","编写测试"],'
                    '"practice_task":"开发一个后端服务。",'
                    '"deliverable":"代码仓库和测试报告。",'
                    '"completion_criteria":["接口可调用","测试通过"],'
                    '"estimated_hours":12}]}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "job_title": jd_analysis.job_title,
                        "skills": [
                            {
                                "skill": context.skill,
                                "skill_category": context.skill_category,
                                "match_status": context.status,
                                "evidence": context.evidence,
                                "basis": context.basis,
                                "priority": context.priority,
                            }
                            for context in skill_contexts
                        ],
                        "match_summary": resume_matching.match_summary,
                        "resume_improvement_suggestions": (
                            resume_matching.resume_improvement_suggestions
                        ),
                        "learning_practice_suggestions": (
                            resume_matching.learning_practice_suggestions
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        response_format={"type": "json_object"},
        extra_body={
            "thinking": {"type": "disabled"},
        },
        max_tokens=5000,
    )

    llm_output = _parse_llm_output(response)

    try:
        return LearningPlanResponse(
            plan_summary=llm_output.plan_summary,
            plan_items=_reconcile_plan_items(
                skill_contexts,
                llm_output.plan_items,
            ),
        )
    except ValidationError as exc:
        raise LLMOutputError(
            "模型返回的内容无法生成有效学习计划"
        ) from exc
