
from fastapi import FastAPI, HTTPException
from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    RateLimitError,
)

from app.schemas import JDAnalysisRequest, JDAnalysisResponse
from app.llm_service import analyze_jd_with_llm, LLMOutputError


app = FastAPI(
    title="CareerPilot AI",
    description="An AI job analysis assistant for graduate job seekers.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "CareerPilot AI",
    }


@app.post("/analyze/jd", response_model=JDAnalysisResponse)
def analyze_jd(request: JDAnalysisRequest):
    try:
        result = analyze_jd_with_llm(request.job_description)

    except LLMOutputError as exc:
        raise HTTPException(
            status_code=502,
            detail="The LLM returned invalid or empty output.",
        ) from exc

    except RateLimitError as exc:
        raise HTTPException(
            status_code=503,
            detail="The LLM provider is temporarily rate-limited. Please try again later.",
        ) from exc

    except (APIConnectionError, APITimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The LLM service is temporarily unavailable. Please try again later.",
        ) from exc

    except APIStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="The LLM provider returned an error.",
        ) from exc

    return JDAnalysisResponse(
        company=result.company,
        job_title=result.job_title,
        location=result.location,
        recruitment_type=result.recruitment_type,
        education=result.education,
        graduation_requirement=result.graduation_requirement,
        experience_requirement=result.experience_requirement,
        salary=result.salary,
        required_skills=result.required_skills,
        preferred_skills=result.preferred_skills,
    )
