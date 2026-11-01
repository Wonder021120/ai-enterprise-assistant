from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.llm_service import analyze_jd_with_llm, get_llm_model_name
from app.repositories import (
    AnalysisRunRepository,
    AnalysisSkillMatchRepository,
    CandidateRepository,
    JobRepository,
    JobSkillRepository,
    LearningPlanItemRepository,
    LearningPlanRepository,
    ResumeRepository,
    SkillRepository,
)
from app.schemas import (
    JDLLMResult,
    LearningPlanResponse,
    ResumeMatchingResponse,
    SkillMatchItem,
)
from app.services.learning_plan_service import generate_learning_plan
from app.services.resume_matching_service import match_resume_to_jd


MODEL_PROVIDER = "deepseek"
PIPELINE_VERSION = "1"
SCHEMA_VERSION = 1


class AnalysisWorkflowConsistencyError(ValueError):
    """结构化结果无法与当前分析的数据库记录一一对应。"""


class AnalysisWorkflowCandidateError(ValueError):
    """候选人信息缺失、无效或无法唯一确定。"""


@dataclass(frozen=True)
class WorkflowRepositories:
    """工作流使用的现有 Repository 集合，便于显式依赖注入。"""

    candidates: CandidateRepository
    resumes: ResumeRepository
    jobs: JobRepository
    skills: SkillRepository
    job_skills: JobSkillRepository
    analysis_runs: AnalysisRunRepository
    skill_matches: AnalysisSkillMatchRepository
    learning_plans: LearningPlanRepository
    learning_plan_items: LearningPlanItemRepository

    @classmethod
    def from_session(cls, session: Session) -> WorkflowRepositories:
        return cls(
            candidates=CandidateRepository(session),
            resumes=ResumeRepository(session),
            jobs=JobRepository(session),
            skills=SkillRepository(session),
            job_skills=JobSkillRepository(session),
            analysis_runs=AnalysisRunRepository(session),
            skill_matches=AnalysisSkillMatchRepository(session),
            learning_plans=LearningPlanRepository(session),
            learning_plan_items=LearningPlanItemRepository(session),
        )


@dataclass(frozen=True)
class AnalysisWorkflowResult:
    """完整分析的数据库标识和三个阶段的结构化结果。"""

    candidate_id: uuid.UUID
    resume_id: uuid.UUID
    job_id: uuid.UUID
    analysis_run_id: uuid.UUID
    learning_plan_id: uuid.UUID
    required_job_skill_ids: tuple[uuid.UUID, ...]
    preferred_job_skill_ids: tuple[uuid.UUID, ...]
    analysis_skill_match_ids: tuple[uuid.UUID, ...]
    learning_plan_item_ids: tuple[uuid.UUID, ...]
    jd_analysis: JDLLMResult
    resume_matching: ResumeMatchingResponse
    learning_plan: LearningPlanResponse


@dataclass(frozen=True)
class _JobSkillReference:
    id: uuid.UUID
    category: str
    normalized_name: str


class AnalysisWorkflowService:
    """编排三个 AI 阶段，并通过现有 Repository 持久化结果。"""

    def __init__(
        self,
        session: Session,
        *,
        repositories: WorkflowRepositories | None = None,
        jd_analyzer: Callable[[str], JDLLMResult] | None = None,
        resume_matcher: Callable[
            [JDLLMResult, str], ResumeMatchingResponse
        ]
        | None = None,
        learning_plan_generator: Callable[
            [JDLLMResult, ResumeMatchingResponse], LearningPlanResponse
        ]
        | None = None,
        model_name_getter: Callable[[], str] | None = None,
    ) -> None:
        self._session = session
        self._repositories = repositories or WorkflowRepositories.from_session(
            session
        )
        self._jd_analyzer = jd_analyzer or analyze_jd_with_llm
        self._resume_matcher = resume_matcher or match_resume_to_jd
        self._learning_plan_generator = (
            learning_plan_generator or generate_learning_plan
        )
        self._model_name_getter = model_name_getter or get_llm_model_name

    def run(
        self,
        *,
        job_description: str,
        resume_text: str,
        candidate_id: uuid.UUID | None = None,
        candidate_display_name: str | None = None,
        candidate_email: str | None = None,
        resume_title: str | None = None,
    ) -> AnalysisWorkflowResult:
        analysis_run_id: uuid.UUID | None = None

        try:
            jd_analysis = self._jd_analyzer(job_description)
            self._validate_jd_skills(jd_analysis)
        except Exception as exc:
            self._annotate_exception(exc, "jd_analysis", "analysis")
            raise

        try:
            candidate = self._get_or_create_candidate(
                candidate_id=candidate_id,
                display_name=candidate_display_name,
                email=candidate_email,
            )
            resume_version = self._next_resume_version(candidate.id)
            resume = self._repositories.resumes.create_resume(
                candidate_id=candidate.id,
                resume_text=resume_text,
                content_sha256=self._sha256(resume_text),
                version=resume_version,
                title=resume_title,
                is_current=True,
            )
            job = self._repositories.jobs.create_job(
                source_text=job_description,
                source_sha256=self._sha256(job_description),
                schema_version=SCHEMA_VERSION,
                company=jd_analysis.company,
                job_title=jd_analysis.job_title,
                location=jd_analysis.location,
                recruitment_type=jd_analysis.recruitment_type,
                education=jd_analysis.education,
                graduation_requirement=jd_analysis.graduation_requirement,
                experience_requirement=jd_analysis.experience_requirement,
                salary=jd_analysis.salary,
                analyzed_at=self._utcnow(),
            )
            job_skill_index, required_ids, preferred_ids = (
                self._persist_job_skills(job.id, jd_analysis)
            )
            analysis_run = self._repositories.analysis_runs.create_analysis_run(
                job_id=job.id,
                resume_id=resume.id,
                run_type="learning_plan",
                status="running",
                current_stage="resume_matching",
                model_provider=MODEL_PROVIDER,
                model_name=self._model_name_getter(),
                pipeline_version=PIPELINE_VERSION,
                jd_analysis_output=jd_analysis.model_dump(mode="json"),
            )
            analysis_run_id = analysis_run.id
            self._session.commit()
        except Exception as exc:
            self._rollback_preserving(exc)
            self._annotate_exception(
                exc,
                "jd_analysis",
                self._classify_failure(exc),
            )
            raise

        try:
            resume_matching = self._resume_matcher(jd_analysis, resume_text)
        except Exception as exc:
            self._record_failure(analysis_run_id, "resume_matching", exc)
            raise

        try:
            match_payloads = self._build_skill_match_payloads(
                jd_analysis,
                resume_matching,
                job_skill_index,
            )
            skill_match_records = (
                self._repositories.skill_matches.create_skill_matches(
                    analysis_run_id=analysis_run_id,
                    matches=match_payloads,
                )
            )
            self._require_analysis_run_update(
                analysis_run_id,
                current_stage="learning_plan",
                resume_matching_output=resume_matching.model_dump(mode="json"),
                match_summary=resume_matching.match_summary,
                resume_improvement_suggestions=(
                    resume_matching.resume_improvement_suggestions
                ),
                learning_practice_suggestions=(
                    resume_matching.learning_practice_suggestions
                ),
            )
            self._session.commit()
        except Exception as exc:
            self._record_failure(
                analysis_run_id,
                "resume_matching",
                exc,
                failure_kind=self._classify_failure(exc),
            )
            raise

        try:
            learning_plan = self._learning_plan_generator(
                jd_analysis,
                resume_matching,
            )
        except Exception as exc:
            self._record_failure(analysis_run_id, "learning_plan", exc)
            raise

        try:
            plan_item_payloads = self._build_learning_plan_item_payloads(
                jd_analysis,
                learning_plan,
                job_skill_index,
            )
            learning_plan_record = (
                self._repositories.learning_plans.create_learning_plan(
                    analysis_run_id=analysis_run_id,
                    plan_summary=learning_plan.plan_summary,
                    full_output=learning_plan.model_dump(mode="json"),
                    schema_version=SCHEMA_VERSION,
                )
            )
            plan_item_records = (
                self._repositories.learning_plan_items.create_learning_plan_items(
                    learning_plan_id=learning_plan_record.id,
                    items=plan_item_payloads,
                )
            )
            self._require_analysis_run_update(
                analysis_run_id,
                status="succeeded",
                current_stage="completed",
                completed_at=self._utcnow(),
            )
            self._session.commit()
        except Exception as exc:
            self._record_failure(
                analysis_run_id,
                "learning_plan",
                exc,
                failure_kind=self._classify_failure(exc),
            )
            raise

        return AnalysisWorkflowResult(
            candidate_id=candidate.id,
            resume_id=resume.id,
            job_id=job.id,
            analysis_run_id=analysis_run_id,
            learning_plan_id=learning_plan_record.id,
            required_job_skill_ids=tuple(required_ids),
            preferred_job_skill_ids=tuple(preferred_ids),
            analysis_skill_match_ids=tuple(
                record.id for record in skill_match_records
            ),
            learning_plan_item_ids=tuple(
                record.id for record in plan_item_records
            ),
            jd_analysis=jd_analysis,
            resume_matching=resume_matching,
            learning_plan=learning_plan,
        )

    def _get_or_create_candidate(
        self,
        *,
        candidate_id: uuid.UUID | None,
        display_name: str | None,
        email: str | None,
    ) -> Any:
        if candidate_id is not None:
            candidate = self._repositories.candidates.get_candidate_by_id(
                candidate_id
            )
            if candidate is None:
                raise AnalysisWorkflowCandidateError(
                    "Candidate does not exist."
                )
            return candidate

        if email is not None:
            candidates = self._repositories.candidates.list_candidates(
                email=email
            )
            if len(candidates) > 1:
                raise AnalysisWorkflowCandidateError(
                    "Candidate email does not identify a unique record."
                )
            if candidates:
                return candidates[0]

        return self._repositories.candidates.create_candidate(
            display_name=display_name,
            email=email,
        )

    def _next_resume_version(self, candidate_id: uuid.UUID) -> int:
        current = self._repositories.resumes.get_current_resume(candidate_id)
        history = self._repositories.resumes.list_resume_history(candidate_id)
        versions = [resume.version for resume in history]
        if current is not None:
            versions.append(current.version)
        return max(versions, default=0) + 1

    def _persist_job_skills(
        self,
        job_id: uuid.UUID,
        jd_analysis: JDLLMResult,
    ) -> tuple[
        dict[tuple[str, str], _JobSkillReference],
        list[uuid.UUID],
        list[uuid.UUID],
    ]:
        index: dict[tuple[str, str], _JobSkillReference] = {}
        ids_by_category: dict[str, list[uuid.UUID]] = {
            "required": [],
            "preferred": [],
        }

        for category, skill_names in (
            ("required", jd_analysis.required_skills),
            ("preferred", jd_analysis.preferred_skills),
        ):
            for position, skill_name in enumerate(skill_names, start=1):
                skill = self._repositories.skills.create_skill(name=skill_name)
                job_skill = self._repositories.job_skills.attach_skill_to_job(
                    job_id=job_id,
                    skill_id=skill.id,
                    skill_category=category,
                    position=position,
                )
                normalized_name = self._normalize_skill(skill_name)
                index[(category, normalized_name)] = _JobSkillReference(
                    id=job_skill.id,
                    category=category,
                    normalized_name=normalized_name,
                )
                ids_by_category[category].append(job_skill.id)

        return index, ids_by_category["required"], ids_by_category["preferred"]

    def _build_skill_match_payloads(
        self,
        jd_analysis: JDLLMResult,
        resume_matching: ResumeMatchingResponse,
        job_skill_index: dict[tuple[str, str], _JobSkillReference],
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []

        for category, expected_skills, matches in (
            (
                "required",
                jd_analysis.required_skills,
                resume_matching.required_skill_matches,
            ),
            (
                "preferred",
                jd_analysis.preferred_skills,
                resume_matching.preferred_skill_matches,
            ),
        ):
            indexed_matches = self._index_matches(matches, category)
            expected_keys = [
                self._normalize_skill(skill) for skill in expected_skills
            ]
            if set(indexed_matches) != set(expected_keys):
                raise AnalysisWorkflowConsistencyError(
                    f"{category} skill matches do not match the JD skills."
                )

            for skill_key in expected_keys:
                match = indexed_matches[skill_key]
                job_skill = self._get_job_skill_reference(
                    job_skill_index,
                    category,
                    skill_key,
                )
                payloads.append(
                    {
                        "job_skill_id": job_skill.id,
                        "status": match.status,
                        "evidence": match.evidence,
                    }
                )

        return payloads

    def _build_learning_plan_item_payloads(
        self,
        jd_analysis: JDLLMResult,
        learning_plan: LearningPlanResponse,
        job_skill_index: dict[tuple[str, str], _JobSkillReference],
    ) -> list[dict[str, Any]]:
        expected_keys = {
            (category, self._normalize_skill(skill))
            for category, skills in (
                ("required", jd_analysis.required_skills),
                ("preferred", jd_analysis.preferred_skills),
            )
            for skill in skills
        }
        seen: set[tuple[str, str]] = set()
        payloads: list[dict[str, Any]] = []

        for item in learning_plan.plan_items:
            key = (item.skill_category, self._normalize_skill(item.skill))
            if key in seen:
                raise AnalysisWorkflowConsistencyError(
                    "Learning plan contains duplicate skill tasks."
                )
            if key not in expected_keys:
                raise AnalysisWorkflowConsistencyError(
                    "Learning plan contains an unmapped JD skill."
                )
            seen.add(key)
            job_skill = self._get_job_skill_reference(
                job_skill_index,
                item.skill_category,
                key[1],
            )
            payloads.append(
                {
                    "job_skill_id": job_skill.id,
                    "priority": item.priority,
                    "priority_order": item.priority_order,
                    "basis": item.basis,
                    "task_type": item.task_type,
                    "rationale": item.rationale,
                    "learning_objective": item.learning_objective,
                    "action_steps": item.action_steps,
                    "practice_task": item.practice_task,
                    "deliverable": item.deliverable,
                    "completion_criteria": item.completion_criteria,
                    "estimated_hours": item.estimated_hours,
                }
            )

        if seen != expected_keys:
            raise AnalysisWorkflowConsistencyError(
                "Learning plan is missing one or more JD skill tasks."
            )
        return payloads

    def _record_failure(
        self,
        analysis_run_id: uuid.UUID,
        stage: str,
        original_error: Exception,
        *,
        failure_kind: str = "analysis",
    ) -> None:
        self._annotate_exception(original_error, stage, failure_kind)
        if not self._rollback_preserving(original_error):
            return

        try:
            updated = self._repositories.analysis_runs.update_analysis_run(
                analysis_run_id,
                status="failed",
                current_stage=stage,
                failure_stage=stage,
                error_type=type(original_error).__name__[:100],
                error_code=self._failure_error_code(failure_kind),
                completed_at=self._utcnow(),
            )
            if updated is None:
                raise AnalysisWorkflowConsistencyError(
                    "AnalysisRun disappeared while recording failure."
                )
            self._session.commit()
        except Exception as recording_error:
            self._rollback_preserving(original_error)
            original_error.add_note(
                "analysis_workflow_failure_recording="
                f"{type(recording_error).__name__}"
            )

    def _require_analysis_run_update(
        self,
        analysis_run_id: uuid.UUID,
        **changes: Any,
    ) -> None:
        updated = self._repositories.analysis_runs.update_analysis_run(
            analysis_run_id,
            **changes,
        )
        if updated is None:
            raise AnalysisWorkflowConsistencyError(
                "AnalysisRun does not exist."
            )

    @classmethod
    def _validate_jd_skills(cls, jd_analysis: JDLLMResult) -> None:
        seen: set[str] = set()
        for skill in (
            jd_analysis.required_skills + jd_analysis.preferred_skills
        ):
            normalized = cls._normalize_skill(skill)
            if not normalized:
                raise AnalysisWorkflowConsistencyError(
                    "JD contains a blank skill name."
                )
            if normalized in seen:
                raise AnalysisWorkflowConsistencyError(
                    "JD contains duplicate skills after normalization."
                )
            seen.add(normalized)

    @classmethod
    def _index_matches(
        cls,
        matches: list[SkillMatchItem],
        category: str,
    ) -> dict[str, SkillMatchItem]:
        indexed: dict[str, SkillMatchItem] = {}
        for match in matches:
            key = cls._normalize_skill(match.skill)
            if key in indexed:
                raise AnalysisWorkflowConsistencyError(
                    f"{category} skill matches contain duplicates."
                )
            indexed[key] = match
        return indexed

    @staticmethod
    def _get_job_skill_reference(
        index: dict[tuple[str, str], _JobSkillReference],
        category: str,
        normalized_name: str,
    ) -> _JobSkillReference:
        reference = index.get((category, normalized_name))
        if reference is None:
            raise AnalysisWorkflowConsistencyError(
                "Structured output contains an unmapped skill."
            )
        return reference

    @staticmethod
    def _normalize_skill(skill: str) -> str:
        return SkillRepository.normalize_name(skill)

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _annotate_exception(
        error: Exception,
        stage: str,
        failure_kind: str,
    ) -> None:
        error.add_note(f"analysis_workflow_stage={stage}")
        error.add_note(f"analysis_workflow_failure_kind={failure_kind}")

    def _rollback_preserving(self, original_error: Exception) -> bool:
        try:
            self._session.rollback()
        except Exception as rollback_error:
            original_error.add_note(
                "analysis_workflow_rollback="
                f"{type(rollback_error).__name__}"
            )
            return False
        return True

    @staticmethod
    def _classify_failure(error: Exception) -> str:
        if isinstance(error, AnalysisWorkflowConsistencyError):
            return "skill_mapping"
        if isinstance(error, AnalysisWorkflowCandidateError):
            return "candidate_resolution"
        if isinstance(error, SQLAlchemyError):
            return "database_persistence"
        return "persistence"

    @staticmethod
    def _failure_error_code(failure_kind: str) -> str:
        return {
            "analysis": "analysis_failed",
            "candidate_resolution": "candidate_resolution_failed",
            "database_persistence": "database_persistence_failed",
            "skill_mapping": "skill_mapping_failed",
        }.get(failure_kind, "persistence_failed")


def run_analysis_workflow(
    session: Session,
    *,
    job_description: str,
    resume_text: str,
    candidate_id: uuid.UUID | None = None,
    candidate_display_name: str | None = None,
    candidate_email: str | None = None,
    resume_title: str | None = None,
) -> AnalysisWorkflowResult:
    """使用默认依赖执行一次完整的三阶段分析工作流。"""

    return AnalysisWorkflowService(session).run(
        job_description=job_description,
        resume_text=resume_text,
        candidate_id=candidate_id,
        candidate_display_name=candidate_display_name,
        candidate_email=candidate_email,
        resume_title=resume_title,
    )
