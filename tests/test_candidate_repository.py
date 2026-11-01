from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.models import Candidate
from app.repositories import CandidateRepository


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_create_candidate_adds_and_flushes_without_committing() -> None:
    session = MagicMock(spec=Session)
    repository = CandidateRepository(session)

    candidate = repository.create_candidate(
        display_name="Lin",
        email="lin@example.com",
    )

    assert isinstance(candidate, Candidate)
    assert candidate.display_name == "Lin"
    assert candidate.email == "lin@example.com"
    session.add.assert_called_once_with(candidate)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_get_candidate_by_id_returns_candidate() -> None:
    session = MagicMock(spec=Session)
    expected = Candidate(display_name="Lin", email=None)
    session.scalar.return_value = expected
    repository = CandidateRepository(session)
    candidate_id = uuid.uuid4()

    result = repository.get_candidate_by_id(candidate_id)

    assert result is expected
    statement = session.scalar.call_args.args[0]
    sql = _compile(statement)
    assert "FROM candidates" in sql
    assert f"candidates.id = '{candidate_id}'" in sql


def test_get_candidate_by_id_returns_none_when_missing() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None

    result = CandidateRepository(session).get_candidate_by_id(uuid.uuid4())

    assert result is None


def test_list_candidates_applies_real_model_filters_and_ordering() -> None:
    session = MagicMock(spec=Session)
    candidates = [
        Candidate(display_name="Lin", email="lin@example.com"),
        Candidate(display_name="Lin", email="lin@example.com"),
    ]
    session.scalars.return_value.all.return_value = candidates
    repository = CandidateRepository(session)

    result = repository.list_candidates(
        display_name="Lin",
        email="lin@example.com",
    )

    assert result == candidates
    statement = session.scalars.call_args.args[0]
    sql = _compile(statement)
    assert "candidates.display_name = 'Lin'" in sql
    assert "candidates.email = 'lin@example.com'" in sql
    assert "ORDER BY candidates.created_at DESC, candidates.id" in sql
    session.commit.assert_not_called()
    session.close.assert_not_called()
