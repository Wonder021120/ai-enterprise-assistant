from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Skill
from app.repositories import SkillRepository


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_create_skill_derives_normalized_name_and_flushes() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None
    repository = SkillRepository(session)

    skill = repository.create_skill(name="  PyThOn  ")

    assert skill.name == "  PyThOn  "
    assert skill.normalized_name == "python"
    session.add.assert_called_once_with(skill)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_create_skill_reuses_case_insensitive_duplicate() -> None:
    session = MagicMock(spec=Session)
    existing = Skill(name="Python")
    session.scalar.return_value = existing
    repository = SkillRepository(session)

    result = repository.create_skill(name="  PYTHON ")

    assert result is existing
    sql = _compile(session.scalar.call_args.args[0])
    assert "skills.normalized_name = 'python'" in sql
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_create_skill_does_not_swallow_unique_constraint_error() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None
    error = IntegrityError("insert", {}, Exception("duplicate"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError) as exc_info:
        SkillRepository(session).create_skill(name="Python")

    assert exc_info.value is error
    session.rollback.assert_not_called()


def test_get_skill_by_id_returns_skill_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = Skill(name="Python")
    session.scalar.side_effect = [expected, None]
    repository = SkillRepository(session)
    skill_id = uuid.uuid4()

    assert repository.get_skill_by_id(skill_id) is expected
    assert repository.get_skill_by_id(uuid.uuid4()) is None
    assert f"skills.id = '{skill_id}'" in _compile(
        session.scalar.call_args_list[0].args[0]
    )


def test_get_by_normalized_name_normalizes_caller_input() -> None:
    session = MagicMock(spec=Session)
    expected = Skill(name="Straße")
    session.scalar.return_value = expected

    result = SkillRepository(session).get_skill_by_normalized_name(
        "  STRASSE "
    )

    assert result is expected
    sql = _compile(session.scalar.call_args.args[0])
    assert "skills.normalized_name = 'strasse'" in sql


def test_search_skills_uses_normalized_name_and_returns_list() -> None:
    session = MagicMock(spec=Session)
    skills = [Skill(name="FastAPI"), Skill(name="Python API")]
    session.scalars.return_value.all.return_value = skills

    result = SkillRepository(session).search_skills("  API ")

    assert result == skills
    sql = _compile(session.scalars.call_args.args[0])
    assert "skills.normalized_name LIKE '%%' || 'api' || '%%'" in sql
    assert "ORDER BY skills.normalized_name, skills.id" in sql
