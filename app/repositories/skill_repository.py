from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Skill


class SkillRepository:
    """Skill 字典的数据访问操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_skill(self, *, name: str) -> Skill:
        normalized_name = self.normalize_name(name)
        existing = self.get_skill_by_normalized_name(normalized_name)
        if existing is not None:
            return existing

        skill = Skill(name=name)
        self._session.add(skill)
        # The unique constraint remains the final guard against concurrent
        # inserts.  IntegrityError intentionally propagates to the caller.
        self._session.flush()
        return skill

    def get_skill_by_id(self, skill_id: uuid.UUID) -> Skill | None:
        statement = select(Skill).where(Skill.id == skill_id)
        return self._session.scalar(statement)

    def get_skill_by_normalized_name(
        self,
        normalized_name: str,
    ) -> Skill | None:
        normalized_name = self.normalize_name(normalized_name)
        statement = select(Skill).where(
            Skill.normalized_name == normalized_name
        )
        return self._session.scalar(statement)

    def search_skills(self, query: str) -> list[Skill]:
        normalized_query = self.normalize_name(query)
        statement = (
            select(Skill)
            .where(Skill.normalized_name.contains(normalized_query))
            .order_by(Skill.normalized_name, Skill.id)
        )
        return list(self._session.scalars(statement).all())

    @staticmethod
    def normalize_name(name: str) -> str:
        return name.strip().casefold()
