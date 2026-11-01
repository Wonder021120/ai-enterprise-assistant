from typing import Literal
from uuid import UUID

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


class ResumeMatchingRequest(BaseModel):
    job_description: str = Field(min_length=1, max_length=20_000)
    resume_text: str = Field(min_length=1, max_length=30_000)

    @field_validator("job_description", "resume_text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace characters")
        return value


class SkillMatchItem(BaseModel):
    skill: str = Field(min_length=1)
    status: Literal["evidence_found", "not_found_in_resume"]
    evidence: str | None = None

    @field_validator("skill")
    @classmethod
    def reject_blank_skill(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("skill must contain non-whitespace characters")
        return value

    @model_validator(mode="after")
    def validate_evidence_for_status(self) -> "SkillMatchItem":
        if self.status == "evidence_found":
            if self.evidence is None or not self.evidence.strip():
                raise ValueError(
                    "evidence_found status requires non-blank evidence"
                )
        elif self.evidence is not None:
            raise ValueError(
                "not_found_in_resume status requires evidence to be None"
            )

        return self


class ResumeMatchingResponse(BaseModel):
    required_skill_matches: list[SkillMatchItem] = Field(
        default_factory=list
    )
    preferred_skill_matches: list[SkillMatchItem] = Field(
        default_factory=list
    )
    match_summary: str
    resume_improvement_suggestions: list[str] = Field(
        default_factory=list
    )
    learning_practice_suggestions: list[str] = Field(
        default_factory=list
    )


class LearningPlanItem(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    skill_category: Literal["required", "preferred"]
    priority: Literal["high", "medium", "low"]
    priority_order: int = Field(ge=1)
    basis: Literal[
        "resume_evidence_missing",
        "existing_evidence_to_strengthen",
    ]
    task_type: Literal[
        "learning",
        "project_practice",
        "resume_revision",
    ]
    rationale: str = Field(min_length=1, max_length=500)
    learning_objective: str = Field(min_length=1, max_length=500)
    action_steps: list[str] = Field(min_length=1, max_length=8)
    practice_task: str = Field(min_length=1, max_length=500)
    deliverable: str = Field(min_length=1, max_length=500)
    completion_criteria: list[str] = Field(min_length=1, max_length=8)
    estimated_hours: int = Field(ge=1, le=40)

    @field_validator(
        "skill",
        "rationale",
        "learning_objective",
        "practice_task",
        "deliverable",
    )
    @classmethod
    def reject_blank_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace characters")
        return value

    @field_validator("action_steps", "completion_criteria")
    @classmethod
    def validate_list_items(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError(
                    "list items must contain non-whitespace characters"
                )
            if len(value) > 300:
                raise ValueError(
                    "list items must contain at most 300 characters"
                )
        return values


class LearningPlanResponse(BaseModel):
    plan_summary: str = Field(min_length=1, max_length=1_000)
    plan_items: list[LearningPlanItem] = Field(
        min_length=1,
        max_length=20,
    )

    @field_validator("plan_summary")
    @classmethod
    def reject_blank_plan_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "plan_summary must contain non-whitespace characters"
            )
        return value

    @model_validator(mode="after")
    def validate_unique_plan_items(self) -> "LearningPlanResponse":
        skill_keys = set()
        priority_orders = set()

        for item in self.plan_items:
            skill_key = item.skill.strip().casefold()
            if skill_key in skill_keys:
                raise ValueError(
                    "plan_items must not contain duplicate skills"
                )
            skill_keys.add(skill_key)

            if item.priority_order in priority_orders:
                raise ValueError(
                    "plan_items must not contain duplicate priority_order"
                )
            priority_orders.add(item.priority_order)

        return self


class AnalysisWorkflowRequest(ResumeMatchingRequest):
    candidate_id: UUID | None = None
    candidate_email: str | None = Field(
        default=None,
        min_length=3,
        max_length=320,
    )
    candidate_display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    resume_title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    @field_validator("candidate_email")
    @classmethod
    def validate_candidate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        local_part, separator, domain = normalized.partition("@")
        if (
            not local_part
            or separator != "@"
            or not domain
            or "@" in domain
            or any(character.isspace() for character in normalized)
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("candidate_email must be a valid email address")
        return normalized

    @field_validator("candidate_display_name", "resume_title")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("text must contain non-whitespace characters")
        return value


class AnalysisWorkflowResponse(BaseModel):
    candidate_id: UUID
    resume_id: UUID
    job_id: UUID
    analysis_run_id: UUID
    learning_plan_id: UUID
    required_job_skill_ids: list[UUID]
    preferred_job_skill_ids: list[UUID]
    analysis_skill_match_ids: list[UUID]
    learning_plan_item_ids: list[UUID]
    jd_analysis: JDLLMResult
    resume_matching: ResumeMatchingResponse
    learning_plan: LearningPlanResponse
