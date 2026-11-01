from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Resume


class ResumeRepository:
    """Resume 的查询和版本状态写入操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_resume(
        self,
        *,
        candidate_id: uuid.UUID,
        resume_text: str,
        content_sha256: str,
        version: int,
        title: str | None = None,
        is_current: bool = False,
    ) -> Resume:
        if is_current:
            self._deactivate_current_resume(candidate_id)

        resume = Resume(
            candidate_id=candidate_id,
            title=title,
            resume_text=resume_text,
            content_sha256=content_sha256,
            version=version,
            is_current=is_current,
        )
        self._session.add(resume)
        self._session.flush()
        return resume

    def get_resume_by_id(self, resume_id: uuid.UUID) -> Resume | None:
        statement = select(Resume).where(Resume.id == resume_id)
        return self._session.scalar(statement)

    def get_current_resume(
        self,
        candidate_id: uuid.UUID,
    ) -> Resume | None:
        statement = select(Resume).where(
            Resume.candidate_id == candidate_id,
            Resume.is_current.is_(True),
        )
        return self._session.scalar(statement)

    def list_resume_history(
        self,
        candidate_id: uuid.UUID,
    ) -> list[Resume]:
        statement = (
            select(Resume)
            .where(
                Resume.candidate_id == candidate_id,
                Resume.is_current.is_(False),
            )
            .order_by(Resume.version.desc(), Resume.created_at.desc())
        )
        return list(self._session.scalars(statement).all())

    def set_current_resume(
        self,
        *,
        candidate_id: uuid.UUID,
        resume_id: uuid.UUID,
    ) -> Resume | None:
        resume = self.get_resume_by_id(resume_id)
        if resume is None:
            return None
        if resume.candidate_id != candidate_id:
            raise ValueError("Resume does not belong to the candidate.")
        if resume.is_current:
            return resume

        self._deactivate_current_resume(candidate_id)
        resume.is_current = True
        self._session.flush()
        return resume

    def _deactivate_current_resume(self, candidate_id: uuid.UUID) -> None:
        current_resume = self.get_current_resume(candidate_id)
        if current_resume is None:
            return

        current_resume.is_current = False
        # Flush the deactivation before inserting/activating another row so the
        # PostgreSQL partial unique index never observes two current resumes.
        self._session.flush()
