import logging
from unittest.mock import Mock, call, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.schemas import (
    JDLLMResult,
    LearningPlanItem,
    LearningPlanResponse,
    ResumeMatchingResponse,
    SkillMatchItem,
)


with patch("dotenv.load_dotenv", return_value=False):
    from app import main as main_module


client = TestClient(main_module.app)


def make_resume_match_jd_result() -> JDLLMResult:
    return JDLLMResult(
        company=None,
        job_title="Python工程师",
        location=None,
        recruitment_type=None,
        education=None,
        graduation_requirement=None,
        experience_requirement=None,
        salary=None,
        required_skills=["Python"],
        preferred_skills=["Docker"],
    )


def make_resume_match_response() -> ResumeMatchingResponse:
    return ResumeMatchingResponse(
        required_skill_matches=[
            SkillMatchItem(
                skill="Python",
                status="evidence_found",
                evidence="使用Python开发后端服务",
            )
        ],
        preferred_skill_matches=[
            SkillMatchItem(
                skill="Docker",
                status="not_found_in_resume",
            )
        ],
        match_summary="简历中找到Python项目证据。",
        resume_improvement_suggestions=["补充项目成果数据"],
        learning_practice_suggestions=["完成Docker部署练习"],
    )


def make_learning_plan_response() -> LearningPlanResponse:
    return LearningPlanResponse(
        plan_summary="优先完成Python项目实践。",
        plan_items=[
            LearningPlanItem(
                skill="Python",
                skill_category="required",
                priority="medium",
                priority_order=1,
                basis="existing_evidence_to_strengthen",
                task_type="project_practice",
                rationale="深化已有Python项目证据。",
                learning_objective="完成可测试的Python后端功能。",
                action_steps=["实现接口", "编写自动化测试"],
                practice_task="扩展现有Python后端项目。",
                deliverable="代码仓库和测试报告。",
                completion_criteria=["接口可调用", "测试全部通过"],
                estimated_hours=12,
            ),
            LearningPlanItem(
                skill="Docker",
                skill_category="preferred",
                priority="medium",
                priority_order=2,
                basis="resume_evidence_missing",
                task_type="learning",
                rationale="通过实践补充Docker项目证据。",
                learning_objective="能够容器化部署后端服务。",
                action_steps=["编写Dockerfile", "运行容器化服务"],
                practice_task="容器化部署Python项目。",
                deliverable="Dockerfile和部署说明。",
                completion_criteria=["镜像构建成功", "容器服务可访问"],
                estimated_hours=8,
            ),
        ],
    )


def make_rate_limit_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    response = httpx.Response(status_code=429, request=request)
    return main_module.RateLimitError(
        "rate limit exceeded",
        response=response,
        body={"error": "rate limit exceeded"},
    )


def make_connection_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    return main_module.APIConnectionError(request=request)


def make_timeout_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    return main_module.APITimeoutError(request=request)


def make_api_status_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    response = httpx.Response(status_code=500, request=request)
    return main_module.APIStatusError(
        "provider error",
        response=response,
        body={"error": "provider error"},
    )


def test_health_check_returns_service_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "CareerPilot AI",
    }


def test_analyze_jd_rejects_missing_job_description():
    response = client.post("/analyze/jd", json={})

    assert response.status_code == 422


def test_analyze_jd_rejects_empty_job_description():
    response = client.post(
        "/analyze/jd",
        json={"job_description": ""},
    )

    assert response.status_code == 422


def test_analyze_jd_rejects_whitespace_only_job_description():
    response = client.post(
        "/analyze/jd",
        json={"job_description": " \t\n"},
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "job_description"]
    assert "must contain non-whitespace characters" in error["msg"]


def test_analyze_jd_rejects_job_description_over_max_length():
    response = client.post(
        "/analyze/jd",
        json={"job_description": "A" * 20_001},
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "job_description"]
    assert "20000" in error["msg"]


def test_analyze_jd_accepts_job_description_at_max_length(monkeypatch):
    job_description = "A" * 20_000

    def fake_analyze_jd_with_llm(received_job_description):
        assert received_job_description == job_description
        return main_module.JDAnalysisResponse()

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        fake_analyze_jd_with_llm,
    )

    response = client.post(
        "/analyze/jd",
        json={"job_description": job_description},
    )

    assert response.status_code == 200
    assert response.json() == {
        "company": None,
        "job_title": None,
        "location": None,
        "recruitment_type": None,
        "education": None,
        "graduation_requirement": None,
        "experience_requirement": None,
        "salary": None,
        "required_skills": [],
        "preferred_skills": [],
    }


def test_analyze_jd_returns_structured_result(monkeypatch):
    expected_response = {
        "company": "示例科技",
        "job_title": "AI应用开发工程师",
        "location": "上海",
        "recruitment_type": "校招",
        "education": "硕士学历",
        "graduation_requirement": "2026届",
        "experience_requirement": None,
        "salary": "20k-30k",
        "required_skills": ["Python", "SQL"],
        "preferred_skills": ["FastAPI", "Docker"],
    }

    def fake_analyze_jd_with_llm(job_description):
        assert job_description == "招聘AI应用开发工程师，要求熟悉Python和SQL。"
        return main_module.JDAnalysisResponse(**expected_response)

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        fake_analyze_jd_with_llm,
    )

    response = client.post(
        "/analyze/jd",
        json={
            "job_description": "招聘AI应用开发工程师，要求熟悉Python和SQL。"
        },
    )

    assert response.status_code == 200
    assert response.json() == expected_response


def test_analyze_jd_maps_llm_output_error_to_bad_gateway(monkeypatch):
    def raise_llm_output_error(_job_description):
        raise main_module.LLMOutputError("invalid model output")

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        raise_llm_output_error,
    )

    response = client.post(
        "/analyze/jd",
        json={"job_description": "招聘Python工程师。"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The LLM returned invalid or empty output."
    }


def test_analyze_jd_maps_rate_limit_error_to_service_unavailable(monkeypatch):
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    provider_response = httpx.Response(
        status_code=429,
        request=request,
    )

    def raise_rate_limit_error(_job_description):
        raise main_module.RateLimitError(
            "rate limit exceeded",
            response=provider_response,
            body={"error": "rate limit exceeded"},
        )

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        raise_rate_limit_error,
    )

    response = client.post(
        "/analyze/jd",
        json={"job_description": "招聘Python工程师。"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "The LLM provider is temporarily rate-limited. "
            "Please try again later."
        )
    }


def test_analyze_jd_maps_connection_error_to_service_unavailable(monkeypatch):
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )

    def raise_connection_error(_job_description):
        raise main_module.APIConnectionError(request=request)

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        raise_connection_error,
    )

    response = client.post(
        "/analyze/jd",
        json={"job_description": "招聘Python工程师。"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "The LLM service is temporarily unavailable. "
            "Please try again later."
        )
    }


def test_analyze_jd_maps_timeout_error_to_service_unavailable(monkeypatch):
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )

    def raise_timeout_error(_job_description):
        raise main_module.APITimeoutError(request=request)

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        raise_timeout_error,
    )

    response = client.post(
        "/analyze/jd",
        json={"job_description": "招聘Python工程师。"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "The LLM service is temporarily unavailable. "
            "Please try again later."
        )
    }


def test_analyze_jd_maps_api_status_error_to_bad_gateway(monkeypatch):
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    provider_response = httpx.Response(
        status_code=500,
        request=request,
    )

    def raise_api_status_error(_job_description):
        raise main_module.APIStatusError(
            "provider error",
            response=provider_response,
            body={"error": "provider error"},
        )

    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        raise_api_status_error,
    )

    response = client.post(
        "/analyze/jd",
        json={"job_description": "招聘Python工程师。"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The LLM provider returned an error."
    }


def test_resume_match_runs_pipeline_and_returns_complete_response(
    monkeypatch,
):
    job_description = "招聘Python工程师，要求熟悉Python，Docker优先。"
    resume_text = "使用Python开发后端服务。"
    jd_analysis = make_resume_match_jd_result()
    expected_response = make_resume_match_response()
    analyze_mock = Mock(return_value=jd_analysis)
    match_mock = Mock(return_value=expected_response)
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)

    response = client.post(
        "/analyze/resume-match",
        json={
            "job_description": job_description,
            "resume_text": resume_text,
        },
    )

    assert response.status_code == 200
    assert response.json() == expected_response.model_dump(mode="json")
    analyze_mock.assert_called_once_with(job_description)
    match_mock.assert_called_once_with(jd_analysis, resume_text)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"job_description": "有效JD内容"},
        {"resume_text": "有效简历内容"},
    ],
)
def test_resume_match_rejects_missing_required_fields(monkeypatch, payload):
    analyze_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    match_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)

    response = client.post("/analyze/resume-match", json=payload)

    assert response.status_code == 422
    analyze_mock.assert_not_called()
    match_mock.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "job_description": " \t\n",
            "resume_text": "有效简历内容",
        },
        {
            "job_description": "有效JD内容",
            "resume_text": " \t\n",
        },
    ],
)
def test_resume_match_rejects_blank_text(monkeypatch, payload):
    analyze_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    match_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)

    response = client.post("/analyze/resume-match", json=payload)

    assert response.status_code == 422
    analyze_mock.assert_not_called()
    match_mock.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "job_description": "A" * 20_001,
            "resume_text": "有效简历内容",
        },
        {
            "job_description": "有效JD内容",
            "resume_text": "A" * 30_001,
        },
    ],
)
def test_resume_match_rejects_over_length_text(monkeypatch, payload):
    analyze_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    match_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)

    response = client.post("/analyze/resume-match", json=payload)

    assert response.status_code == 422
    analyze_mock.assert_not_called()
    match_mock.assert_not_called()


def test_resume_match_maps_jd_output_error_to_bad_gateway(
    monkeypatch,
    caplog,
):
    analyze_mock = Mock(
        side_effect=main_module.LLMOutputError("invalid JD output")
    )
    match_mock = Mock()
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    caplog.set_level(logging.ERROR, logger=main_module.__name__)

    response = client.post(
        "/analyze/resume-match",
        json={
            "job_description": "有效JD内容",
            "resume_text": "有效简历内容",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The LLM returned invalid or empty output."
    }
    assert (
        "resume_match stage=jd_analysis "
        "llm_output_error=invalid JD output"
    ) in caplog.messages
    assert not any(
        "stage=resume_matching" in message for message in caplog.messages
    )
    match_mock.assert_not_called()


def test_resume_match_maps_matching_output_error_to_bad_gateway(
    monkeypatch,
    caplog,
):
    jd_analysis = make_resume_match_jd_result()
    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        Mock(return_value=jd_analysis),
    )
    monkeypatch.setattr(
        main_module,
        "match_resume_to_jd",
        Mock(side_effect=main_module.LLMOutputError("invalid match output")),
    )
    caplog.set_level(logging.ERROR, logger=main_module.__name__)

    response = client.post(
        "/analyze/resume-match",
        json={
            "job_description": "有效JD内容",
            "resume_text": "有效简历内容",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The LLM returned invalid or empty output."
    }
    assert (
        "resume_match stage=resume_matching "
        "llm_output_error=invalid match output"
    ) in caplog.messages
    assert not any(
        "stage=jd_analysis" in message for message in caplog.messages
    )


@pytest.mark.parametrize("failure_stage", ["jd_analysis", "resume_matching"])
@pytest.mark.parametrize(
    (
        "error_factory",
        "expected_status",
        "expected_detail",
    ),
    [
        (
            make_rate_limit_error,
            503,
            "The LLM provider is temporarily rate-limited. Please try again later.",
        ),
        (
            make_connection_error,
            503,
            "The LLM service is temporarily unavailable. Please try again later.",
        ),
        (
            make_timeout_error,
            503,
            "The LLM service is temporarily unavailable. Please try again later.",
        ),
        (
            make_api_status_error,
            502,
            "The LLM provider returned an error.",
        ),
    ],
)
def test_resume_match_maps_provider_errors_from_both_stages(
    monkeypatch,
    failure_stage,
    error_factory,
    expected_status,
    expected_detail,
):
    jd_analysis = make_resume_match_jd_result()
    error = error_factory()

    if failure_stage == "jd_analysis":
        analyze_mock = Mock(side_effect=error)
        match_mock = Mock()
    else:
        analyze_mock = Mock(return_value=jd_analysis)
        match_mock = Mock(side_effect=error)

    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)

    response = client.post(
        "/analyze/resume-match",
        json={
            "job_description": "有效JD内容",
            "resume_text": "有效简历内容",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}

    if failure_stage == "jd_analysis":
        match_mock.assert_not_called()
    else:
        match_mock.assert_called_once_with(jd_analysis, "有效简历内容")


def test_learning_plan_runs_three_stage_pipeline_in_order(monkeypatch):
    job_description = "招聘Python工程师，Docker优先。"
    resume_text = "使用Python开发后端服务。"
    jd_analysis = make_resume_match_jd_result()
    resume_matching = make_resume_match_response()
    learning_plan = make_learning_plan_response()
    pipeline = Mock()
    analyze_mock = Mock(return_value=jd_analysis)
    match_mock = Mock(return_value=resume_matching)
    generate_mock = Mock(return_value=learning_plan)
    pipeline.attach_mock(analyze_mock, "analyze")
    pipeline.attach_mock(match_mock, "match")
    pipeline.attach_mock(generate_mock, "generate")
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    monkeypatch.setattr(main_module, "generate_learning_plan", generate_mock)

    response = client.post(
        "/analyze/learning-plan",
        json={
            "job_description": job_description,
            "resume_text": resume_text,
        },
    )

    assert response.status_code == 200
    assert response.json() == learning_plan.model_dump(mode="json")
    assert pipeline.mock_calls == [
        call.analyze(job_description),
        call.match(jd_analysis, resume_text),
        call.generate(jd_analysis, resume_matching),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"job_description": "有效JD内容"},
        {"resume_text": "有效简历内容"},
    ],
)
def test_learning_plan_rejects_missing_request_fields(monkeypatch, payload):
    analyze_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    match_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    generate_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    monkeypatch.setattr(main_module, "generate_learning_plan", generate_mock)

    response = client.post("/analyze/learning-plan", json=payload)

    assert response.status_code == 422
    analyze_mock.assert_not_called()
    match_mock.assert_not_called()
    generate_mock.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "job_description": " \t\n",
            "resume_text": "有效简历内容",
        },
        {
            "job_description": "有效JD内容",
            "resume_text": " \t\n",
        },
    ],
)
def test_learning_plan_rejects_blank_request_text(monkeypatch, payload):
    analyze_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    match_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    generate_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    monkeypatch.setattr(main_module, "generate_learning_plan", generate_mock)

    response = client.post("/analyze/learning-plan", json=payload)

    assert response.status_code == 422
    analyze_mock.assert_not_called()
    match_mock.assert_not_called()
    generate_mock.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "job_description": "A" * 20_001,
            "resume_text": "有效简历内容",
        },
        {
            "job_description": "有效JD内容",
            "resume_text": "A" * 30_001,
        },
    ],
)
def test_learning_plan_rejects_over_length_request_text(
    monkeypatch,
    payload,
):
    analyze_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    match_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    generate_mock = Mock(side_effect=AssertionError("pipeline must not run"))
    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    monkeypatch.setattr(main_module, "generate_learning_plan", generate_mock)

    response = client.post("/analyze/learning-plan", json=payload)

    assert response.status_code == 422
    analyze_mock.assert_not_called()
    match_mock.assert_not_called()
    generate_mock.assert_not_called()


@pytest.mark.parametrize(
    "failure_stage",
    ["jd_analysis", "resume_matching", "learning_plan"],
)
def test_learning_plan_maps_llm_output_errors_from_all_stages(
    monkeypatch,
    caplog,
    failure_stage,
):
    jd_analysis = make_resume_match_jd_result()
    resume_matching = make_resume_match_response()
    error = main_module.LLMOutputError("invalid stage output")

    if failure_stage == "jd_analysis":
        analyze_mock = Mock(side_effect=error)
        match_mock = Mock()
        generate_mock = Mock()
    elif failure_stage == "resume_matching":
        analyze_mock = Mock(return_value=jd_analysis)
        match_mock = Mock(side_effect=error)
        generate_mock = Mock()
    else:
        analyze_mock = Mock(return_value=jd_analysis)
        match_mock = Mock(return_value=resume_matching)
        generate_mock = Mock(side_effect=error)

    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    monkeypatch.setattr(main_module, "generate_learning_plan", generate_mock)
    caplog.set_level(logging.ERROR, logger=main_module.__name__)

    response = client.post(
        "/analyze/learning-plan",
        json={
            "job_description": "有效JD内容",
            "resume_text": "有效简历内容",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The LLM returned invalid or empty output."
    }
    assert (
        "api=analyze_learning_plan "
        f"stage={failure_stage} exception=LLMOutputError"
    ) in caplog.messages
    assert "invalid stage output" not in "\n".join(caplog.messages)
    if failure_stage == "jd_analysis":
        match_mock.assert_not_called()
        generate_mock.assert_not_called()
    elif failure_stage == "resume_matching":
        generate_mock.assert_not_called()
    else:
        generate_mock.assert_called_once_with(jd_analysis, resume_matching)


@pytest.mark.parametrize(
    "failure_stage",
    ["jd_analysis", "resume_matching", "learning_plan"],
)
@pytest.mark.parametrize(
    ("error_factory", "expected_status", "expected_detail"),
    [
        (
            make_rate_limit_error,
            503,
            "The LLM provider is temporarily rate-limited. Please try again later.",
        ),
        (
            make_connection_error,
            503,
            "The LLM service is temporarily unavailable. Please try again later.",
        ),
        (
            make_timeout_error,
            503,
            "The LLM service is temporarily unavailable. Please try again later.",
        ),
        (
            make_api_status_error,
            502,
            "The LLM provider returned an error.",
        ),
    ],
)
def test_learning_plan_maps_provider_errors_from_all_stages(
    monkeypatch,
    caplog,
    failure_stage,
    error_factory,
    expected_status,
    expected_detail,
):
    jd_analysis = make_resume_match_jd_result()
    resume_matching = make_resume_match_response()
    error = error_factory()

    if failure_stage == "jd_analysis":
        analyze_mock = Mock(side_effect=error)
        match_mock = Mock()
        generate_mock = Mock()
    elif failure_stage == "resume_matching":
        analyze_mock = Mock(return_value=jd_analysis)
        match_mock = Mock(side_effect=error)
        generate_mock = Mock()
    else:
        analyze_mock = Mock(return_value=jd_analysis)
        match_mock = Mock(return_value=resume_matching)
        generate_mock = Mock(side_effect=error)

    monkeypatch.setattr(main_module, "analyze_jd_with_llm", analyze_mock)
    monkeypatch.setattr(main_module, "match_resume_to_jd", match_mock)
    monkeypatch.setattr(main_module, "generate_learning_plan", generate_mock)
    caplog.set_level(logging.ERROR, logger=main_module.__name__)

    response = client.post(
        "/analyze/learning-plan",
        json={
            "job_description": "有效JD内容",
            "resume_text": "有效简历内容",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    if error_factory is make_rate_limit_error:
        assert (
            "api=analyze_learning_plan "
            f"stage={failure_stage} exception=RateLimitError"
        ) in caplog.messages
        assert "rate limit exceeded" not in "\n".join(caplog.messages)
    else:
        assert not any(
            "api=analyze_learning_plan" in message
            for message in caplog.messages
        )
    if failure_stage == "jd_analysis":
        match_mock.assert_not_called()
        generate_mock.assert_not_called()
    elif failure_stage == "resume_matching":
        generate_mock.assert_not_called()
    else:
        generate_mock.assert_called_once_with(jd_analysis, resume_matching)


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            main_module.LearningPlanInputError("no skills"),
            422,
            "The learning plan input cannot be processed.",
        ),
        (
            main_module.LearningPlanConsistencyError("missing skill"),
            502,
            "The upstream analysis results are inconsistent.",
        ),
    ],
)
def test_learning_plan_maps_domain_errors(
    monkeypatch,
    error,
    expected_status,
    expected_detail,
):
    jd_analysis = make_resume_match_jd_result()
    resume_matching = make_resume_match_response()
    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        Mock(return_value=jd_analysis),
    )
    monkeypatch.setattr(
        main_module,
        "match_resume_to_jd",
        Mock(return_value=resume_matching),
    )
    monkeypatch.setattr(
        main_module,
        "generate_learning_plan",
        Mock(side_effect=error),
    )

    response = client.post(
        "/analyze/learning-plan",
        json={
            "job_description": "有效JD内容",
            "resume_text": "有效简历内容",
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert str(error) not in response.text
