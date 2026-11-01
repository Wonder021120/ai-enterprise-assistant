from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.models import Resume
from app.repositories import ResumeRepository


def _resume(
    *,
    candidate_id: uuid.UUID,
    resume_id: uuid.UUID | None = None,
    version: int = 1,
    is_current: bool = False,
) -> Resume:
    return Resume(
        id=resume_id or uuid.uuid4(),
        candidate_id=candidate_id,
        title=f"Resume v{version}",
        resume_text="Python project experience",
        content_sha256="a" * 64,
        version=version,
        is_current=is_current,
    )


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_create_non_current_resume_adds_and_flushes() -> None:
    session = MagicMock(spec=Session)
    repository = ResumeRepository(session)
    candidate_id = uuid.uuid4()

    resume = repository.create_resume(
        candidate_id=candidate_id,
        title="Backend Resume",
        resume_text="FastAPI and PostgreSQL experience",
        content_sha256="b" * 64,
        version=2,
    )

    assert resume.candidate_id == candidate_id
    assert resume.title == "Backend Resume"
    assert resume.version == 2
    assert resume.is_current is False
    session.add.assert_called_once_with(resume)
    session.flush.assert_called_once_with()


def test_create_current_resume_deactivates_old_version_before_insert() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    old_resume = _resume(
        candidate_id=candidate_id,
        version=1,
        is_current=True,
    )
    session.scalar.return_value = old_resume
    repository = ResumeRepository(session)

    new_resume = repository.create_resume(
        candidate_id=candidate_id,
        resume_text="New resume",
        content_sha256="c" * 64,
        version=2,
        is_current=True,
    )

    assert old_resume.is_current is False
    assert new_resume.is_current is True
    assert session.method_calls.index(call.flush()) < session.method_calls.index(
        call.add(new_resume)
    )
    assert session.flush.call_count == 2
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_get_resume_by_id_returns_resume_or_none() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    expected = _resume(candidate_id=candidate_id)
    session.scalar.side_effect = [expected, None]
    repository = ResumeRepository(session)

    assert repository.get_resume_by_id(expected.id) is expected
    assert repository.get_resume_by_id(uuid.uuid4()) is None

    first_statement = session.scalar.call_args_list[0].args[0]
    assert f"resumes.id = '{expected.id}'" in _compile(first_statement)


def test_get_current_resume_filters_candidate_and_current_flag() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    expected = _resume(candidate_id=candidate_id, is_current=True)
    session.scalar.return_value = expected

    result = ResumeRepository(session).get_current_resume(candidate_id)

    assert result is expected
    sql = _compile(session.scalar.call_args.args[0])
    assert f"resumes.candidate_id = '{candidate_id}'" in sql
    assert "resumes.is_current IS true" in sql


def test_list_resume_history_excludes_current_and_orders_versions() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    history = [
        _resume(candidate_id=candidate_id, version=2),
        _resume(candidate_id=candidate_id, version=1),
    ]
    session.scalars.return_value.all.return_value = history

    result = ResumeRepository(session).list_resume_history(candidate_id)

    assert result == history
    sql = _compile(session.scalars.call_args.args[0])
    assert f"resumes.candidate_id = '{candidate_id}'" in sql
    assert "resumes.is_current IS false" in sql
    assert "ORDER BY resumes.version DESC, resumes.created_at DESC" in sql


def test_set_current_resume_switches_versions_in_safe_flush_order() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    old_resume = _resume(
        candidate_id=candidate_id,
        version=1,
        is_current=True,
    )
    target_resume = _resume(
        candidate_id=candidate_id,
        version=2,
        is_current=False,
    )
    session.scalar.side_effect = [target_resume, old_resume]
    repository = ResumeRepository(session)

    result = repository.set_current_resume(
        candidate_id=candidate_id,
        resume_id=target_resume.id,
    )

    assert result is target_resume
    assert old_resume.is_current is False
    assert target_resume.is_current is True
    assert session.flush.call_count == 2
    session.commit.assert_not_called()
    session.close.assert_not_called()


def test_set_current_resume_rejects_resume_from_other_candidate() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    foreign_resume = _resume(candidate_id=uuid.uuid4())
    session.scalar.return_value = foreign_resume
    repository = ResumeRepository(session)

    with pytest.raises(ValueError, match="does not belong"):
        repository.set_current_resume(
            candidate_id=candidate_id,
            resume_id=foreign_resume.id,
        )

    session.flush.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_set_current_resume_returns_none_when_resume_is_missing() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None

    result = ResumeRepository(session).set_current_resume(
        candidate_id=uuid.uuid4(),
        resume_id=uuid.uuid4(),
    )

    assert result is None
    session.flush.assert_not_called()


def test_setting_already_current_resume_does_not_create_second_current() -> None:
    session = MagicMock(spec=Session)
    candidate_id = uuid.uuid4()
    current_resume = _resume(candidate_id=candidate_id, is_current=True)
    session.scalar.return_value = current_resume

    result = ResumeRepository(session).set_current_resume(
        candidate_id=candidate_id,
        resume_id=current_resume.id,
    )

    assert result is current_resume
    assert current_resume.is_current is True
    assert session.scalar.call_count == 1
    session.flush.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_not_called()
