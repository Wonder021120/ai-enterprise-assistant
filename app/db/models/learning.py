from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.db.models.analysis import AnalysisRun
    from app.db.models.job import JobSkill


class LearningPlan(Base):
    __tablename__ = "learning_plans"
    __table_args__ = (
        UniqueConstraint("analysis_run_id"),
        CheckConstraint(
            "btrim(plan_summary) <> ''",
            name="plan_summary_nonblank",
        ),
        CheckConstraint(
            "schema_version >= 1",
            name="schema_version_positive",
        ),
        CheckConstraint(
            "jsonb_typeof(full_output) = 'object'",
            name="full_output_object",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    full_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    analysis_run: Mapped[AnalysisRun] = relationship(
        back_populates="learning_plan"
    )
    items: Mapped[list[LearningPlanItem]] = relationship(
        back_populates="learning_plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LearningPlanItem(Base):
    __tablename__ = "learning_plan_items"
    __table_args__ = (
        UniqueConstraint("learning_plan_id", "job_skill_id"),
        UniqueConstraint("learning_plan_id", "priority_order"),
        CheckConstraint(
            "priority IN ('high', 'medium', 'low')",
            name="priority_allowed",
        ),
        CheckConstraint(
            "priority_order >= 1",
            name="priority_order_positive",
        ),
        CheckConstraint(
            "basis IN ('resume_evidence_missing', "
            "'existing_evidence_to_strengthen')",
            name="basis_allowed",
        ),
        CheckConstraint(
            "task_type IN ('learning', 'project_practice', "
            "'resume_revision')",
            name="task_type_allowed",
        ),
        CheckConstraint(
            "estimated_hours BETWEEN 1 AND 40",
            name="estimated_hours_range",
        ),
        CheckConstraint(
            "btrim(rationale) <> ''",
            name="rationale_nonblank",
        ),
        CheckConstraint(
            "btrim(learning_objective) <> ''",
            name="learning_objective_nonblank",
        ),
        CheckConstraint(
            "btrim(practice_task) <> ''",
            name="practice_task_nonblank",
        ),
        CheckConstraint(
            "btrim(deliverable) <> ''",
            name="deliverable_nonblank",
        ),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(action_steps) = 'array' "
            "THEN jsonb_array_length(action_steps) BETWEEN 1 AND 8 "
            "ELSE FALSE END",
            name="action_steps_array_length",
        ),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(completion_criteria) = 'array' "
            "THEN jsonb_array_length(completion_criteria) BETWEEN 1 AND 8 "
            "ELSE FALSE END",
            name="completion_criteria_array_length",
        ),
        Index(None, "job_skill_id"),
        Index(None, "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    learning_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    priority_order: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    basis: Mapped[str] = mapped_column(String(50), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)
    learning_objective: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    action_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    practice_task: Mapped[str] = mapped_column(String(500), nullable=False)
    deliverable: Mapped[str] = mapped_column(String(500), nullable=False)
    completion_criteria: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )
    estimated_hours: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    learning_plan: Mapped[LearningPlan] = relationship(
        back_populates="items"
    )
    job_skill: Mapped[JobSkill] = relationship(
        back_populates="learning_plan_items"
    )
