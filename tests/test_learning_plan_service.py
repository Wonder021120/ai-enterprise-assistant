import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import APIConnectionError

from app.schemas import (
    JDLLMResult,
    ResumeMatchingResponse,
    SkillMatchItem,
)


with patch("dotenv.load_dotenv", return_value=False):
    from app.services import learning_plan_service as service


def make_jd_analysis(
    required_skills: list[str] | None = None,
    preferred_skills: list[str] | None = None,
) -> JDLLMResult:
    return JDLLMResult(
        company=None,
        job_title="AI应用开发工程师",
        location=None,
        recruitment_type=None,
        education=None,
        graduation_requirement=None,
        experience_requirement=None,
        salary=None,
        required_skills=required_skills or [],
        preferred_skills=preferred_skills or [],
    )


def make_skill_match(skill, status):
    return SkillMatchItem(
        skill=skill,
        status=status,
        evidence=(
            f"使用{skill}完成真实项目"
            if status == "evidence_found"
            else None
        ),
    )


def make_resume_matching(
    required_matches=None,
    preferred_matches=None,
) -> ResumeMatchingResponse:
    return ResumeMatchingResponse(
        required_skill_matches=[
            make_skill_match(skill, status)
            for skill, status in (required_matches or [])
        ],
        preferred_skill_matches=[
            make_skill_match(skill, status)
            for skill, status in (preferred_matches or [])
        ],
        match_summary="结构化匹配摘要",
        resume_improvement_suggestions=["补充真实项目成果"],
        learning_practice_suggestions=["完成可演示实践项目"],
    )


def make_llm_item(skill, **overrides):
    item = {
        "skill": skill,
        "task_type": "project_practice",
        "rationale": f"通过实践强化{skill}并形成真实证据。",
        "learning_objective": f"能够使用{skill}完成可验证功能。",
        "action_steps": ["学习核心概念", "完成自动化测试"],
        "practice_task": f"完成一个{skill}实践项目。",
        "deliverable": "代码仓库、README和测试报告。",
        "completion_criteria": ["功能可以运行", "测试全部通过"],
        "estimated_hours": 12,
    }
    item.update(overrides)
    return item


def make_llm_payload(skills, **overrides):
    payload = {
        "plan_summary": "先补充必需技能证据，再强化加分技能。",
        "plan_items": [make_llm_item(skill) for skill in skills],
    }
    payload.update(overrides)
    return payload


def make_completion_response(
    content,
    finish_reason="stop",
    refusal=None,
    choices=True,
):
    return SimpleNamespace(
        choices=(
            [
                SimpleNamespace(
                    finish_reason=finish_reason,
                    message=SimpleNamespace(
                        content=content,
                        refusal=refusal,
                    ),
                )
            ]
            if choices
            else []
        )
    )


def mock_llm_response(monkeypatch, payload):
    create = Mock(
        return_value=make_completion_response(
            json.dumps(payload, ensure_ascii=False)
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(service, "create_llm_client", lambda: client)
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")
    return create


def test_generate_normal_learning_plan(monkeypatch):
    mock_llm_response(monkeypatch, make_llm_payload(["Python", "Docker"]))

    result = service.generate_learning_plan(
        make_jd_analysis(["Python"], ["Docker"]),
        make_resume_matching(
            [("Python", "not_found_in_resume")],
            [("Docker", "evidence_found")],
        ),
    )

    assert result.plan_summary == "先补充必需技能证据，再强化加分技能。"
    assert [item.skill for item in result.plan_items] == [
        "Python",
        "Docker",
    ]
    assert result.plan_items[0].deliverable == "代码仓库、README和测试报告。"


def test_python_sets_categories_basis_priorities_and_order(monkeypatch):
    jd_analysis = make_jd_analysis(
        ["Python", "SQL"],
        ["Docker", "FastAPI"],
    )
    resume_matching = make_resume_matching(
        [
            ("Python", "evidence_found"),
            ("SQL", "not_found_in_resume"),
        ],
        [
            ("Docker", "evidence_found"),
            ("FastAPI", "not_found_in_resume"),
        ],
    )
    mock_llm_response(
        monkeypatch,
        make_llm_payload(["SQL", "Python", "FastAPI", "Docker"]),
    )

    result = service.generate_learning_plan(jd_analysis, resume_matching)

    assert [item.skill for item in result.plan_items] == [
        "SQL",
        "Python",
        "FastAPI",
        "Docker",
    ]
    assert [item.skill_category for item in result.plan_items] == [
        "required",
        "required",
        "preferred",
        "preferred",
    ]
    assert [item.basis for item in result.plan_items] == [
        "resume_evidence_missing",
        "existing_evidence_to_strengthen",
        "resume_evidence_missing",
        "existing_evidence_to_strengthen",
    ]
    assert [item.priority for item in result.plan_items] == [
        "high",
        "medium",
        "medium",
        "low",
    ]
    assert [item.priority_order for item in result.plan_items] == [1, 2, 3, 4]


def test_same_level_skills_keep_jd_order(monkeypatch):
    skills = ["Python", "SQL", "FastAPI"]
    mock_llm_response(monkeypatch, make_llm_payload(skills))

    result = service.generate_learning_plan(
        make_jd_analysis(skills),
        make_resume_matching(
            [(skill, "not_found_in_resume") for skill in skills]
        ),
    )

    assert [item.skill for item in result.plan_items] == skills
    assert [item.priority_order for item in result.plan_items] == [1, 2, 3]


def test_case_insensitive_matching_restores_jd_skill_name(monkeypatch):
    mock_llm_response(monkeypatch, make_llm_payload(["PYTHON"]))

    result = service.generate_learning_plan(
        make_jd_analysis(["Python"]),
        make_resume_matching([("python", "not_found_in_resume")]),
    )

    assert result.plan_items[0].skill == "Python"


def test_extra_llm_skills_are_removed(monkeypatch):
    mock_llm_response(
        monkeypatch,
        make_llm_payload(["Python", "Go"]),
    )

    result = service.generate_learning_plan(
        make_jd_analysis(["Python"]),
        make_resume_matching([("Python", "not_found_in_resume")]),
    )

    assert [item.skill for item in result.plan_items] == ["Python"]


def test_missing_llm_skill_fails(monkeypatch):
    mock_llm_response(monkeypatch, make_llm_payload(["Python"]))

    with pytest.raises(service.LLMOutputError, match="遗漏"):
        service.generate_learning_plan(
            make_jd_analysis(["Python", "SQL"]),
            make_resume_matching(
                [
                    ("Python", "not_found_in_resume"),
                    ("SQL", "not_found_in_resume"),
                ]
            ),
        )


def test_duplicate_llm_skill_fails(monkeypatch):
    payload = make_llm_payload(["Python", "python"])
    mock_llm_response(monkeypatch, payload)

    with pytest.raises(service.LLMOutputError, match="重复"):
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            make_resume_matching([("Python", "not_found_in_resume")]),
        )


def test_missing_evidence_rejects_resume_revision_task(monkeypatch):
    payload = make_llm_payload(["Python"])
    payload["plan_items"][0]["task_type"] = "resume_revision"
    mock_llm_response(monkeypatch, payload)

    with pytest.raises(service.LLMOutputError, match="简历改写"):
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            make_resume_matching([("Python", "not_found_in_resume")]),
        )


def test_no_skills_fails_before_creating_client(monkeypatch):
    create_client = Mock(side_effect=AssertionError("client must not run"))
    monkeypatch.setattr(service, "create_llm_client", create_client)

    with pytest.raises(service.LearningPlanInputError, match="at least one"):
        service.generate_learning_plan(
            make_jd_analysis(),
            make_resume_matching(),
        )

    create_client.assert_not_called()


def test_more_than_twenty_skills_fail_without_silent_truncation(monkeypatch):
    skills = [f"Skill-{index}" for index in range(21)]
    create_client = Mock(side_effect=AssertionError("client must not run"))
    monkeypatch.setattr(service, "create_llm_client", create_client)

    with pytest.raises(service.LearningPlanInputError, match="at most 20"):
        service.generate_learning_plan(
            make_jd_analysis(skills),
            make_resume_matching(
                [(skill, "not_found_in_resume") for skill in skills]
            ),
        )

    create_client.assert_not_called()


def test_missing_resume_match_raises_consistency_error(monkeypatch):
    create_client = Mock(side_effect=AssertionError("client must not run"))
    monkeypatch.setattr(service, "create_llm_client", create_client)

    with pytest.raises(
        service.LearningPlanConsistencyError,
        match="missing",
    ):
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            make_resume_matching(),
        )

    create_client.assert_not_called()


def test_duplicate_resume_matches_raise_consistency_error(monkeypatch):
    create_client = Mock(side_effect=AssertionError("client must not run"))
    monkeypatch.setattr(service, "create_llm_client", create_client)
    resume_matching = make_resume_matching(
        [
            ("Python", "not_found_in_resume"),
            ("python", "not_found_in_resume"),
        ]
    )

    with pytest.raises(
        service.LearningPlanConsistencyError,
        match="duplicate",
    ):
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            resume_matching,
        )

    create_client.assert_not_called()


def test_normalized_duplicate_jd_skills_raise_consistency_error(
    monkeypatch,
):
    create_client = Mock(side_effect=AssertionError("client must not run"))
    monkeypatch.setattr(service, "create_llm_client", create_client)

    with pytest.raises(
        service.LearningPlanConsistencyError,
        match="duplicate",
    ):
        service.generate_learning_plan(
            make_jd_analysis(["Python", " python "]),
            make_resume_matching(
                [
                    ("Python", "not_found_in_resume"),
                    (" python ", "not_found_in_resume"),
                ]
            ),
        )

    create_client.assert_not_called()


@pytest.mark.parametrize(
    ("response", "error_pattern"),
    [
        (make_completion_response("{invalid json"), "JSON"),
        (make_completion_response(""), "有效内容"),
        (
            make_completion_response(None, refusal="request refused"),
            "拒绝",
        ),
        (
            make_completion_response(
                json.dumps(make_llm_payload(["Python"])),
                finish_reason="length",
            ),
            "长度限制",
        ),
        (make_completion_response(None, choices=False), "候选结果"),
        (
            make_completion_response(
                json.dumps(make_llm_payload(["Python"])),
                finish_reason="content_filter",
            ),
            "未正常结束",
        ),
    ],
)
def test_invalid_completion_responses_raise_llm_output_error(
    monkeypatch,
    response,
    error_pattern,
):
    create = Mock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(service, "create_llm_client", lambda: client)

    with pytest.raises(service.LLMOutputError, match=error_pattern):
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            make_resume_matching([("Python", "not_found_in_resume")]),
        )


def test_schema_invalid_llm_output_fails(monkeypatch):
    invalid_item = make_llm_item("Python")
    invalid_item.pop("deliverable")
    mock_llm_response(
        monkeypatch,
        {
            "plan_summary": "学习计划摘要",
            "plan_items": [invalid_item],
        },
    )

    with pytest.raises(service.LLMOutputError, match="数据结构"):
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            make_resume_matching([("Python", "not_found_in_resume")]),
        )


def test_sdk_error_propagates(monkeypatch):
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    connection_error = APIConnectionError(request=request)
    create = Mock(side_effect=connection_error)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(service, "create_llm_client", lambda: client)

    with pytest.raises(APIConnectionError) as exc_info:
        service.generate_learning_plan(
            make_jd_analysis(["Python"]),
            make_resume_matching([("Python", "not_found_in_resume")]),
        )

    assert exc_info.value is connection_error


def test_strict_llm_schema_requires_all_fields(monkeypatch):
    schema = service.LearningPlanLLMOutput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"plan_summary", "plan_items"}

    item_reference = schema["properties"]["plan_items"]["items"]["$ref"]
    item_schema = schema["$defs"][item_reference.rsplit("/", 1)[-1]]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == set(item_schema["properties"])
    assert {
        "skill_category",
        "basis",
        "priority",
        "priority_order",
    }.isdisjoint(item_schema["properties"])


def test_prompt_protects_missing_evidence_semantics_and_omits_resume(
    monkeypatch,
):
    create = mock_llm_response(
        monkeypatch,
        make_llm_payload(["Python"]),
    )

    service.generate_learning_plan(
        make_jd_analysis(["Python"]),
        make_resume_matching([("Python", "not_found_in_resume")]),
    )

    request_kwargs = create.call_args.kwargs
    system_prompt = request_kwargs["messages"][0]["content"]
    user_payload = json.loads(request_kwargs["messages"][1]["content"])

    assert request_kwargs["model"] == "test-model"
    assert request_kwargs["response_format"] == {"type": "json_object"}
    assert request_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert "provider" not in request_kwargs["extra_body"]
    assert "不代表候选人不会或不具备该技能" in system_prompt
    assert "不得编造已有经历" in system_prompt
    assert "不得生成resume_revision任务" in system_prompt
    assert "只返回合法JSON对象" in system_prompt
    assert "JSON示例" in system_prompt
    assert '"plan_items"' in system_prompt
    assert "resume_text" not in user_payload
    assert set(user_payload) == {
        "job_title",
        "skills",
        "match_summary",
        "resume_improvement_suggestions",
        "learning_practice_suggestions",
    }
    assert user_payload["skills"][0]["match_status"] == (
        "not_found_in_resume"
    )
