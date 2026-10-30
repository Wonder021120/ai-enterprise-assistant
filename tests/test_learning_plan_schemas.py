import pytest
from pydantic import ValidationError

from app.schemas import (
    JDLLMResult,
    LearningPlanItem,
    LearningPlanResponse,
    ResumeMatchingResponse,
    SkillMatchItem,
)


def make_learning_plan_item(**overrides) -> LearningPlanItem:
    data = {
        "skill": "Python",
        "skill_category": "required",
        "priority": "high",
        "priority_order": 1,
        "basis": "resume_evidence_missing",
        "task_type": "project_practice",
        "rationale": "岗位要求Python，但简历中尚未找到相关证据。",
        "learning_objective": "能够使用Python完成可测试的后端功能。",
        "action_steps": [
            "实现一个包含输入校验的接口",
            "为核心逻辑编写自动化测试",
        ],
        "practice_task": "开发一个小型FastAPI服务。",
        "deliverable": "代码仓库、README和测试报告。",
        "completion_criteria": [
            "核心接口可以正常调用",
            "自动化测试全部通过",
        ],
        "estimated_hours": 12,
    }
    data.update(overrides)
    return LearningPlanItem(**data)


def test_valid_learning_plan_data_passes():
    item = make_learning_plan_item()
    response = LearningPlanResponse(
        plan_summary="优先补充必需技能的项目证据。",
        plan_items=[item],
    )

    assert response.plan_items == [item]
    assert response.plan_items[0].estimated_hours == 12


@pytest.mark.parametrize(
    "field_name",
    [
        "skill",
        "skill_category",
        "priority",
        "priority_order",
        "basis",
        "task_type",
        "rationale",
        "learning_objective",
        "action_steps",
        "practice_task",
        "deliverable",
        "completion_criteria",
        "estimated_hours",
    ],
)
def test_learning_plan_item_rejects_missing_required_fields(field_name):
    item = make_learning_plan_item().model_dump()
    item.pop(field_name)

    with pytest.raises(ValidationError):
        LearningPlanItem(**item)


@pytest.mark.parametrize("field_name", ["plan_summary", "plan_items"])
def test_learning_plan_response_rejects_missing_required_fields(field_name):
    data = {
        "plan_summary": "学习计划摘要",
        "plan_items": [make_learning_plan_item()],
    }
    data.pop(field_name)

    with pytest.raises(ValidationError):
        LearningPlanResponse(**data)


def test_learning_plan_schema_keeps_all_output_fields_required():
    item_schema = LearningPlanItem.model_json_schema()
    response_schema = LearningPlanResponse.model_json_schema()

    assert set(item_schema["required"]) == set(item_schema["properties"])
    assert set(response_schema["required"]) == {
        "plan_summary",
        "plan_items",
    }


def test_learning_plan_response_rejects_empty_plan_items():
    with pytest.raises(ValidationError):
        LearningPlanResponse(
            plan_summary="学习计划摘要",
            plan_items=[],
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "skill",
        "rationale",
        "learning_objective",
        "practice_task",
        "deliverable",
    ],
)
@pytest.mark.parametrize("invalid_value", ["", " \t\n"])
def test_learning_plan_item_rejects_empty_or_blank_text(
    field_name,
    invalid_value,
):
    with pytest.raises(ValidationError):
        make_learning_plan_item(**{field_name: invalid_value})


@pytest.mark.parametrize("invalid_value", ["", " \t\n"])
def test_learning_plan_response_rejects_empty_or_blank_summary(
    invalid_value,
):
    with pytest.raises(ValidationError):
        LearningPlanResponse(
            plan_summary=invalid_value,
            plan_items=[make_learning_plan_item()],
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("skill_category", "optional"),
        ("priority", "urgent"),
        ("basis", "skill_missing"),
        ("task_type", "reading"),
    ],
)
def test_learning_plan_item_rejects_invalid_literals(
    field_name,
    invalid_value,
):
    with pytest.raises(ValidationError):
        make_learning_plan_item(**{field_name: invalid_value})


def test_learning_plan_item_rejects_empty_action_steps():
    with pytest.raises(ValidationError):
        make_learning_plan_item(action_steps=[])


def test_learning_plan_item_rejects_empty_completion_criteria():
    with pytest.raises(ValidationError):
        make_learning_plan_item(completion_criteria=[])


@pytest.mark.parametrize(
    "field_name",
    ["action_steps", "completion_criteria"],
)
@pytest.mark.parametrize("invalid_item", ["", " \t\n"])
def test_learning_plan_item_rejects_empty_or_blank_list_items(
    field_name,
    invalid_item,
):
    with pytest.raises(ValidationError):
        make_learning_plan_item(**{field_name: [invalid_item]})


def test_priority_order_boundary():
    assert make_learning_plan_item(priority_order=1).priority_order == 1

    with pytest.raises(ValidationError):
        make_learning_plan_item(priority_order=0)


@pytest.mark.parametrize("valid_hours", [1, 40])
def test_estimated_hours_accepts_boundaries(valid_hours):
    assert make_learning_plan_item(
        estimated_hours=valid_hours
    ).estimated_hours == valid_hours


@pytest.mark.parametrize("invalid_hours", [0, 41])
def test_estimated_hours_rejects_out_of_range_values(invalid_hours):
    with pytest.raises(ValidationError):
        make_learning_plan_item(estimated_hours=invalid_hours)


def test_learning_plan_response_rejects_case_insensitive_duplicate_skills():
    first = make_learning_plan_item(skill="Python", priority_order=1)
    second = make_learning_plan_item(
        skill=" python ",
        priority_order=2,
    )

    with pytest.raises(ValidationError, match="duplicate skills"):
        LearningPlanResponse(
            plan_summary="学习计划摘要",
            plan_items=[first, second],
        )


def test_learning_plan_response_rejects_duplicate_priority_order():
    first = make_learning_plan_item(skill="Python", priority_order=1)
    second = make_learning_plan_item(skill="Docker", priority_order=1)

    with pytest.raises(ValidationError, match="duplicate priority_order"):
        LearningPlanResponse(
            plan_summary="学习计划摘要",
            plan_items=[first, second],
        )


def test_learning_plan_response_accepts_multiple_valid_tasks():
    first = make_learning_plan_item(skill="Python", priority_order=1)
    second = make_learning_plan_item(
        skill="Docker",
        skill_category="preferred",
        priority="medium",
        priority_order=2,
        basis="existing_evidence_to_strengthen",
        task_type="resume_revision",
    )

    response = LearningPlanResponse(
        plan_summary="先完成必需技能实践，再强化加分技能展示。",
        plan_items=[first, second],
    )

    assert [item.skill for item in response.plan_items] == [
        "Python",
        "Docker",
    ]
    assert [item.priority_order for item in response.plan_items] == [1, 2]


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("skill", "A" * 101),
        ("rationale", "A" * 501),
        ("learning_objective", "A" * 501),
        ("practice_task", "A" * 501),
        ("deliverable", "A" * 501),
        ("action_steps", ["A" * 301]),
        ("completion_criteria", ["A" * 301]),
        ("action_steps", ["有效步骤"] * 9),
        ("completion_criteria", ["有效标准"] * 9),
    ],
)
def test_learning_plan_item_rejects_oversized_content(
    field_name,
    invalid_value,
):
    with pytest.raises(ValidationError):
        make_learning_plan_item(**{field_name: invalid_value})


def test_learning_plan_response_rejects_oversized_content():
    with pytest.raises(ValidationError):
        LearningPlanResponse(
            plan_summary="A" * 1_001,
            plan_items=[make_learning_plan_item()],
        )

    items = [
        make_learning_plan_item(
            skill=f"Skill-{index}",
            priority_order=index,
        )
        for index in range(1, 22)
    ]

    with pytest.raises(ValidationError):
        LearningPlanResponse(
            plan_summary="学习计划摘要",
            plan_items=items,
        )


def test_existing_schemas_keep_their_behavior():
    jd_result = JDLLMResult(
        company=None,
        job_title="Python工程师",
        location=None,
        recruitment_type=None,
        education=None,
        graduation_requirement=None,
        experience_requirement=None,
        salary=None,
        required_skills=["Python", "python", "SQL"],
        preferred_skills=["PYTHON", "Docker"],
    )
    matching_response = ResumeMatchingResponse(
        required_skill_matches=[
            SkillMatchItem(
                skill="Python",
                status="evidence_found",
                evidence="使用Python开发服务",
            )
        ],
        match_summary="简历中找到Python证据。",
    )

    assert jd_result.required_skills == ["Python", "SQL"]
    assert jd_result.preferred_skills == ["Docker"]
    assert matching_response.preferred_skill_matches == []
    assert matching_response.learning_practice_suggestions == []
