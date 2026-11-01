from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, AnalysisSkillMatch, JobSkill
from app.repositories import AnalysisRunRepository, AnalysisSkillMatchRepository


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _analysis_run(
    *,
    job_id: uuid.UUID | None = None,
    resume_id: uuid.UUID | None = None,
) -> AnalysisRun:
    return AnalysisRun(
        id=uuid.uuid4(),
        job_id=job_id or uuid.uuid4(),
        resume_id=resume_id,
        run_type="resume_matching" if resume_id else "jd_analysis",
        status="running",
        current_stage="jd_analysis",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
    )


def _job_skill(
    *,
    job_id: uuid.UUID,
    position: int = 1,
    category: str = "required",
) -> JobSkill:
    return JobSkill(
        id=uuid.uuid4(),
        job_id=job_id,
        skill_id=uuid.uuid4(),
        skill_name_snapshot="Python",
        skill_category=category,
        position=position,
    )


def test_create_analysis_run_maps_fields_and_flushes() -> None:
    session = MagicMock(spec=Session)
    repository = AnalysisRunRepository(session)
    job_id = uuid.uuid4()
    resume_id = uuid.uuid4()

    analysis_run = repository.create_analysis_run(
        job_id=job_id,
        resume_id=resume_id,
        run_type="resume_matching",
        status="running",
        current_stage="jd_analysis",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
        jd_analysis_output={"job_title": "Engineer"},
    )

    assert analysis_run.job_id == job_id
    assert analysis_run.resume_id == resume_id
    assert analysis_run.status == "running"
    assert analysis_run.jd_analysis_output == {"job_title": "Engineer"}
    assert analysis_run.resume_matching_output is None
    assert analysis_run.resume_improvement_suggestions == []
    assert analysis_run.learning_practice_suggestions == []
    session.add.assert_called_once_with(analysis_run)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_create_analysis_run_uses_independent_empty_suggestion_lists() -> None:
    session = MagicMock(spec=Session)
    repository = AnalysisRunRepository(session)

    first = repository.create_analysis_run(
        job_id=uuid.uuid4(),
        run_type="jd_analysis",
        status="running",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
    )
    second = repository.create_analysis_run(
        job_id=uuid.uuid4(),
        run_type="jd_analysis",
        status="running",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
    )

    first.learning_practice_suggestions.append("Practice FastAPI")
    assert second.learning_practice_suggestions == []
    assert first.learning_practice_suggestions is not (
        second.learning_practice_suggestions
    )


def test_get_analysis_run_by_id_returns_record_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = _analysis_run()
    session.scalar.side_effect = [expected, None]
    repository = AnalysisRunRepository(session)

    assert repository.get_analysis_run_by_id(expected.id) is expected
    assert repository.get_analysis_run_by_id(uuid.uuid4()) is None
    sql = _compile(session.scalar.call_args_list[0].args[0])
    assert f"analysis_runs.id = '{expected.id}'" in sql


def test_list_analysis_runs_filters_job_and_paginates() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    records = [_analysis_run(job_id=job_id)]
    session.scalars.return_value.all.return_value = records

    result = AnalysisRunRepository(session).list_analysis_runs(
        job_id=job_id,
        limit=20,
        offset=40,
    )

    assert result == records
    sql = _compile(session.scalars.call_args.args[0])
    assert f"analysis_runs.job_id = '{job_id}'" in sql
    assert "ORDER BY analysis_runs.created_at DESC, analysis_runs.id" in sql
    assert "LIMIT 20 OFFSET 40" in sql


def test_list_analysis_runs_filters_resume_history() -> None:
    session = MagicMock(spec=Session)
    resume_id = uuid.uuid4()
    session.scalars.return_value.all.return_value = []

    result = AnalysisRunRepository(session).list_analysis_runs(
        resume_id=resume_id
    )

    assert result == []
    sql = _compile(session.scalars.call_args.args[0])
    assert f"analysis_runs.resume_id = '{resume_id}'" in sql


def test_list_analysis_runs_filters_type_and_status() -> None:
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = []

    AnalysisRunRepository(session).list_analysis_runs(
        run_type="learning_plan",
        status="failed",
    )

    sql = _compile(session.scalars.call_args.args[0])
    assert "analysis_runs.run_type = 'learning_plan'" in sql
    assert "analysis_runs.status = 'failed'" in sql
    session.commit.assert_not_called()
    session.close.assert_not_called()


@pytest.mark.parametrize(
    ("limit", "offset", "message"),
    [(0, 0, "limit"), (10, -1, "offset")],
)
def test_list_analysis_runs_rejects_invalid_pagination(
    limit: int,
    offset: int,
    message: str,
) -> None:
    session = MagicMock(spec=Session)
    with pytest.raises(ValueError, match=message):
        AnalysisRunRepository(session).list_analysis_runs(
            limit=limit,
            offset=offset,
        )
    session.scalars.assert_not_called()


def test_update_analysis_run_updates_only_lifecycle_fields() -> None:
    session = MagicMock(spec=Session)
    analysis_run = _analysis_run()
    session.scalar.return_value = analysis_run
    completed_at = datetime.now(UTC)

    result = AnalysisRunRepository(session).update_analysis_run(
        analysis_run.id,
        status="succeeded",
        current_stage="completed",
        jd_analysis_output={"job_title": "Engineer"},
        completed_at=completed_at,
    )

    assert result is analysis_run
    assert analysis_run.status == "succeeded"
    assert analysis_run.current_stage == "completed"
    assert analysis_run.completed_at == completed_at
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_update_analysis_run_rejects_unknown_or_immutable_fields() -> None:
    session = MagicMock(spec=Session)
    repository = AnalysisRunRepository(session)

    with pytest.raises(ValueError, match="job_id, unknown"):
        repository.update_analysis_run(
            uuid.uuid4(),
            job_id=uuid.uuid4(),
            unknown="value",
        )

    session.scalar.assert_not_called()
    session.flush.assert_not_called()


def test_update_analysis_run_returns_none_when_missing() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None

    result = AnalysisRunRepository(session).update_analysis_run(
        uuid.uuid4(),
        status="failed",
    )

    assert result is None
    session.flush.assert_not_called()


def test_create_single_skill_match_validates_same_job_and_flushes() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id=job_id)
    job_skill = _job_skill(job_id=job_id)
    session.scalar.side_effect = [analysis_run, job_skill]

    skill_match = AnalysisSkillMatchRepository(session).create_skill_match(
        analysis_run_id=analysis_run.id,
        job_skill_id=job_skill.id,
        status="evidence_found",
        evidence="Built Python services",
    )

    assert skill_match.analysis_run_id == analysis_run.id
    assert skill_match.job_skill_id == job_skill.id
    assert skill_match.evidence == "Built Python services"
    session.add.assert_called_once_with(skill_match)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_create_skill_matches_validates_batch_before_adding() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id=job_id)
    required = _job_skill(job_id=job_id, position=1)
    preferred = _job_skill(
        job_id=job_id,
        position=1,
        category="preferred",
    )
    session.scalar.return_value = analysis_run
    session.scalars.return_value.all.return_value = [required, preferred]

    matches = AnalysisSkillMatchRepository(session).create_skill_matches(
        analysis_run_id=analysis_run.id,
        matches=[
            {
                "job_skill_id": required.id,
                "status": "evidence_found",
                "evidence": "Python service",
            },
            {
                "job_skill_id": preferred.id,
                "status": "not_found_in_resume",
                "evidence": None,
            },
        ],
    )

    assert [match.job_skill_id for match in matches] == [
        required.id,
        preferred.id,
    ]
    session.add_all.assert_called_once_with(matches)
    session.flush.assert_called_once_with()


def test_get_skill_match_by_id_returns_record_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = MagicMock(spec=AnalysisSkillMatch)
    session.scalar.side_effect = [expected, None]
    repository = AnalysisSkillMatchRepository(session)
    skill_match_id = uuid.uuid4()

    assert repository.get_skill_match_by_id(skill_match_id) is expected
    assert repository.get_skill_match_by_id(uuid.uuid4()) is None
    sql = _compile(session.scalar.call_args_list[0].args[0])
    assert f"analysis_skill_matches.id = '{skill_match_id}'" in sql


def test_list_skill_matches_filters_status_category_and_orders_position() -> None:
    session = MagicMock(spec=Session)
    analysis_run_id = uuid.uuid4()
    records = [MagicMock(spec=AnalysisSkillMatch)]
    session.scalars.return_value.all.return_value = records

    result = AnalysisSkillMatchRepository(session).list_skill_matches(
        analysis_run_id,
        status="evidence_found",
        skill_category="required",
    )

    assert result == records
    sql = _compile(session.scalars.call_args.args[0])
    assert "JOIN job_skills" in sql
    assert f"analysis_skill_matches.analysis_run_id = '{analysis_run_id}'" in sql
    assert "analysis_skill_matches.status = 'evidence_found'" in sql
    assert "job_skills.skill_category = 'required'" in sql
    assert (
        "ORDER BY job_skills.skill_category DESC, job_skills.position, "
        "analysis_skill_matches.id"
    ) in sql


@pytest.mark.parametrize(
    ("lookup_results", "message"),
    [
        ([None], "AnalysisRun does not exist"),
        ([_analysis_run(), None], "JobSkill does not exist"),
    ],
)
def test_create_skill_match_rejects_missing_related_records(
    lookup_results,
    message: str,
) -> None:
    session = MagicMock(spec=Session)
    session.scalar.side_effect = lookup_results

    with pytest.raises(ValueError, match=message):
        AnalysisSkillMatchRepository(session).create_skill_match(
            analysis_run_id=uuid.uuid4(),
            job_skill_id=uuid.uuid4(),
            status="not_found_in_resume",
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_create_skill_match_rejects_job_skill_from_different_job() -> None:
    session = MagicMock(spec=Session)
    analysis_run = _analysis_run(job_id=uuid.uuid4())
    foreign_job_skill = _job_skill(job_id=uuid.uuid4())
    session.scalar.side_effect = [analysis_run, foreign_job_skill]

    with pytest.raises(ValueError, match="does not belong"):
        AnalysisSkillMatchRepository(session).create_skill_match(
            analysis_run_id=analysis_run.id,
            job_skill_id=foreign_job_skill.id,
            status="not_found_in_resume",
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_batch_rejects_mixed_job_skills_before_add_all() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id=job_id)
    valid = _job_skill(job_id=job_id)
    foreign = _job_skill(job_id=uuid.uuid4(), position=2)
    session.scalar.return_value = analysis_run
    session.scalars.return_value.all.return_value = [valid, foreign]

    with pytest.raises(ValueError, match="does not belong"):
        AnalysisSkillMatchRepository(session).create_skill_matches(
            analysis_run_id=analysis_run.id,
            matches=[
                {"job_skill_id": valid.id, "status": "evidence_found"},
                {
                    "job_skill_id": foreign.id,
                    "status": "not_found_in_resume",
                },
            ],
        )

    session.add_all.assert_not_called()
    session.flush.assert_not_called()


def test_duplicate_skill_match_integrity_error_is_not_swallowed() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id=job_id)
    job_skill = _job_skill(job_id=job_id)
    session.scalar.side_effect = [analysis_run, job_skill]
    error = IntegrityError("insert", {}, Exception("unique violation"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError) as exc_info:
        AnalysisSkillMatchRepository(session).create_skill_match(
            analysis_run_id=analysis_run.id,
            job_skill_id=job_skill.id,
            status="not_found_in_resume",
        )

    assert exc_info.value is error
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()
