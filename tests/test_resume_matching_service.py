import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import APIConnectionError

from app.schemas import JDLLMResult


with patch("dotenv.load_dotenv", return_value=False):
    from app.services import resume_matching_service as service


def make_jd_analysis(
    required_skills: list[str] | None = None,
    preferred_skills: list[str] | None = None,
) -> JDLLMResult:
    return JDLLMResult(
        company=None,
        job_title="Python工程师",
        location=None,
        recruitment_type=None,
        education=None,
        graduation_requirement=None,
        experience_requirement=None,
        salary=None,
        required_skills=required_skills or [],
        preferred_skills=preferred_skills or [],
    )


def make_llm_payload(
    required_skill_matches=None,
    preferred_skill_matches=None,
    match_summary="匹配摘要",
    resume_improvement_suggestions=None,
    learning_practice_suggestions=None,
):
    return {
        "required_skill_matches": required_skill_matches or [],
        "preferred_skill_matches": preferred_skill_matches or [],
        "match_summary": match_summary,
        "resume_improvement_suggestions": (
            resume_improvement_suggestions or []
        ),
        "learning_practice_suggestions": (
            learning_practice_suggestions or []
        ),
    }


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
                    message=SimpleNamespace(
                        content=content,
                        refusal=refusal,
                    ),
                    finish_reason=finish_reason,
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


def test_normal_resume_matching_result(monkeypatch, caplog):
    resume_text = (
        "负责使用Python开发数据处理服务。"
        "使用Docker完成服务容器化部署。"
    )
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "Python",
                "status": "evidence_found",
                "evidence": "使用Python开发数据处理服务",
            }
        ],
        preferred_skill_matches=[
            {
                "skill": "Docker",
                "status": "evidence_found",
                "evidence": "使用Docker完成服务容器化部署",
            }
        ],
        match_summary="简历包含两项技能的项目证据。",
        resume_improvement_suggestions=["补充项目规模"],
        learning_practice_suggestions=["完善部署监控"],
    )
    mock_llm_response(monkeypatch, payload)
    caplog.set_level(logging.ERROR, logger=service.__name__)

    result = service.match_resume_to_jd(
        make_jd_analysis(["Python"], ["Docker"]),
        resume_text,
    )

    assert result.model_dump() == {
        "required_skill_matches": [
            {
                "skill": "Python",
                "status": "evidence_found",
                "evidence": "使用Python开发数据处理服务",
            }
        ],
        "preferred_skill_matches": [
            {
                "skill": "Docker",
                "status": "evidence_found",
                "evidence": "使用Docker完成服务容器化部署",
            }
        ],
        "match_summary": "简历包含两项技能的项目证据。",
        "resume_improvement_suggestions": ["补充项目规模"],
        "learning_practice_suggestions": ["完善部署监控"],
    }
    assert not any(
        "service=resume_matching" in message
        for message in caplog.messages
    )


def test_missing_skill_is_filled_as_not_found(monkeypatch):
    resume_text = "使用Python开发后端接口。"
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "Python",
                "status": "evidence_found",
                "evidence": "使用Python开发后端接口",
            }
        ]
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(["Python", "SQL"]),
        resume_text,
    )

    assert [item.skill for item in result.required_skill_matches] == [
        "Python",
        "SQL",
    ]
    assert result.required_skill_matches[1].status == "not_found_in_resume"
    assert result.required_skill_matches[1].evidence is None


def test_extra_skills_are_removed(monkeypatch):
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "Python",
                "status": "not_found_in_resume",
                "evidence": None,
            },
            {
                "skill": "Go",
                "status": "not_found_in_resume",
                "evidence": None,
            },
        ],
        preferred_skill_matches=[
            {
                "skill": "React",
                "status": "not_found_in_resume",
                "evidence": None,
            }
        ],
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(["Python"]),
        "简历内容",
    )

    assert [item.skill for item in result.required_skill_matches] == [
        "Python"
    ]
    assert result.preferred_skill_matches == []


def test_case_insensitive_skill_mapping_uses_jd_name(monkeypatch):
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "python",
                "status": "not_found_in_resume",
                "evidence": None,
            }
        ]
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(["Python"]),
        "简历内容",
    )

    assert result.required_skill_matches[0].skill == "Python"


def test_verbatim_resume_evidence_is_preserved(monkeypatch):
    evidence = "使用FastAPI构建内部服务接口"
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "FastAPI",
                "status": "evidence_found",
                "evidence": evidence,
            }
        ]
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(["FastAPI"]),
        f"项目经历：{evidence}，并负责上线维护。",
    )

    assert result.required_skill_matches[0].status == "evidence_found"
    assert result.required_skill_matches[0].evidence == evidence


def test_fabricated_evidence_is_downgraded(monkeypatch):
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "Python",
                "status": "evidence_found",
                "evidence": "使用Python将处理速度提升50%",
            }
        ]
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(["Python"]),
        "参与后端项目开发。",
    )

    assert result.required_skill_matches[0].status == "not_found_in_resume"
    assert result.required_skill_matches[0].evidence is None


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        ("{not valid json", "invalid_json"),
        ("", "empty_output"),
        (
            json.dumps(
                {
                    "required_skill_matches": [],
                    "preferred_skill_matches": [],
                }
            ),
            "schema_validation_failed",
        ),
    ],
)
def test_invalid_llm_output_logs_safe_error_code(
    monkeypatch,
    caplog,
    content,
    error_code,
):
    create = Mock(return_value=make_completion_response(content))
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(service, "create_llm_client", lambda: client)
    caplog.set_level(logging.ERROR, logger=service.__name__)

    with pytest.raises(service.LLMOutputError):
        service.match_resume_to_jd(
            make_jd_analysis(["Python"]),
            "简历内容",
        )

    assert caplog.messages == [
        f"service=resume_matching error_code={error_code}"
    ]


def test_length_finish_reason_logs_output_truncated(monkeypatch, caplog):
    create = Mock(
        return_value=make_completion_response(
            json.dumps(make_llm_payload(), ensure_ascii=False),
            finish_reason="length",
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(service, "create_llm_client", lambda: client)
    caplog.set_level(logging.ERROR, logger=service.__name__)

    with pytest.raises(service.LLMOutputError):
        service.match_resume_to_jd(
            make_jd_analysis(["Python"]),
            "简历内容",
        )

    assert caplog.messages == [
        "service=resume_matching error_code=output_truncated"
    ]


@pytest.mark.parametrize(
    ("response", "error_code"),
    [
        (
            make_completion_response(None, choices=False),
            "no_candidate",
        ),
        (
            make_completion_response(None, refusal="request refused"),
            "model_refusal",
        ),
        (
            make_completion_response(
                json.dumps(make_llm_payload()),
                finish_reason="content_filter",
            ),
            "abnormal_finish_reason",
        ),
    ],
)
def test_candidate_and_refusal_failures_log_safe_error_code(
    monkeypatch,
    caplog,
    response,
    error_code,
):
    create = Mock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(service, "create_llm_client", lambda: client)
    caplog.set_level(logging.ERROR, logger=service.__name__)

    with pytest.raises(service.LLMOutputError):
        service.match_resume_to_jd(
            make_jd_analysis(["Python"]),
            "简历内容",
        )

    assert caplog.messages == [
        f"service=resume_matching error_code={error_code}"
    ]


def test_required_and_preferred_skills_are_not_mixed(monkeypatch):
    payload = make_llm_payload(
        required_skill_matches=[
            {
                "skill": "Docker",
                "status": "not_found_in_resume",
                "evidence": None,
            }
        ],
        preferred_skill_matches=[
            {
                "skill": "Python",
                "status": "not_found_in_resume",
                "evidence": None,
            }
        ],
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(["Python"], ["Docker"]),
        "简历内容",
    )

    assert result.required_skill_matches[0].skill == "Python"
    assert result.required_skill_matches[0].status == "not_found_in_resume"
    assert result.preferred_skill_matches[0].skill == "Docker"
    assert result.preferred_skill_matches[0].status == "not_found_in_resume"


def test_empty_skill_lists(monkeypatch):
    payload = make_llm_payload(
        match_summary="JD没有明确技能要求。",
    )
    mock_llm_response(monkeypatch, payload)

    result = service.match_resume_to_jd(
        make_jd_analysis(),
        "简历内容",
    )

    assert result.required_skill_matches == []
    assert result.preferred_skill_matches == []
    assert result.match_summary == "JD没有明确技能要求。"


def test_model_call_error_is_not_converted_to_success(monkeypatch):
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
        service.match_resume_to_jd(
            make_jd_analysis(["Python"]),
            "简历内容",
        )

    assert exc_info.value is connection_error


def test_strict_llm_schema_requires_every_field(monkeypatch):
    schema = service.ResumeMatchingLLMOutput.model_json_schema()
    expected_fields = {
        "required_skill_matches",
        "preferred_skill_matches",
        "match_summary",
        "resume_improvement_suggestions",
        "learning_practice_suggestions",
    }

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == expected_fields

    item_reference = schema["properties"]["required_skill_matches"][
        "items"
    ]["$ref"]
    item_definition = schema["$defs"][item_reference.rsplit("/", 1)[-1]]

    assert item_definition["additionalProperties"] is False
    assert set(item_definition["required"]) == {
        "skill",
        "status",
        "evidence",
    }
    assert {
        option["type"]
        for option in item_definition["properties"]["evidence"]["anyOf"]
    } == {"string", "null"}


def test_llm_request_uses_larger_budget_and_concise_output_prompt(
    monkeypatch,
):
    create = mock_llm_response(monkeypatch, make_llm_payload())

    service.match_resume_to_jd(
        make_jd_analysis(["Python"], ["Docker"]),
        "简历内容",
    )

    request_kwargs = create.call_args.kwargs
    system_prompt = request_kwargs["messages"][0]["content"]

    assert request_kwargs["model"] == "test-model"
    assert request_kwargs["response_format"] == {"type": "json_object"}
    assert request_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert "provider" not in request_kwargs["extra_body"]
    assert request_kwargs["max_tokens"] == 2500
    assert "match_summary不超过120个中文字符" in system_prompt
    assert "resume_improvement_suggestions最多3条" in system_prompt
    assert "learning_practice_suggestions最多3条" in system_prompt
    assert system_prompt.count("每条不超过50个中文字符") == 2
    assert "简短、连续、逐字一致的证据片段" in system_prompt
    assert "不得重复内容" in system_prompt
    assert "不得为了缩短输出而遗漏任何技能" in system_prompt
    assert "只返回合法JSON对象" in system_prompt
    assert "JSON示例" in system_prompt
    assert '"required_skill_matches"' in system_prompt
