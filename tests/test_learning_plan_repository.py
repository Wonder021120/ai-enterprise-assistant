from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, JobSkill, LearningPlan, LearningPlanItem
from app.repositories import LearningPlanItemRepository, LearningPlanRepository


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _analysis_run(job_id: uuid.UUID | None = None) -> AnalysisRun:
    return AnalysisRun(
        id=uuid.uuid4(),
        job_id=job_id or uuid.uuid4(),
        resume_id=uuid.uuid4(),
        run_type="learning_plan",
        status="succeeded",
        current_stage="completed",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
    )


def _learning_plan(analysis_run_id: uuid.UUID) -> LearningPlan:
    return LearningPlan(
        id=uuid.uuid4(),
        analysis_run_id=analysis_run_id,
        plan_summary="Prioritized learning plan",
        full_output={"plan_summary": "Prioritized learning plan"},
        schema_version=1,
    )


def _job_skill(job_id: uuid.UUID, position: int = 1) -> JobSkill:
    return JobSkill(
        id=uuid.uuid4(),
        job_id=job_id,
        skill_id=uuid.uuid4(),
        skill_name_snapshot="Python",
        skill_category="required",
        position=position,
    )


def _item_data(
    job_skill_id: uuid.UUID,
    *,
    priority_order: int = 1,
) -> dict[str, object]:
    return {
        "job_skill_id": job_skill_id,
        "priority": "high",
        "priority_order": priority_order,
        "basis": "resume_evidence_missing",
        "task_type": "project_practice",
        "rationale": "Build verifiable evidence",
        "learning_objective": "Apply the skill in a real project",
        "action_steps": ["Study fundamentals", "Implement a feature"],
        "practice_task": "Build a small service",
        "deliverable": "A tested repository",
        "completion_criteria": ["Tests pass", "README is complete"],
        "estimated_hours": 8,
    }


def test_create_learning_plan_validates_analysis_run_and_flushes() -> None:
    session = MagicMock(spec=Session)
    analysis_run = _analysis_run()
    session.scalar.return_value = analysis_run

    plan = LearningPlanRepository(session).create_learning_plan(
        analysis_run_id=analysis_run.id,
        plan_summary="Prioritized plan",
        full_output={"plan_summary": "Prioritized plan", "plan_items": []},
        schema_version=1,
    )

    assert plan.analysis_run_id == analysis_run.id
    assert plan.plan_summary == "Prioritized plan"
    assert plan.schema_version == 1
    session.add.assert_called_once_with(plan)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_create_learning_plan_rejects_missing_analysis_run() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None

    with pytest.raises(ValueError, match="AnalysisRun does not exist"):
        LearningPlanRepository(session).create_learning_plan(
            analysis_run_id=uuid.uuid4(),
            plan_summary="Plan",
            full_output={"plan_summary": "Plan"},
            schema_version=1,
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_duplicate_learning_plan_integrity_error_is_not_swallowed() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = _analysis_run()
    error = IntegrityError("insert", {}, Exception("unique violation"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError) as exc_info:
        LearningPlanRepository(session).create_learning_plan(
            analysis_run_id=uuid.uuid4(),
            plan_summary="Plan",
            full_output={"plan_summary": "Plan"},
            schema_version=1,
        )

    assert exc_info.value is error
    session.rollback.assert_not_called()


def test_get_learning_plan_by_id_returns_record_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = _learning_plan(uuid.uuid4())
    session.scalar.side_effect = [expected, None]
    repository = LearningPlanRepository(session)

    assert repository.get_learning_plan_by_id(expected.id) is expected
    assert repository.get_learning_plan_by_id(uuid.uuid4()) is None
    sql = _compile(session.scalar.call_args_list[0].args[0])
    assert f"learning_plans.id = '{expected.id}'" in sql


def test_get_learning_plan_by_analysis_run_id() -> None:
    session = MagicMock(spec=Session)
    analysis_run_id = uuid.uuid4()
    expected = _learning_plan(analysis_run_id)
    session.scalar.return_value = expected

    result = LearningPlanRepository(
        session
    ).get_learning_plan_by_analysis_run_id(analysis_run_id)

    assert result is expected
    sql = _compile(session.scalar.call_args.args[0])
    assert f"learning_plans.analysis_run_id = '{analysis_run_id}'" in sql


def test_list_learning_plans_filters_orders_and_paginates() -> None:
    session = MagicMock(spec=Session)
    analysis_run_id = uuid.uuid4()
    plans = [_learning_plan(analysis_run_id)]
    session.scalars.return_value.all.return_value = plans

    result = LearningPlanRepository(session).list_learning_plans(
        analysis_run_id=analysis_run_id,
        schema_version=1,
        limit=10,
        offset=20,
    )

    assert result == plans
    sql = _compile(session.scalars.call_args.args[0])
    assert f"learning_plans.analysis_run_id = '{analysis_run_id}'" in sql
    assert "learning_plans.schema_version = 1" in sql
    assert "ORDER BY learning_plans.created_at DESC, learning_plans.id" in sql
    assert "LIMIT 10 OFFSET 20" in sql


def test_update_learning_plan_uses_explicit_whitelist() -> None:
    session = MagicMock(spec=Session)
    plan = _learning_plan(uuid.uuid4())
    session.scalar.return_value = plan

    result = LearningPlanRepository(session).update_learning_plan(
        plan.id,
        plan_summary="Updated plan",
        full_output={"plan_summary": "Updated plan"},
        schema_version=2,
    )

    assert result is plan
    assert plan.plan_summary == "Updated plan"
    assert plan.full_output == {"plan_summary": "Updated plan"}
    assert plan.schema_version == 2
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_update_learning_plan_returns_none_when_missing() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = None

    result = LearningPlanRepository(session).update_learning_plan(
        uuid.uuid4(),
        plan_summary="Updated",
    )

    assert result is None
    session.flush.assert_not_called()


@pytest.mark.parametrize("field_name", ["id", "analysis_run_id", "created_at"])
def test_update_learning_plan_rejects_immutable_fields(field_name: str) -> None:
    session = MagicMock(spec=Session)

    with pytest.raises(ValueError, match=field_name):
        LearningPlanRepository(session).update_learning_plan(
            uuid.uuid4(),
            **{field_name: uuid.uuid4()},
        )

    session.scalar.assert_not_called()
    session.flush.assert_not_called()


def test_create_single_item_checks_full_job_chain_and_flushes() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id)
    plan = _learning_plan(analysis_run.id)
    job_skill = _job_skill(job_id)
    session.scalar.side_effect = [plan, analysis_run, job_skill]
    repository = LearningPlanItemRepository(session)

    item = repository.create_learning_plan_item(
        learning_plan_id=plan.id,
        **_item_data(job_skill.id),
    )

    assert item.learning_plan_id == plan.id
    assert item.job_skill_id == job_skill.id
    assert item.priority_order == 1
    session.add.assert_called_once_with(item)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


def test_create_learning_plan_items_validates_batch_before_add_all() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id)
    plan = _learning_plan(analysis_run.id)
    first_skill = _job_skill(job_id, 1)
    second_skill = _job_skill(job_id, 2)
    session.scalar.side_effect = [plan, analysis_run]
    session.scalars.return_value.all.return_value = [first_skill, second_skill]

    items = LearningPlanItemRepository(session).create_learning_plan_items(
        learning_plan_id=plan.id,
        items=[
            _item_data(first_skill.id, priority_order=1),
            _item_data(second_skill.id, priority_order=2),
        ],
    )

    assert [item.job_skill_id for item in items] == [
        first_skill.id,
        second_skill.id,
    ]
    session.add_all.assert_called_once_with(items)
    session.flush.assert_called_once_with()


def test_get_learning_plan_item_by_id_returns_record_or_none() -> None:
    session = MagicMock(spec=Session)
    expected = MagicMock(spec=LearningPlanItem)
    session.scalar.side_effect = [expected, None]
    repository = LearningPlanItemRepository(session)
    item_id = uuid.uuid4()

    assert repository.get_learning_plan_item_by_id(item_id) is expected
    assert repository.get_learning_plan_item_by_id(uuid.uuid4()) is None
    sql = _compile(session.scalar.call_args_list[0].args[0])
    assert f"learning_plan_items.id = '{item_id}'" in sql


def test_list_items_filters_orders_and_paginates() -> None:
    session = MagicMock(spec=Session)
    plan_id = uuid.uuid4()
    job_skill_id = uuid.uuid4()
    records = [MagicMock(spec=LearningPlanItem)]
    session.scalars.return_value.all.return_value = records

    result = LearningPlanItemRepository(session).list_learning_plan_items(
        plan_id,
        priority="high",
        job_skill_id=job_skill_id,
        limit=5,
        offset=10,
    )

    assert result == records
    sql = _compile(session.scalars.call_args.args[0])
    assert f"learning_plan_items.learning_plan_id = '{plan_id}'" in sql
    assert "learning_plan_items.priority = 'high'" in sql
    assert f"learning_plan_items.job_skill_id = '{job_skill_id}'" in sql
    assert (
        "ORDER BY learning_plan_items.priority_order, learning_plan_items.id"
    ) in sql
    assert "LIMIT 5 OFFSET 10" in sql


@pytest.mark.parametrize(
    ("lookup_results", "message"),
    [
        ([None], "LearningPlan does not exist"),
        ([_learning_plan(uuid.uuid4()), None], "AnalysisRun does not exist"),
        (
            [
                _learning_plan(uuid.uuid4()),
                _analysis_run(),
                None,
            ],
            "JobSkill does not exist",
        ),
    ],
)
def test_create_item_rejects_missing_related_records(
    lookup_results,
    message: str,
) -> None:
    session = MagicMock(spec=Session)
    session.scalar.side_effect = lookup_results

    with pytest.raises(ValueError, match=message):
        LearningPlanItemRepository(session).create_learning_plan_item(
            learning_plan_id=uuid.uuid4(),
            **_item_data(uuid.uuid4()),
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_create_item_rejects_job_skill_from_different_job() -> None:
    session = MagicMock(spec=Session)
    analysis_run = _analysis_run(job_id=uuid.uuid4())
    plan = _learning_plan(analysis_run.id)
    foreign_job_skill = _job_skill(job_id=uuid.uuid4())
    session.scalar.side_effect = [plan, analysis_run, foreign_job_skill]

    with pytest.raises(ValueError, match="does not belong"):
        LearningPlanItemRepository(session).create_learning_plan_item(
            learning_plan_id=plan.id,
            **_item_data(foreign_job_skill.id),
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_batch_with_foreign_job_skill_is_rejected_before_add_all() -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id)
    plan = _learning_plan(analysis_run.id)
    valid = _job_skill(job_id, 1)
    foreign = _job_skill(uuid.uuid4(), 2)
    session.scalar.side_effect = [plan, analysis_run]
    session.scalars.return_value.all.return_value = [valid, foreign]

    with pytest.raises(ValueError, match="does not belong"):
        LearningPlanItemRepository(session).create_learning_plan_items(
            learning_plan_id=plan.id,
            items=[
                _item_data(valid.id, priority_order=1),
                _item_data(foreign.id, priority_order=2),
            ],
        )

    session.add_all.assert_not_called()
    session.flush.assert_not_called()


@pytest.mark.parametrize("duplicate_field", ["job_skill_id", "priority_order"])
def test_duplicate_item_constraint_error_is_not_swallowed(
    duplicate_field: str,
) -> None:
    session = MagicMock(spec=Session)
    job_id = uuid.uuid4()
    analysis_run = _analysis_run(job_id)
    plan = _learning_plan(analysis_run.id)
    first_skill = _job_skill(job_id, 1)
    second_skill = _job_skill(job_id, 2)
    session.scalar.side_effect = [plan, analysis_run]
    session.scalars.return_value.all.return_value = [first_skill, second_skill]
    first = _item_data(first_skill.id, priority_order=1)
    second = _item_data(second_skill.id, priority_order=2)
    if duplicate_field == "job_skill_id":
        second["job_skill_id"] = first_skill.id
    else:
        second["priority_order"] = 1
    error = IntegrityError("insert", {}, Exception("unique violation"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError) as exc_info:
        LearningPlanItemRepository(session).create_learning_plan_items(
            learning_plan_id=plan.id,
            items=[first, second],
        )

    assert exc_info.value is error
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()
