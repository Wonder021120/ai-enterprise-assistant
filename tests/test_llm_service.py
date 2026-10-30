import json
from types import SimpleNamespace
from unittest.mock import Mock, patch, sentinel

import pytest


with patch("dotenv.load_dotenv", return_value=False):
    from app import llm_service


def make_valid_jd_output():
    return {
        "company": None,
        "job_title": "Python工程师",
        "location": None,
        "recruitment_type": None,
        "education": None,
        "graduation_requirement": None,
        "experience_requirement": None,
        "salary": None,
        "required_skills": ["Python"],
        "preferred_skills": [],
    }


def make_completion_response(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=content,
                    refusal=None,
                ),
            )
        ]
    )


def mock_completion(monkeypatch, response):
    create = Mock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )
    monkeypatch.setattr(llm_service, "create_llm_client", lambda: client)
    return create


def test_create_llm_client_uses_deepseek_configuration(monkeypatch):
    openai_client = Mock(return_value=sentinel.client)
    monkeypatch.setattr(llm_service, "OpenAI", openai_client)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-api-key")

    result = llm_service.create_llm_client()

    assert result is sentinel.client
    openai_client.assert_called_once_with(
        base_url="https://api.deepseek.com",
        api_key="test-api-key",
        timeout=60.0,
        max_retries=2,
    )


def test_model_name_uses_deepseek_environment_and_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    assert llm_service.get_llm_model_name() == "deepseek-flash"

    monkeypatch.setenv("DEEPSEEK_MODEL", "configured-model")
    assert llm_service.get_llm_model_name() == "configured-model"


def test_analyze_jd_uses_deepseek_json_output(monkeypatch):
    create = mock_completion(
        monkeypatch,
        make_completion_response(json.dumps(make_valid_jd_output())),
    )
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-deepseek-model")

    result = llm_service.analyze_jd_with_llm("招聘Python工程师。")

    assert result.job_title == "Python工程师"
    request_kwargs = create.call_args.kwargs
    assert request_kwargs["model"] == "test-deepseek-model"
    assert request_kwargs["response_format"] == {"type": "json_object"}
    assert request_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
    assert "provider" not in request_kwargs["extra_body"]
    system_prompt = request_kwargs["messages"][0]["content"]
    assert "只返回合法JSON对象" in system_prompt
    assert "JSON示例" in system_prompt
    assert '"required_skills"' in system_prompt


@pytest.mark.parametrize(
    ("content", "error_pattern"),
    [
        ("{invalid json", "合法 JSON"),
        (json.dumps({"job_title": "Python工程师"}), "数据结构"),
    ],
)
def test_analyze_jd_keeps_json_and_pydantic_validation(
    monkeypatch,
    content,
    error_pattern,
):
    mock_completion(monkeypatch, make_completion_response(content))

    with pytest.raises(llm_service.LLMOutputError, match=error_pattern):
        llm_service.analyze_jd_with_llm("招聘Python工程师。")


@pytest.mark.parametrize(
    ("finish_reason", "error_pattern"),
    [
        ("length", "长度限制"),
        ("content_filter", "未正常结束"),
    ],
)
def test_analyze_jd_rejects_non_success_finish_reasons(
    monkeypatch,
    finish_reason,
    error_pattern,
):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=json.dumps(make_valid_jd_output()),
                    refusal=None,
                ),
            )
        ]
    )
    create = mock_completion(monkeypatch, response)

    with pytest.raises(
        llm_service.LLMOutputError,
        match=error_pattern,
    ):
        llm_service.analyze_jd_with_llm("招聘Python工程师。")

    create.assert_called_once()
