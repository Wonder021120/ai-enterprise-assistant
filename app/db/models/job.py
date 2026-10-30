from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base


if TYPE_CHECKING:
    from app.db.models.analysis import AnalysisRun, AnalysisSkillMatch
    from app.db.models.learning import LearningPlanItem


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "char_length(source_text) BETWEEN 1 AND 20000",
            name="source_text_length",
        ),
        CheckConstraint(
            "btrim(source_text) <> ''",
            name="source_text_nonblank",
        ),
        CheckConstraint(
            "schema_version >= 1",
            name="schema_version_positive",
        ),
        Index(None, "source_sha256"),
        Index(None, "job_title"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    company: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    recruitment_type: Mapped[str | None] = mapped_column(Text)
    education: Mapped[str | None] = mapped_column(Text)
    graduation_requirement: Mapped[str | None] = mapped_column(Text)
    experience_requirement: Mapped[str | None] = mapped_column(Text)
    salary: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    job_skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(
        back_populates="job",
        passive_deletes="all",
    )


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("normalized_name"),
        CheckConstraint("btrim(name) <> ''", name="name_nonblank"),
        CheckConstraint(
            "btrim(normalized_name) <> ''",
            name="normalized_name_nonblank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    job_skills: Mapped[list[JobSkill]] = relationship(
        back_populates="skill",
        passive_deletes="all",
    )

    @validates("name")
    def derive_normalized_name(self, _key: str, value: str) -> str:
        """Keep the persisted lookup key in sync with the display name."""
        self.normalized_name = value.strip().casefold()
        return value


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (
        UniqueConstraint("job_id", "skill_id"),
        UniqueConstraint("job_id", "skill_category", "position"),
        CheckConstraint(
            "skill_category IN ('required', 'preferred')",
            name="skill_category_allowed",
        ),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(
            "btrim(skill_name_snapshot) <> ''",
            name="skill_name_snapshot_nonblank",
        ),
        Index(None, "skill_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    skill_name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    skill_category: Mapped[str] = mapped_column(String(10), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    job: Mapped[Job] = relationship(back_populates="job_skills")
    skill: Mapped[Skill] = relationship(back_populates="job_skills")
    analysis_skill_matches: Mapped[list[AnalysisSkillMatch]] = relationship(
        back_populates="job_skill",
        passive_deletes="all",
    )
    learning_plan_items: Mapped[list[LearningPlanItem]] = relationship(
        back_populates="job_skill",
        passive_deletes="all",
    )
