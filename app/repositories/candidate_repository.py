from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Candidate


class CandidateRepository:
    """Candidate 的 SQLAlchemy 数据访问操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_candidate(
        self,
        *,
        display_name: str | None = None,
        email: str | None = None,
    ) -> Candidate:
        candidate = Candidate(display_name=display_name, email=email)
        self._session.add(candidate)
        self._session.flush()
        return candidate

    def get_candidate_by_id(
        self,
        candidate_id: uuid.UUID,
    ) -> Candidate | None:
        statement = select(Candidate).where(Candidate.id == candidate_id)
        return self._session.scalar(statement)

    def list_candidates(
        self,
        *,
        display_name: str | None = None,
        email: str | None = None,
    ) -> list[Candidate]:
        statement = select(Candidate)

        if display_name is not None:
            statement = statement.where(
                Candidate.display_name == display_name
            )
        if email is not None:
            statement = statement.where(Candidate.email == email)

        statement = statement.order_by(
            Candidate.created_at.desc(),
            Candidate.id,
        )
        return list(self._session.scalars(statement).all())
