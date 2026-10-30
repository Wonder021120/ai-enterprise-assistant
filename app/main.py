
import logging

from fastapi import FastAPI, HTTPException
from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    RateLimitError,
)

from app.schemas import (
    JDAnalysisRequest,
    JDAnalysisResponse,
    LearningPlanResponse,
    ResumeMatchingRequest,
    ResumeMatchingResponse,
)
from app.llm_service import analyze_jd_with_llm, LLMOutputError
from app.services.learning_plan_service import (
    LearningPlanConsistencyError,
    LearningPlanInputError,
    generate_learning_plan,
)
from app.services.resume_matching_service import match_resume_to_jd


logger = logging.getLogger(__name__)


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


@app.post(
    "/analyze/resume-match",
    response_model=ResumeMatchingResponse,
)
def analyze_resume_match(
    request: ResumeMatchingRequest,
) -> ResumeMatchingResponse:
    try:
        try:
            jd_analysis = analyze_jd_with_llm(request.job_description)
        except LLMOutputError as exc:
            logger.error(
                "resume_match stage=jd_analysis llm_output_error=%s",
                exc,
            )
            raise

        try:
            return match_resume_to_jd(jd_analysis, request.resume_text)
        except LLMOutputError as exc:
            logger.error(
                "resume_match stage=resume_matching llm_output_error=%s",
                exc,
            )
            raise

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


@app.post(
    "/analyze/learning-plan",
    response_model=LearningPlanResponse,
)
def analyze_learning_plan(
    request: ResumeMatchingRequest,
) -> LearningPlanResponse:
    stage = "jd_analysis"

    try:
        jd_analysis = analyze_jd_with_llm(request.job_description)

        stage = "resume_matching"
        resume_matching = match_resume_to_jd(
            jd_analysis,
            request.resume_text,
        )

        stage = "learning_plan"
        return generate_learning_plan(jd_analysis, resume_matching)

    except LearningPlanInputError as exc:
        raise HTTPException(
            status_code=422,
            detail="The learning plan input cannot be processed.",
        ) from exc

    except LearningPlanConsistencyError as exc:
        raise HTTPException(
            status_code=502,
            detail="The upstream analysis results are inconsistent.",
        ) from exc

    except LLMOutputError as exc:
        logger.error(
            "api=analyze_learning_plan stage=%s exception=%s",
            stage,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The LLM returned invalid or empty output.",
        ) from exc

    except RateLimitError as exc:
        logger.error(
            "api=analyze_learning_plan stage=%s exception=%s",
            stage,
            type(exc).__name__,
        )
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
