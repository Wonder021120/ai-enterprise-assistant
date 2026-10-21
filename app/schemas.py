from pydantic import BaseModel, Field


class JDAnalysisRequest(BaseModel):
    job_description: str = Field(
        min_length=1,
        description="用户输入的原始招聘 JD"
    )


class JDAnalysisResponse(BaseModel):
    company: str | None = None
    job_title: str | None = None
    location: str | None = None
    recruitment_type: str | None = None
    education: str | None = None
    graduation_requirement: str | None = None
    experience_requirement: str | None = None
    salary: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)

class JDLLMResult(BaseModel):
    job_title: str | None
    required_skills: list[str]
    preferred_skills: list[str]