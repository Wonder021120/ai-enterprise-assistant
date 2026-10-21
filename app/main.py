from fastapi import FastAPI
from app.schemas import JDAnalysisRequest, JDAnalysisResponse
from app.llm_service import analyze_jd_with_llm

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
    result = analyze_jd_with_llm(request.job_description)

    return JDAnalysisResponse(
        job_title=result.job_title,
        required_skills=result.required_skills,
        preferred_skills=result.preferred_skills,
    )