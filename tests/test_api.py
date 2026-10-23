from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


with patch("dotenv.load_dotenv", return_value=False):
    from app import main as main_module


client = TestClient(main_module.app)


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
        "https://openrouter.ai/api/v1/chat/completions",
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
        "https://openrouter.ai/api/v1/chat/completions",
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
        "https://openrouter.ai/api/v1/chat/completions",
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
        "https://openrouter.ai/api/v1/chat/completions",
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
