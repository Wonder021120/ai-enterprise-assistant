from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.db.models.candidate import Resume
    from app.db.models.job import Job, JobSkill
    from app.db.models.learning import LearningPlan


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('jd_analysis', 'resume_matching', 'learning_plan')",
            name="run_type_allowed",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint(
            "current_stage IS NULL OR current_stage IN "
            "('jd_analysis', 'resume_matching', 'learning_plan', 'completed')",
            name="current_stage_allowed",
        ),
        CheckConstraint(
            "failure_stage IS NULL OR failure_stage IN "
            "('jd_analysis', 'resume_matching', 'learning_plan')",
            name="failure_stage_allowed",
        ),
        CheckConstraint(
            "jd_analysis_output IS NULL OR "
            "jsonb_typeof(jd_analysis_output) = 'object'",
            name="jd_analysis_output_object",
        ),
        CheckConstraint(
            "resume_matching_output IS NULL OR "
            "jsonb_typeof(resume_matching_output) = 'object'",
            name="resume_matching_output_object",
        ),
        CheckConstraint(
            "resume_improvement_suggestions IS NULL OR "
            "jsonb_typeof(resume_improvement_suggestions) = 'array'",
            name="resume_improvement_suggestions_array",
        ),
        CheckConstraint(
            "learning_practice_suggestions IS NULL OR "
            "jsonb_typeof(learning_practice_suggestions) = 'array'",
            name="learning_practice_suggestions_array",
        ),
        CheckConstraint(
            "run_type = 'jd_analysis' OR resume_id IS NOT NULL",
            name="resume_required_for_pipeline_run",
        ),
        Index(
            "ix_analysis_runs_job_id_created_at_desc",
            "job_id",
            sql_text("created_at DESC"),
        ),
        Index(
            "ix_analysis_runs_resume_id_created_at_desc",
            "resume_id",
            sql_text("created_at DESC"),
        ),
        Index(
            "ix_analysis_runs_run_type_created_at_desc",
            "run_type",
            sql_text("created_at DESC"),
        ),
        Index(
            "ix_analysis_runs_status_created_at_desc",
            "status",
            sql_text("created_at DESC"),
        ),
        Index(None, "failure_stage", "error_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(32))
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    jd_analysis_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resume_matching_output: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB
    )
    match_summary: Mapped[str | None] = mapped_column(Text)
    resume_improvement_suggestions: Mapped[list[str] | None] = mapped_column(
        JSONB
    )
    learning_practice_suggestions: Mapped[list[str] | None] = mapped_column(
        JSONB
    )
    failure_stage: Mapped[str | None] = mapped_column(String(32))
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    job: Mapped[Job] = relationship(back_populates="analysis_runs")
    resume: Mapped[Resume | None] = relationship(
        back_populates="analysis_runs"
    )
    skill_matches: Mapped[list[AnalysisSkillMatch]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    learning_plan: Mapped[LearningPlan | None] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class AnalysisSkillMatch(Base):
    __tablename__ = "analysis_skill_matches"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "job_skill_id"),
        CheckConstraint(
            "status IN ('evidence_found', 'not_found_in_resume')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(status = 'evidence_found' AND evidence IS NOT NULL "
            "AND btrim(evidence) <> '') OR "
            "(status = 'not_found_in_resume' AND evidence IS NULL)",
            name="evidence_matches_status",
        ),
        Index(None, "job_skill_id"),
        Index(None, "status"),
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
    job_skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    analysis_run: Mapped[AnalysisRun] = relationship(
        back_populates="skill_matches"
    )
    job_skill: Mapped[JobSkill] = relationship(
        back_populates="analysis_skill_matches"
    )
