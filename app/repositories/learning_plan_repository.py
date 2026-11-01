from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, JobSkill, LearningPlan, LearningPlanItem


class LearningPlanRepository:
    """LearningPlan 主记录的数据访问操作。"""

    _UPDATABLE_FIELDS = frozenset(
        {"plan_summary", "full_output", "schema_version"}
    )

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_learning_plan(
        self,
        *,
        analysis_run_id: uuid.UUID,
        plan_summary: str,
        full_output: dict[str, Any],
        schema_version: int,
    ) -> LearningPlan:
        analysis_run = self._session.scalar(
            select(AnalysisRun).where(AnalysisRun.id == analysis_run_id)
        )
        if analysis_run is None:
            raise ValueError("AnalysisRun does not exist.")

        learning_plan = LearningPlan(
            analysis_run_id=analysis_run_id,
            plan_summary=plan_summary,
            full_output=full_output,
            schema_version=schema_version,
        )
        self._session.add(learning_plan)
        # The unique analysis_run_id constraint remains the final duplicate
        # guard.  IntegrityError intentionally propagates to the caller.
        self._session.flush()
        return learning_plan

    def get_learning_plan_by_id(
        self,
        learning_plan_id: uuid.UUID,
    ) -> LearningPlan | None:
        statement = select(LearningPlan).where(
            LearningPlan.id == learning_plan_id
        )
        return self._session.scalar(statement)

    def get_learning_plan_by_analysis_run_id(
        self,
        analysis_run_id: uuid.UUID,
    ) -> LearningPlan | None:
        statement = select(LearningPlan).where(
            LearningPlan.analysis_run_id == analysis_run_id
        )
        return self._session.scalar(statement)

    def update_learning_plan(
        self,
        learning_plan_id: uuid.UUID,
        **changes: Any,
    ) -> LearningPlan | None:
        invalid_fields = set(changes).difference(self._UPDATABLE_FIELDS)
        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            raise ValueError(f"LearningPlan fields cannot be updated: {invalid}")

        learning_plan = self.get_learning_plan_by_id(learning_plan_id)
        if learning_plan is None:
            return None
        if not changes:
            return learning_plan

        for field_name, value in changes.items():
            setattr(learning_plan, field_name, value)

        self._session.flush()
        return learning_plan

    def list_learning_plans(
        self,
        *,
        analysis_run_id: uuid.UUID | None = None,
        schema_version: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LearningPlan]:
        self._validate_pagination(limit, offset)

        statement = select(LearningPlan)
        if analysis_run_id is not None:
            statement = statement.where(
                LearningPlan.analysis_run_id == analysis_run_id
            )
        if schema_version is not None:
            statement = statement.where(
                LearningPlan.schema_version == schema_version
            )

        statement = (
            statement.order_by(
                LearningPlan.created_at.desc(),
                LearningPlan.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement).all())

    @staticmethod
    def _validate_pagination(limit: int, offset: int) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        if offset < 0:
            raise ValueError("offset must not be negative.")


class LearningPlanItemRepository:
    """LearningPlanItem 的写入、一致性校验和查询操作。"""

    _ITEM_FIELDS = frozenset(
        {
            "job_skill_id",
            "priority",
            "priority_order",
            "basis",
            "task_type",
            "rationale",
            "learning_objective",
            "action_steps",
            "practice_task",
            "deliverable",
            "completion_criteria",
            "estimated_hours",
        }
    )

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_learning_plan_item(
        self,
        *,
        learning_plan_id: uuid.UUID,
        job_skill_id: uuid.UUID,
        priority: str,
        priority_order: int,
        basis: str,
        task_type: str,
        rationale: str,
        learning_objective: str,
        action_steps: list[str],
        practice_task: str,
        deliverable: str,
        completion_criteria: list[str],
        estimated_hours: int,
    ) -> LearningPlanItem:
        analysis_run = self._get_plan_analysis_run_or_raise(learning_plan_id)
        job_skill = self._get_job_skill_or_raise(job_skill_id)
        self._validate_same_job(analysis_run, job_skill)

        item = LearningPlanItem(
            learning_plan_id=learning_plan_id,
            job_skill_id=job_skill_id,
            priority=priority,
            priority_order=priority_order,
            basis=basis,
            task_type=task_type,
            rationale=rationale,
            learning_objective=learning_objective,
            action_steps=action_steps,
            practice_task=practice_task,
            deliverable=deliverable,
            completion_criteria=completion_criteria,
            estimated_hours=estimated_hours,
        )
        self._session.add(item)
        self._session.flush()
        return item

    def create_learning_plan_items(
        self,
        *,
        learning_plan_id: uuid.UUID,
        items: Sequence[Mapping[str, Any]],
    ) -> list[LearningPlanItem]:
        analysis_run = self._get_plan_analysis_run_or_raise(learning_plan_id)
        prepared = [self._prepare_item_data(item) for item in items]
        if not prepared:
            return []

        job_skill_ids = list(
            dict.fromkeys(item["job_skill_id"] for item in prepared)
        )
        statement = select(JobSkill).where(JobSkill.id.in_(job_skill_ids))
        job_skills = list(self._session.scalars(statement).all())
        job_skills_by_id = {job_skill.id: job_skill for job_skill in job_skills}

        for job_skill_id in job_skill_ids:
            job_skill = job_skills_by_id.get(job_skill_id)
            if job_skill is None:
                raise ValueError("JobSkill does not exist.")
            self._validate_same_job(analysis_run, job_skill)

        learning_plan_items = [
            LearningPlanItem(learning_plan_id=learning_plan_id, **item)
            for item in prepared
        ]
        self._session.add_all(learning_plan_items)
        # CHECK and both unique constraints are intentionally enforced here.
        self._session.flush()
        return learning_plan_items

    def get_learning_plan_item_by_id(
        self,
        learning_plan_item_id: uuid.UUID,
    ) -> LearningPlanItem | None:
        statement = select(LearningPlanItem).where(
            LearningPlanItem.id == learning_plan_item_id
        )
        return self._session.scalar(statement)

    def list_learning_plan_items(
        self,
        learning_plan_id: uuid.UUID,
        *,
        priority: str | None = None,
        job_skill_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LearningPlanItem]:
        LearningPlanRepository._validate_pagination(limit, offset)

        statement = select(LearningPlanItem).where(
            LearningPlanItem.learning_plan_id == learning_plan_id
        )
        if priority is not None:
            statement = statement.where(
                LearningPlanItem.priority == priority
            )
        if job_skill_id is not None:
            statement = statement.where(
                LearningPlanItem.job_skill_id == job_skill_id
            )

        statement = (
            statement.order_by(
                LearningPlanItem.priority_order,
                LearningPlanItem.id,
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(statement).all())

    def _get_plan_analysis_run_or_raise(
        self,
        learning_plan_id: uuid.UUID,
    ) -> AnalysisRun:
        learning_plan = self._session.scalar(
            select(LearningPlan).where(LearningPlan.id == learning_plan_id)
        )
        if learning_plan is None:
            raise ValueError("LearningPlan does not exist.")

        analysis_run = self._session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.id == learning_plan.analysis_run_id
            )
        )
        if analysis_run is None:
            raise ValueError("AnalysisRun does not exist.")
        return analysis_run

    def _get_job_skill_or_raise(self, job_skill_id: uuid.UUID) -> JobSkill:
        job_skill = self._session.scalar(
            select(JobSkill).where(JobSkill.id == job_skill_id)
        )
        if job_skill is None:
            raise ValueError("JobSkill does not exist.")
        return job_skill

    def _prepare_item_data(
        self,
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        invalid_fields = set(item).difference(self._ITEM_FIELDS)
        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            raise ValueError(f"Unknown learning plan item fields: {invalid}")

        missing_fields = self._ITEM_FIELDS.difference(item)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Missing learning plan item fields: {missing}")
        return dict(item)

    @staticmethod
    def _validate_same_job(
        analysis_run: AnalysisRun,
        job_skill: JobSkill,
    ) -> None:
        if analysis_run.job_id != job_skill.job_id:
            raise ValueError(
                "JobSkill does not belong to the LearningPlan job."
            )
