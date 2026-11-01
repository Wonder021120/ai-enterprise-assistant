from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, AnalysisSkillMatch, JobSkill


class AnalysisRunRepository:
    """AnalysisRun 生命周期状态和历史查询的数据访问操作。"""

    _UPDATABLE_FIELDS = frozenset(
        {
            "status",
            "current_stage",
            "jd_analysis_output",
            "resume_matching_output",
            "match_summary",
            "resume_improvement_suggestions",
            "learning_practice_suggestions",
            "failure_stage",
            "error_type",
            "error_code",
            "completed_at",
        }
    )

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_analysis_run(
        self,
        *,
        job_id: uuid.UUID,
        run_type: str,
        status: str,
        model_provider: str,
        model_name: str,
        pipeline_version: str,
        resume_id: uuid.UUID | None = None,
        current_stage: str | None = None,
        jd_analysis_output: dict[str, Any] | None = None,
        resume_matching_output: dict[str, Any] | None = None,
        match_summary: str | None = None,
        resume_improvement_suggestions: list[str] | None = None,
        learning_practice_suggestions: list[str] | None = None,
        failure_stage: str | None = None,
        error_type: str | None = None,
        error_code: str | None = None,
        completed_at: datetime | None = None,
    ) -> AnalysisRun:
        analysis_values: dict[str, Any] = {
            "job_id": job_id,
            "resume_id": resume_id,
            "run_type": run_type,
            "status": status,
            "current_stage": current_stage,
            "model_provider": model_provider,
            "model_name": model_name,
            "pipeline_version": pipeline_version,
            "match_summary": match_summary,
            "resume_improvement_suggestions": (
                []
                if resume_improvement_suggestions is None
                else resume_improvement_suggestions
            ),
            "learning_practice_suggestions": (
                []
                if learning_practice_suggestions is None
                else learning_practice_suggestions
            ),
            "failure_stage": failure_stage,
            "error_type": error_type,
            "error_code": error_code,
            "completed_at": completed_at,
        }
        # Explicit Python None becomes JSONB null.  Omit absent object outputs
        # so nullable columns persist SQL NULL instead of violating jsonb_typeof.
        if jd_analysis_output is not None:
            analysis_values["jd_analysis_output"] = jd_analysis_output
        if resume_matching_output is not None:
            analysis_values["resume_matching_output"] = resume_matching_output

        analysis_run = AnalysisRun(**analysis_values)
        self._session.add(analysis_run)
        self._session.flush()
        return analysis_run

    def get_analysis_run_by_id(
        self,
        analysis_run_id: uuid.UUID,
    ) -> AnalysisRun | None:
        statement = select(AnalysisRun).where(
            AnalysisRun.id == analysis_run_id
        )
        return self._session.scalar(statement)

    def list_analysis_runs(
        self,
        *,
        job_id: uuid.UUID | None = None,
        resume_id: uuid.UUID | None = None,
        run_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AnalysisRun]:
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        if offset < 0:
            raise ValueError("offset must not be negative.")

        statement = select(AnalysisRun)
        filters = (
            (AnalysisRun.job_id, job_id),
            (AnalysisRun.resume_id, resume_id),
            (AnalysisRun.run_type, run_type),
            (AnalysisRun.status, status),
        )
        for column, value in filters:
            if value is not None:
                statement = statement.where(column == value)

        statement = (
            statement.order_by(
                AnalysisRun.created_at.desc(),
                AnalysisRun.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement).all())

    def update_analysis_run(
        self,
        analysis_run_id: uuid.UUID,
        **changes: Any,
    ) -> AnalysisRun | None:
        invalid_fields = set(changes).difference(self._UPDATABLE_FIELDS)
        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            raise ValueError(f"AnalysisRun fields cannot be updated: {invalid}")

        analysis_run = self.get_analysis_run_by_id(analysis_run_id)
        if analysis_run is None:
            return None
        if not changes:
            return analysis_run

        for field_name, value in changes.items():
            setattr(analysis_run, field_name, value)

        # Model CHECK constraints remain the source of truth for status/stage.
        self._session.flush()
        return analysis_run


class AnalysisSkillMatchRepository:
    """AnalysisSkillMatch 的写入、一致性校验和查询操作。"""

    _MATCH_FIELDS = frozenset({"job_skill_id", "status", "evidence"})

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_skill_match(
        self,
        *,
        analysis_run_id: uuid.UUID,
        job_skill_id: uuid.UUID,
        status: str,
        evidence: str | None = None,
    ) -> AnalysisSkillMatch:
        analysis_run = self._get_analysis_run_or_raise(analysis_run_id)
        job_skill = self._get_job_skill_or_raise(job_skill_id)
        self._validate_same_job(analysis_run, job_skill)

        skill_match = AnalysisSkillMatch(
            analysis_run_id=analysis_run_id,
            job_skill_id=job_skill_id,
            status=status,
            evidence=evidence,
        )
        self._session.add(skill_match)
        self._session.flush()
        return skill_match

    def create_skill_matches(
        self,
        *,
        analysis_run_id: uuid.UUID,
        matches: Sequence[Mapping[str, Any]],
    ) -> list[AnalysisSkillMatch]:
        if not matches:
            return []

        analysis_run = self._get_analysis_run_or_raise(analysis_run_id)
        prepared: list[tuple[uuid.UUID, str, str | None]] = []
        for match in matches:
            invalid_fields = set(match).difference(self._MATCH_FIELDS)
            if invalid_fields:
                invalid = ", ".join(sorted(invalid_fields))
                raise ValueError(f"Unknown skill match fields: {invalid}")
            if "job_skill_id" not in match or "status" not in match:
                raise ValueError(
                    "Each skill match requires job_skill_id and status."
                )
            prepared.append(
                (
                    match["job_skill_id"],
                    match["status"],
                    match.get("evidence"),
                )
            )

        job_skill_ids = list(dict.fromkeys(item[0] for item in prepared))
        statement = select(JobSkill).where(JobSkill.id.in_(job_skill_ids))
        job_skills = list(self._session.scalars(statement).all())
        job_skills_by_id = {job_skill.id: job_skill for job_skill in job_skills}

        for job_skill_id in job_skill_ids:
            job_skill = job_skills_by_id.get(job_skill_id)
            if job_skill is None:
                raise ValueError("JobSkill does not exist.")
            self._validate_same_job(analysis_run, job_skill)

        skill_matches = [
            AnalysisSkillMatch(
                analysis_run_id=analysis_run_id,
                job_skill_id=job_skill_id,
                status=status,
                evidence=evidence,
            )
            for job_skill_id, status, evidence in prepared
        ]
        self._session.add_all(skill_matches)
        self._session.flush()
        return skill_matches

    def get_skill_match_by_id(
        self,
        skill_match_id: uuid.UUID,
    ) -> AnalysisSkillMatch | None:
        statement = select(AnalysisSkillMatch).where(
            AnalysisSkillMatch.id == skill_match_id
        )
        return self._session.scalar(statement)

    def list_skill_matches(
        self,
        analysis_run_id: uuid.UUID,
        *,
        status: str | None = None,
        skill_category: str | None = None,
    ) -> list[AnalysisSkillMatch]:
        statement = (
            select(AnalysisSkillMatch)
            .join(
                JobSkill,
                AnalysisSkillMatch.job_skill_id == JobSkill.id,
            )
            .where(AnalysisSkillMatch.analysis_run_id == analysis_run_id)
        )
        if status is not None:
            statement = statement.where(
                AnalysisSkillMatch.status == status
            )
        if skill_category is not None:
            statement = statement.where(
                JobSkill.skill_category == skill_category
            )

        statement = statement.order_by(
            JobSkill.skill_category.desc(),
            JobSkill.position,
            AnalysisSkillMatch.id,
        )
        return list(self._session.scalars(statement).all())

    def _get_analysis_run_or_raise(
        self,
        analysis_run_id: uuid.UUID,
    ) -> AnalysisRun:
        statement = select(AnalysisRun).where(
            AnalysisRun.id == analysis_run_id
        )
        analysis_run = self._session.scalar(statement)
        if analysis_run is None:
            raise ValueError("AnalysisRun does not exist.")
        return analysis_run

    def _get_job_skill_or_raise(self, job_skill_id: uuid.UUID) -> JobSkill:
        statement = select(JobSkill).where(JobSkill.id == job_skill_id)
        job_skill = self._session.scalar(statement)
        if job_skill is None:
            raise ValueError("JobSkill does not exist.")
        return job_skill

    @staticmethod
    def _validate_same_job(
        analysis_run: AnalysisRun,
        job_skill: JobSkill,
    ) -> None:
        if analysis_run.job_id != job_skill.job_id:
            raise ValueError(
                "JobSkill does not belong to the AnalysisRun job."
            )
