from pydantic import BaseModel, Field, field_validator, model_validator


class JDAnalysisRequest(BaseModel):
    job_description: str = Field(
        min_length=1,
        max_length=20_000,
        description="用户输入的原始招聘 JD"
    )

    @field_validator("job_description")
    @classmethod
    def reject_blank_job_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "job_description must contain non-whitespace characters"
            )
        return value


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
    company: str | None
    job_title: str | None
    location: str | None
    recruitment_type: str | None
    education: str | None
    graduation_requirement: str | None
    experience_requirement: str | None
    salary: str | None
    required_skills: list[str]
    preferred_skills: list[str]

    @model_validator(mode="after")
    def normalize_skill_lists(self) -> "JDLLMResult":
        def deduplicate(skills: list[str]) -> list[str]:
            seen = set()
            unique_skills = []

            for skill in skills:
                comparison_key = skill.casefold()
                if comparison_key in seen:
                    continue

                seen.add(comparison_key)
                unique_skills.append(skill)

            return unique_skills

        self.required_skills = deduplicate(self.required_skills)
        required_skill_keys = {
            skill.casefold() for skill in self.required_skills
        }
        self.preferred_skills = [
            skill
            for skill in deduplicate(self.preferred_skills)
            if skill.casefold() not in required_skill_keys
        ]

        return self
