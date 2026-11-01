from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job, JobSkill, Skill


class JobSkillRepository:
    """Job 与 Skill 关联记录的数据访问操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def attach_skill_to_job(
        self,
        *,
        job_id: uuid.UUID,
        skill_id: uuid.UUID,
        skill_category: str,
        position: int,
    ) -> JobSkill:
        job = self._session.scalar(select(Job).where(Job.id == job_id))
        if job is None:
            raise ValueError("Job does not exist.")

        skill = self._session.scalar(
            select(Skill).where(Skill.id == skill_id)
        )
        if skill is None:
            raise ValueError("Skill does not exist.")

        job_skill = JobSkill(
            job_id=job_id,
            skill_id=skill_id,
            skill_name_snapshot=skill.name,
            skill_category=skill_category,
            position=position,
        )
        self._session.add(job_skill)
        # Foreign keys, both unique constraints, category and position checks
        # are deliberately enforced by the database during flush.
        self._session.flush()
        return job_skill

    def get_job_skill_by_id(
        self,
        job_skill_id: uuid.UUID,
    ) -> JobSkill | None:
        statement = select(JobSkill).where(JobSkill.id == job_skill_id)
        return self._session.scalar(statement)

    def list_job_skills(
        self,
        job_id: uuid.UUID,
        *,
        skill_category: str | None = None,
    ) -> list[JobSkill]:
        statement = select(JobSkill).where(JobSkill.job_id == job_id)
        if skill_category is not None:
            statement = statement.where(
                JobSkill.skill_category == skill_category
            )

        statement = statement.order_by(JobSkill.position, JobSkill.id)
        return list(self._session.scalars(statement).all())
