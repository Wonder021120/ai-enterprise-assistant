from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job


class JobRepository:
    """Job 的 SQLAlchemy 数据访问操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job(
        self,
        *,
        source_text: str,
        source_sha256: str,
        schema_version: int,
        company: str | None = None,
        job_title: str | None = None,
        location: str | None = None,
        recruitment_type: str | None = None,
        education: str | None = None,
        graduation_requirement: str | None = None,
        experience_requirement: str | None = None,
        salary: str | None = None,
        analyzed_at: datetime | None = None,
    ) -> Job:
        job = Job(
            source_text=source_text,
            source_sha256=source_sha256,
            company=company,
            job_title=job_title,
            location=location,
            recruitment_type=recruitment_type,
            education=education,
            graduation_requirement=graduation_requirement,
            experience_requirement=experience_requirement,
            salary=salary,
            schema_version=schema_version,
            analyzed_at=analyzed_at,
        )
        self._session.add(job)
        self._session.flush()
        return job

    def get_job_by_id(self, job_id: uuid.UUID) -> Job | None:
        statement = select(Job).where(Job.id == job_id)
        return self._session.scalar(statement)

    def list_jobs(
        self,
        *,
        company: str | None = None,
        job_title: str | None = None,
        location: str | None = None,
        recruitment_type: str | None = None,
        education: str | None = None,
        schema_version: int | None = None,
    ) -> list[Job]:
        statement = select(Job)
        filters = (
            (Job.company, company),
            (Job.job_title, job_title),
            (Job.location, location),
            (Job.recruitment_type, recruitment_type),
            (Job.education, education),
            (Job.schema_version, schema_version),
        )
        for column, value in filters:
            if value is not None:
                statement = statement.where(column == value)

        statement = statement.order_by(Job.created_at.desc(), Job.id)
        return list(self._session.scalars(statement).all())

    def find_jobs_by_source_sha256(self, source_sha256: str) -> list[Job]:
        statement = (
            select(Job)
            .where(Job.source_sha256 == source_sha256)
            .order_by(Job.created_at.desc(), Job.id)
        )
        return list(self._session.scalars(statement).all())
