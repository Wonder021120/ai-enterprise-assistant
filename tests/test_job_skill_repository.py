from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Job, JobSkill, Skill
from app.repositories import JobSkillRepository


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _job(job_id: uuid.UUID) -> Job:
    return Job(
        id=job_id,
        source_text="Python role",
        source_sha256="a" * 64,
        schema_version=1,
    )


def _skill(skill_id: uuid.UUID, name: str = "Python") -> Skill:
    return Skill(id=skill_id, name=name)


def test_attach_skill_uses_existing_entities_and_skill_name_snapshot() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    skill_id = uuid.uuid4()
    session.scalar.side_effect = [_job(job_id), _skill(skill_id)]
    repository = JobSkillRepository(session)

    job_skill = repository.attach_skill_to_job(
        job_id=job_id,
        skill_id=skill_id,
        skill_category="required",
        position=1,
    )

    assert job_skill.job_id == job_id
    assert job_skill.skill_id == skill_id
    assert job_skill.skill_name_snapshot == "Python"
    assert job_skill.skill_category == "required"
    assert job_skill.position == 1
    session.add.assert_called_once_with(job_skill)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


@pytest.mark.parametrize(
    ("lookup_results", "message"),
    [
        ([None], "Job does not exist"),
        ([MagicMock(spec=Job), None], "Skill does not exist"),
    ],
)
def test_attach_skill_rejects_missing_foreign_entities(
    lookup_results,
    message: str,
) -> None:
    session = MagicMock(spec=Session)
    session.scalar.side_effect = lookup_results

    with pytest.raises(ValueError, match=message):
        JobSkillRepository(session).attach_skill_to_job(
            job_id=uuid.uuid4(),
            skill_id=uuid.uuid4(),
            skill_category="required",
            position=1,
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


@pytest.mark.parametrize(
    ("skill_category", "position"),
    [("invalid", 1), ("required", 0)],
)
def test_attach_skill_leaves_check_constraints_to_database(
    skill_category: str,
    position: int,
) -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    skill_id = uuid.uuid4()
    session.scalar.side_effect = [_job(job_id), _skill(skill_id)]
    error = IntegrityError("insert", {}, Exception("check violation"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError) as exc_info:
        JobSkillRepository(session).attach_skill_to_job(
            job_id=job_id,
            skill_id=skill_id,
            skill_category=skill_category,
            position=position,
        )

    assert exc_info.value is error
    session.rollback.assert_not_called()


def test_duplicate_job_skill_integrity_error_is_not_swallowed() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    skill_id = uuid.uuid4()
    session.scalar.side_effect = [_job(job_id), _skill(skill_id)]
    error = IntegrityError("insert", {}, Exception("unique violation"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError) as exc_info:
        JobSkillRepository(session).attach_skill_to_job(
            job_id=job_id,
            skill_id=skill_id,
            skill_category="required",
            position=1,
        )

    assert exc_info.value is error
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_get_job_skill_by_id_returns_association_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = MagicMock(spec=JobSkill)
    session.scalar.side_effect = [expected, None]
    repository = JobSkillRepository(session)
    job_skill_id = uuid.uuid4()

    assert repository.get_job_skill_by_id(job_skill_id) is expected
    assert repository.get_job_skill_by_id(uuid.uuid4()) is None
    sql = _compile(session.scalar.call_args_list[0].args[0])
    assert f"job_skills.id = '{job_skill_id}'" in sql


def test_list_job_skills_filters_category_and_orders_position() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    matches = [MagicMock(spec=JobSkill), MagicMock(spec=JobSkill)]
    session.scalars.return_value.all.return_value = matches

    result = JobSkillRepository(session).list_job_skills(
        job_id,
        skill_category="preferred",
    )

    assert result == matches
    sql = _compile(session.scalars.call_args.args[0])
    assert f"job_skills.job_id = '{job_id}'" in sql
    assert "job_skills.skill_category = 'preferred'" in sql
    assert "ORDER BY job_skills.position, job_skills.id" in sql
    session.commit.assert_not_called()
    session.close.assert_not_called()
