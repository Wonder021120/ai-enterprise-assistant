from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db import session as db_session_module
from app.schemas import (
    JDLLMResult,
    LearningPlanItem,
    LearningPlanResponse,
    ResumeMatchingResponse,
    SkillMatchItem,
)


with patch("dotenv.load_dotenv", return_value=False):
    from app.llm_service import LLMOutputError
    from app.services.analysis_workflow_service import (
        AnalysisWorkflowCandidateError,
        AnalysisWorkflowConsistencyError,
        AnalysisWorkflowResult,
    )
    from app import main as main_module


def _id(number: int) -> uuid.UUID:
    return uuid.UUID(int=number)


def _jd_analysis() -> JDLLMResult:
    return JDLLMResult(
        company="Example",
        job_title="Python Engineer",
        location="Shanghai",
        recruitment_type="社招",
        education="本科",
        graduation_requirement=None,
        experience_requirement="2年后端经验",
        salary="20k-30k",
        required_skills=["Python"],
        preferred_skills=["Docker"],
    )


def _resume_matching() -> ResumeMatchingResponse:
    return ResumeMatchingResponse(
        required_skill_matches=[
            SkillMatchItem(
                skill="Python",
                status="evidence_found",
                evidence="使用Python开发API",
            )
        ],
        preferred_skill_matches=[
            SkillMatchItem(
                skill="Docker",
                status="not_found_in_resume",
                evidence=None,
            )
        ],
        match_summary="找到Python项目证据。",
        resume_improvement_suggestions=["补充部署成果"],
        learning_practice_suggestions=["完成容器化练习"],
    )


def _learning_plan() -> LearningPlanResponse:
    return LearningPlanResponse(
        plan_summary="先深化Python，再练习Docker。",
        plan_items=[
            LearningPlanItem(
                skill="Python",
                skill_category="required",
                priority="medium",
                priority_order=1,
                basis="existing_evidence_to_strengthen",
                task_type="project_practice",
                rationale="深化已有实践。",
                learning_objective="提高后端工程质量。",
                action_steps=["补充测试"],
                practice_task="完善现有API。",
                deliverable="代码和测试报告。",
                completion_criteria=["测试通过"],
                estimated_hours=6,
            ),
            LearningPlanItem(
                skill="Docker",
                skill_category="preferred",
                priority="medium",
                priority_order=2,
                basis="resume_evidence_missing",
                task_type="learning",
                rationale="通过实践建立真实证据。",
                learning_objective="掌握服务容器化。",
                action_steps=["编写Dockerfile"],
                practice_task="容器化现有API。",
                deliverable="Dockerfile和部署说明。",
                completion_criteria=["容器可正常启动"],
                estimated_hours=8,
            ),
        ],
    )


def _workflow_result() -> AnalysisWorkflowResult:
    return AnalysisWorkflowResult(
        candidate_id=_id(1),
        resume_id=_id(2),
        job_id=_id(3),
        analysis_run_id=_id(4),
        learning_plan_id=_id(5),
        required_job_skill_ids=(_id(11),),
        preferred_job_skill_ids=(_id(12),),
        analysis_skill_match_ids=(_id(21), _id(22)),
        learning_plan_item_ids=(_id(31), _id(32)),
        jd_analysis=_jd_analysis(),
        resume_matching=_resume_matching(),
        learning_plan=_learning_plan(),
    )


def _request_payload() -> dict[str, str]:
    return {
        "job_description": "招聘Python后端工程师，Docker经验优先。",
        "resume_text": "使用Python开发API。",
        "candidate_id": str(_id(100)),
        "candidate_email": " alice@example.com ",
        "candidate_display_name": "Alice",
        "resume_title": "Backend Resume",
    }


def _rate_limit_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    response = httpx.Response(status_code=429, request=request)
    return main_module.RateLimitError(
        "rate limited",
        response=response,
        body={"error": "rate limited"},
    )


def _connection_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    return main_module.APIConnectionError(request=request)


def _timeout_error():
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    return main_module.APITimeoutError(request=request)


def _api_status_error():
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


@dataclass
class APIHarness:
    client: TestClient
    session: MagicMock
    workflow_class: MagicMock
    workflow: MagicMock


@pytest.fixture
def api_harness(monkeypatch) -> APIHarness:
    session = MagicMock(spec=Session)

    def override_get_db():
        yield session

    workflow = MagicMock()
    workflow.run.return_value = _workflow_result()
    workflow_class = MagicMock(return_value=workflow)
    monkeypatch.setattr(
        main_module,
        "AnalysisWorkflowService",
        workflow_class,
    )
    main_module.app.dependency_overrides[main_module.get_db] = override_get_db

    with TestClient(main_module.app) as client:
        yield APIHarness(
            client=client,
            session=session,
            workflow_class=workflow_class,
            workflow=workflow,
        )

    main_module.app.dependency_overrides.clear()


def test_workflow_api_returns_complete_result(api_harness: APIHarness) -> None:
    response = api_harness.client.post(
        "/analyze/workflow",
        json=_request_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == str(_id(1))
    assert body["resume_id"] == str(_id(2))
    assert body["job_id"] == str(_id(3))
    assert body["analysis_run_id"] == str(_id(4))
    assert body["learning_plan_id"] == str(_id(5))
    assert body["required_job_skill_ids"] == [str(_id(11))]
    assert body["preferred_job_skill_ids"] == [str(_id(12))]
    assert body["analysis_skill_match_ids"] == [
        str(_id(21)),
        str(_id(22)),
    ]
    assert body["learning_plan_item_ids"] == [
        str(_id(31)),
        str(_id(32)),
    ]
    assert body["jd_analysis"] == _jd_analysis().model_dump(mode="json")
    assert body["resume_matching"] == _resume_matching().model_dump(
        mode="json"
    )
    assert body["learning_plan"] == _learning_plan().model_dump(mode="json")


def test_workflow_api_passes_candidate_information_and_calls_once(
    api_harness: APIHarness,
) -> None:
    response = api_harness.client.post(
        "/analyze/workflow",
        json=_request_payload(),
    )

    assert response.status_code == 200
    api_harness.workflow_class.assert_called_once_with(api_harness.session)
    api_harness.workflow.run.assert_called_once_with(
        job_description="招聘Python后端工程师，Docker经验优先。",
        resume_text="使用Python开发API。",
        candidate_id=_id(100),
        candidate_display_name="Alice",
        candidate_email="alice@example.com",
        resume_title="Backend Resume",
    )


def test_workflow_api_does_not_manage_repository_transactions(
    api_harness: APIHarness,
) -> None:
    response = api_harness.client.post(
        "/analyze/workflow",
        json=_request_payload(),
    )

    assert response.status_code == 200
    api_harness.session.add.assert_not_called()
    api_harness.session.add_all.assert_not_called()
    api_harness.session.flush.assert_not_called()
    api_harness.session.commit.assert_not_called()
    api_harness.session.rollback.assert_not_called()
    api_harness.session.close.assert_not_called()


def test_workflow_api_get_db_closes_injected_session_after_request(
    api_harness: APIHarness,
    monkeypatch,
) -> None:
    main_module.app.dependency_overrides.pop(main_module.get_db)
    session_factory = MagicMock(return_value=api_harness.session)
    monkeypatch.setattr(
        db_session_module,
        "get_session_factory",
        MagicMock(return_value=session_factory),
    )

    response = api_harness.client.post(
        "/analyze/workflow",
        json=_request_payload(),
    )

    assert response.status_code == 200
    api_harness.workflow_class.assert_called_once_with(api_harness.session)
    api_harness.session.close.assert_called_once_with()


@pytest.mark.parametrize("missing_field", ["job_description", "resume_text"])
def test_workflow_api_rejects_missing_required_input(
    api_harness: APIHarness,
    missing_field: str,
) -> None:
    payload = _request_payload()
    payload.pop(missing_field)

    response = api_harness.client.post("/analyze/workflow", json=payload)

    assert response.status_code == 422
    api_harness.workflow.run.assert_not_called()


@pytest.mark.parametrize("field", ["job_description", "resume_text"])
@pytest.mark.parametrize("value", ["", " \t\n"])
def test_workflow_api_rejects_empty_or_blank_analysis_text(
    api_harness: APIHarness,
    field: str,
    value: str,
) -> None:
    payload = _request_payload()
    payload[field] = value

    response = api_harness.client.post("/analyze/workflow", json=payload)

    assert response.status_code == 422
    api_harness.workflow.run.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job_description", "J" * 20_001),
        ("resume_text", "R" * 30_001),
    ],
)
def test_workflow_api_rejects_analysis_text_over_limit(
    api_harness: APIHarness,
    field: str,
    value: str,
) -> None:
    payload = _request_payload()
    payload[field] = value

    response = api_harness.client.post("/analyze/workflow", json=payload)

    assert response.status_code == 422
    api_harness.workflow.run.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_email", "not-an-email"),
        ("candidate_display_name", "   "),
        ("resume_title", "\t"),
        ("candidate_display_name", "N" * 201),
        ("resume_title", "T" * 201),
    ],
)
def test_workflow_api_rejects_invalid_candidate_metadata(
    api_harness: APIHarness,
    field: str,
    value: str,
) -> None:
    payload = _request_payload()
    payload[field] = value

    response = api_harness.client.post("/analyze/workflow", json=payload)

    assert response.status_code == 422
    api_harness.workflow.run.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            AnalysisWorkflowCandidateError("candidate lookup failed"),
            422,
            "The candidate information cannot be processed.",
        ),
        (
            AnalysisWorkflowConsistencyError("unmapped skill"),
            502,
            "The workflow analysis results are inconsistent.",
        ),
        (
            LLMOutputError("invalid model output"),
            502,
            "The LLM returned invalid or empty output.",
        ),
        (
            RuntimeError("unexpected internal failure"),
            500,
            "The workflow could not be completed.",
        ),
    ],
)
def test_workflow_api_maps_safe_workflow_errors(
    api_harness: APIHarness,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    error.add_note("analysis_workflow_stage=resume_matching")
    api_harness.workflow.run.side_effect = error

    response = api_harness.client.post(
        "/analyze/workflow",
        json=_request_payload(),
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    ("error_factory", "status_code", "detail"),
    [
        (
            _rate_limit_error,
            503,
            "The LLM provider is temporarily rate-limited. "
            "Please try again later.",
        ),
        (
            _connection_error,
            503,
            "The LLM service is temporarily unavailable. "
            "Please try again later.",
        ),
        (
            _timeout_error,
            503,
            "The LLM service is temporarily unavailable. "
            "Please try again later.",
        ),
        (
            _api_status_error,
            502,
            "The LLM provider returned an error.",
        ),
    ],
)
def test_workflow_api_preserves_existing_sdk_error_mapping(
    api_harness: APIHarness,
    error_factory,
    status_code: int,
    detail: str,
) -> None:
    api_harness.workflow.run.side_effect = error_factory()

    response = api_harness.client.post(
        "/analyze/workflow",
        json=_request_payload(),
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_workflow_api_does_not_leak_integrity_error_details(
    api_harness: APIHarness,
    caplog,
) -> None:
    sensitive_resume = "SECRET_RESUME_CONTENT"
    error = IntegrityError(
        "INSERT INTO resumes (resume_text) VALUES (%(resume_text)s)",
        {"resume_text": sensitive_resume, "password": "SECRET_PASSWORD"},
        Exception("constraint failed"),
    )
    error.add_note("analysis_workflow_stage=learning_plan")
    api_harness.workflow.run.side_effect = error

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = api_harness.client.post(
            "/analyze/workflow",
            json=_request_payload(),
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The workflow conflicts with existing stored data."
    }
    serialized_response = response.text
    assert sensitive_resume not in serialized_response
    assert "SECRET_PASSWORD" not in serialized_response
    assert sensitive_resume not in caplog.text
    assert "SECRET_PASSWORD" not in caplog.text
    assert "INSERT INTO" not in caplog.text


def test_workflow_api_maps_database_connection_failure_without_url_leak(
    api_harness: APIHarness,
    caplog,
) -> None:
    database_url = "postgresql://user:SECRET@localhost/careerpilot_db"
    error = OperationalError(
        "SELECT 1",
        {},
        Exception(database_url),
    )
    api_harness.workflow.run.side_effect = error

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = api_harness.client.post(
            "/analyze/workflow",
            json=_request_payload(),
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The database service is temporarily unavailable."
    }
    assert database_url not in response.text
    assert database_url not in caplog.text


def test_workflow_openapi_uses_explicit_request_and_response_models(
    api_harness: APIHarness,
) -> None:
    operation = main_module.app.openapi()["paths"]["/analyze/workflow"][
        "post"
    ]

    request_schema = operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    response_schema = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert request_schema["$ref"].endswith("/AnalysisWorkflowRequest")
    assert response_schema["$ref"].endswith("/AnalysisWorkflowResponse")


def test_existing_analysis_routes_remain_compatible(
    api_harness: APIHarness,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main_module,
        "analyze_jd_with_llm",
        MagicMock(return_value=_jd_analysis()),
    )
    monkeypatch.setattr(
        main_module,
        "match_resume_to_jd",
        MagicMock(return_value=_resume_matching()),
    )
    monkeypatch.setattr(
        main_module,
        "generate_learning_plan",
        MagicMock(return_value=_learning_plan()),
    )
    analysis_payload = {
        "job_description": "招聘Python工程师",
        "resume_text": "使用Python开发API",
    }

    jd_response = api_harness.client.post(
        "/analyze/jd",
        json={"job_description": analysis_payload["job_description"]},
    )
    matching_response = api_harness.client.post(
        "/analyze/resume-match",
        json=analysis_payload,
    )
    plan_response = api_harness.client.post(
        "/analyze/learning-plan",
        json=analysis_payload,
    )

    assert jd_response.status_code == 200
    assert matching_response.status_code == 200
    assert plan_response.status_code == 200
