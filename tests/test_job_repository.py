from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.models import Job
from app.repositories import JobRepository


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _job(source_sha256: str = "a" * 64) -> Job:
    return Job(
        source_text="Python backend role",
        source_sha256=source_sha256,
        schema_version=1,
        company="CareerPilot",
        job_title="Python Engineer",
    )


def test_create_job_maps_all_actual_fields_and_flushes() -> None:
    session = MagicMock(spec=Session)
    repository = JobRepository(session)

    job = repository.create_job(
        source_text="Python backend role",
        source_sha256="a" * 64,
        schema_version=1,
        company="CareerPilot",
        job_title="Python Engineer",
        location="Shanghai",
        recruitment_type="full-time",
        education="Bachelor",
        graduation_requirement="2026",
        experience_requirement="2 years",
        salary="20k-30k",
    )

    assert job.company == "CareerPilot"
    assert job.job_title == "Python Engineer"
    assert job.location == "Shanghai"
    assert job.schema_version == 1
    session.add.assert_called_once_with(job)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_get_job_by_id_returns_job_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = _job()
    session.scalar.side_effect = [expected, None]
    repository = JobRepository(session)
    job_id = uuid.uuid4()

    assert repository.get_job_by_id(job_id) is expected
    assert repository.get_job_by_id(uuid.uuid4()) is None

    sql = _compile(session.scalar.call_args_list[0].args[0])
    assert f"jobs.id = '{job_id}'" in sql


def test_list_jobs_without_filters_returns_ordered_results() -> None:
    session = MagicMock(spec=Session)
    jobs = [_job(), _job()]
    session.scalars.return_value.all.return_value = jobs

    result = JobRepository(session).list_jobs()

    assert result == jobs
    sql = _compile(session.scalars.call_args.args[0])
    assert "ORDER BY jobs.created_at DESC, jobs.id" in sql


def test_list_jobs_applies_supported_model_filters() -> None:
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = []

    result = JobRepository(session).list_jobs(
        company="CareerPilot",
        job_title="Python Engineer",
        location="Shanghai",
        recruitment_type="full-time",
        education="Bachelor",
        schema_version=1,
    )

    assert result == []
    sql = _compile(session.scalars.call_args.args[0])
    assert "jobs.company = 'CareerPilot'" in sql
    assert "jobs.job_title = 'Python Engineer'" in sql
    assert "jobs.location = 'Shanghai'" in sql
    assert "jobs.recruitment_type = 'full-time'" in sql
    assert "jobs.education = 'Bachelor'" in sql
    assert "jobs.schema_version = 1" in sql


def test_source_sha256_query_returns_all_matches_not_one() -> None:
    session = MagicMock(spec=Session)
    source_sha256 = "b" * 64
    matches = [_job(source_sha256), _job(source_sha256)]
    session.scalars.return_value.all.return_value = matches

    result = JobRepository(session).find_jobs_by_source_sha256(source_sha256)

    assert result == matches
    assert len(result) == 2
    sql = _compile(session.scalars.call_args.args[0])
    assert f"jobs.source_sha256 = '{source_sha256}'" in sql
    session.commit.assert_not_called()
    session.close.assert_not_called()
