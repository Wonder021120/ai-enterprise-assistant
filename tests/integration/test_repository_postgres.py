from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    AnalysisSkillMatch,
    Candidate,
    Job,
    JobSkill,
    LearningPlan,
    LearningPlanItem,
    Resume,
    Skill,
)
from app.repositories import (
    AnalysisRunRepository,
    AnalysisSkillMatchRepository,
    CandidateRepository,
    JobRepository,
    JobSkillRepository,
    LearningPlanItemRepository,
    LearningPlanRepository,
    ResumeRepository,
    SkillRepository,
)


def _token() -> str:
    return uuid.uuid4().hex


def _hash() -> str:
    return _token() * 2


def _create_candidate(session: Session) -> Candidate:
    token = _token()
    return CandidateRepository(session).create_candidate(
        display_name=f"Candidate {token}",
        email=f"{token}@example.com",
    )


def _create_resume(
    session: Session,
    candidate: Candidate,
    *,
    version: int = 1,
    is_current: bool = True,
) -> Resume:
    return ResumeRepository(session).create_resume(
        candidate_id=candidate.id,
        title=f"Resume {version}",
        resume_text=f"Python project experience {_token()}",
        content_sha256=_hash(),
        version=version,
        is_current=is_current,
    )


def _create_job(session: Session, *, source_sha256: str | None = None) -> Job:
    token = _token()
    return JobRepository(session).create_job(
        source_text=f"Python backend role {token}",
        source_sha256=source_sha256 or _hash(),
        schema_version=1,
        company=f"Company {token}",
        job_title="Python Engineer",
        location="Shanghai",
    )


def _create_skill(session: Session, prefix: str = "Python") -> Skill:
    return SkillRepository(session).create_skill(
        name=f"  {prefix}-{_token()}  "
    )


def _attach_skill(
    session: Session,
    job: Job,
    skill: Skill,
    *,
    category: str = "required",
    position: int = 1,
) -> JobSkill:
    return JobSkillRepository(session).attach_skill_to_job(
        job_id=job.id,
        skill_id=skill.id,
        skill_category=category,
        position=position,
    )


def _create_analysis_run(
    session: Session,
    job: Job,
    resume: Resume,
) -> AnalysisRun:
    return AnalysisRunRepository(session).create_analysis_run(
        job_id=job.id,
        resume_id=resume.id,
        run_type="learning_plan",
        status="running",
        current_stage="jd_analysis",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
        jd_analysis_output={"job_title": "Python Engineer"},
        resume_matching_output={},
        resume_improvement_suggestions=[],
        learning_practice_suggestions=[],
    )


def _create_plan(session: Session, analysis_run: AnalysisRun) -> LearningPlan:
    return LearningPlanRepository(session).create_learning_plan(
        analysis_run_id=analysis_run.id,
        plan_summary="Prioritized learning plan",
        full_output={"plan_summary": "Prioritized learning plan"},
        schema_version=1,
    )


def _item_data(job_skill_id: uuid.UUID, priority_order: int = 1) -> dict:
    return {
        "job_skill_id": job_skill_id,
        "priority": "high",
        "priority_order": priority_order,
        "basis": "resume_evidence_missing",
        "task_type": "project_practice",
        "rationale": "Build verifiable evidence",
        "learning_objective": "Apply the skill in a real project",
        "action_steps": ["Study fundamentals", "Build a feature"],
        "practice_task": "Build a small service",
        "deliverable": "A tested repository",
        "completion_criteria": ["Tests pass", "README is complete"],
        "estimated_hours": 8,
    }


def _count(session: Session, model, *criteria) -> int:
    statement = select(func.count()).select_from(model)
    if criteria:
        statement = statement.where(*criteria)
    return session.scalar(statement) or 0


def test_candidate_resume_versions_partial_unique_and_cascade(
    db_session: Session,
) -> None:
    candidate_repository = CandidateRepository(db_session)
    resume_repository = ResumeRepository(db_session)
    candidate = _create_candidate(db_session)
    first = _create_resume(db_session, candidate, version=1)
    second = _create_resume(db_session, candidate, version=2)

    assert candidate_repository.get_candidate_by_id(candidate.id) is candidate
    assert resume_repository.get_current_resume(candidate.id).id == second.id
    assert [item.id for item in resume_repository.list_resume_history(candidate.id)] == [
        first.id
    ]
    assert first.is_current is False
    assert second.is_current is True

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(
                Resume(
                    candidate_id=candidate.id,
                    title="Conflicting current resume",
                    resume_text="Another current resume",
                    content_sha256=_hash(),
                    version=3,
                    is_current=True,
                )
            )
            db_session.flush()

    db_session.delete(candidate)
    db_session.flush()
    assert _count(db_session, Resume, Resume.candidate_id == candidate.id) == 0


def test_job_skill_repositories_and_database_constraints(
    db_session: Session,
) -> None:
    job_repository = JobRepository(db_session)
    skill_repository = SkillRepository(db_session)
    job_skill_repository = JobSkillRepository(db_session)
    shared_hash = _hash()
    first_job = _create_job(db_session, source_sha256=shared_hash)
    second_job = _create_job(db_session, source_sha256=shared_hash)
    skill_name = f"  Python-{_token()}  "
    skill = skill_repository.create_skill(name=skill_name)

    assert skill.normalized_name == skill_name.strip().casefold()
    assert skill_repository.create_skill(name=skill_name.swapcase()) is skill
    assert len(job_repository.find_jobs_by_source_sha256(shared_hash)) == 2

    job_skill = _attach_skill(db_session, first_job, skill)
    assert job_skill_repository.get_job_skill_by_id(job_skill.id).id == job_skill.id
    assert job_skill_repository.list_job_skills(first_job.id) == [job_skill]

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(Skill(name=skill_name.upper()))
            db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            job_skill_repository.attach_skill_to_job(
                job_id=first_job.id,
                skill_id=skill.id,
                skill_category="required",
                position=2,
            )

    invalid_skill = _create_skill(db_session, "InvalidCategory")
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            job_skill_repository.attach_skill_to_job(
                job_id=first_job.id,
                skill_id=invalid_skill.id,
                skill_category="invalid",
                position=2,
            )

    invalid_position_skill = _create_skill(db_session, "InvalidPosition")
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            job_skill_repository.attach_skill_to_job(
                job_id=first_job.id,
                skill_id=invalid_position_skill.id,
                skill_category="preferred",
                position=0,
            )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(
                JobSkill(
                    job_id=first_job.id,
                    skill_id=uuid.uuid4(),
                    skill_name_snapshot="Missing skill",
                    skill_category="preferred",
                    position=3,
                )
            )
            db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.delete(skill)
            db_session.flush()

    db_session.delete(first_job)
    db_session.flush()
    assert _count(db_session, JobSkill, JobSkill.job_id == first_job.id) == 0


def test_analysis_repositories_constraints_and_delete_rules(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    job = _create_job(db_session)
    first_job_skill = _attach_skill(db_session, job, _create_skill(db_session))
    second_job_skill = _attach_skill(
        db_session,
        job,
        _create_skill(db_session, "FastAPI"),
        category="preferred",
        position=1,
    )
    run_repository = AnalysisRunRepository(db_session)
    match_repository = AnalysisSkillMatchRepository(db_session)
    analysis_run = _create_analysis_run(db_session, job, resume)
    match = match_repository.create_skill_match(
        analysis_run_id=analysis_run.id,
        job_skill_id=first_job_skill.id,
        status="evidence_found",
        evidence="Built a Python service",
    )

    assert run_repository.get_analysis_run_by_id(analysis_run.id).id == analysis_run.id
    assert run_repository.list_analysis_runs(job_id=job.id)[0].id == analysis_run.id
    assert match_repository.list_skill_matches(analysis_run.id)[0].id == match.id

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            match_repository.create_skill_match(
                analysis_run_id=analysis_run.id,
                job_skill_id=first_job_skill.id,
                status="evidence_found",
                evidence="Duplicate",
            )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            match_repository.create_skill_match(
                analysis_run_id=analysis_run.id,
                job_skill_id=second_job_skill.id,
                status="evidence_found",
                evidence=None,
            )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            run_repository.update_analysis_run(
                analysis_run.id,
                status="invalid",
            )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.delete(job)
            db_session.flush()

    db_session.delete(analysis_run)
    db_session.flush()
    assert _count(
        db_session,
        AnalysisSkillMatch,
        AnalysisSkillMatch.analysis_run_id == analysis_run.id,
    ) == 0


def test_analysis_run_repository_persists_valid_empty_json_defaults(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    job = _create_job(db_session)

    analysis_run = AnalysisRunRepository(db_session).create_analysis_run(
        job_id=job.id,
        resume_id=resume.id,
        run_type="learning_plan",
        status="running",
        current_stage="jd_analysis",
        model_provider="deepseek",
        model_name="deepseek-flash",
        pipeline_version="1",
    )
    db_session.refresh(analysis_run)

    assert analysis_run.jd_analysis_output is None
    assert analysis_run.resume_matching_output is None
    assert analysis_run.resume_improvement_suggestions == []
    assert analysis_run.learning_practice_suggestions == []


def test_analysis_cross_job_validation_and_batch_atomicity(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    first_job = _create_job(db_session)
    second_job = _create_job(db_session)
    valid_skill = _attach_skill(
        db_session, first_job, _create_skill(db_session, "Valid")
    )
    foreign_skill = _attach_skill(
        db_session, second_job, _create_skill(db_session, "Foreign")
    )
    analysis_run = _create_analysis_run(db_session, first_job, resume)
    repository = AnalysisSkillMatchRepository(db_session)

    with pytest.raises(ValueError, match="does not belong"):
        repository.create_skill_match(
            analysis_run_id=analysis_run.id,
            job_skill_id=foreign_skill.id,
            status="not_found_in_resume",
        )

    with pytest.raises(ValueError, match="does not belong"):
        repository.create_skill_matches(
            analysis_run_id=analysis_run.id,
            matches=[
                {
                    "job_skill_id": valid_skill.id,
                    "status": "not_found_in_resume",
                },
                {
                    "job_skill_id": foreign_skill.id,
                    "status": "not_found_in_resume",
                },
            ],
        )

    assert _count(
        db_session,
        AnalysisSkillMatch,
        AnalysisSkillMatch.analysis_run_id == analysis_run.id,
    ) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Current schema has no composite constraint tying AnalysisSkillMatch "
        "JobSkill.job_id to AnalysisRun.job_id."
    ),
)
def test_database_blocks_cross_job_analysis_match_when_repository_is_bypassed(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    first_job = _create_job(db_session)
    second_job = _create_job(db_session)
    foreign_skill = _attach_skill(
        db_session, second_job, _create_skill(db_session, "CrossJob")
    )
    analysis_run = _create_analysis_run(db_session, first_job, resume)

    with pytest.raises(IntegrityError):
        db_session.add(
            AnalysisSkillMatch(
                analysis_run_id=analysis_run.id,
                job_skill_id=foreign_skill.id,
                status="not_found_in_resume",
                evidence=None,
            )
        )
        db_session.flush()


def test_learning_plan_repositories_json_constraints_uniques_and_cascade(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    job = _create_job(db_session)
    skills = [
        _attach_skill(
            db_session,
            job,
            _create_skill(db_session, f"Skill{position}"),
            category="required" if position < 3 else "preferred",
            position=position if position < 3 else 1,
        )
        for position in range(1, 4)
    ]
    analysis_run = _create_analysis_run(db_session, job, resume)
    plan_repository = LearningPlanRepository(db_session)
    item_repository = LearningPlanItemRepository(db_session)
    plan = _create_plan(db_session, analysis_run)
    first_item = item_repository.create_learning_plan_item(
        learning_plan_id=plan.id,
        **_item_data(skills[0].id, 1),
    )

    assert plan_repository.get_learning_plan_by_analysis_run_id(
        analysis_run.id
    ).id == plan.id
    assert item_repository.list_learning_plan_items(plan.id) == [first_item]

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            plan_repository.create_learning_plan(
                analysis_run_id=analysis_run.id,
                plan_summary="Duplicate plan",
                full_output={"plan_summary": "Duplicate plan"},
                schema_version=1,
            )

    invalid_output_run = _create_analysis_run(db_session, job, resume)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            plan_repository.create_learning_plan(
                analysis_run_id=invalid_output_run.id,
                plan_summary="Invalid output",
                full_output=[],  # type: ignore[arg-type]
                schema_version=1,
            )

    second_item = item_repository.create_learning_plan_item(
        learning_plan_id=plan.id,
        **_item_data(skills[1].id, 2),
    )
    assert second_item.priority_order == 2

    for changes in (
        {"job_skill_id": skills[0].id, "priority_order": 3},
        {"job_skill_id": skills[2].id, "priority_order": 2},
        {
            "job_skill_id": skills[2].id,
            "priority_order": 3,
            "priority": "invalid",
        },
        {
            "job_skill_id": skills[2].id,
            "priority_order": 3,
            "action_steps": [],
        },
        {
            "job_skill_id": skills[2].id,
            "priority_order": 3,
            "completion_criteria": [],
        },
        {
            "job_skill_id": skills[2].id,
            "priority_order": 3,
            "rationale": "   ",
        },
        {
            "job_skill_id": skills[2].id,
            "priority_order": 3,
            "estimated_hours": 41,
        },
    ):
        item_values = _item_data(
            changes["job_skill_id"],
            changes["priority_order"],
        )
        item_values.update(changes)
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                item_repository.create_learning_plan_item(
                    learning_plan_id=plan.id,
                    **item_values,
                )

    db_session.delete(plan)
    db_session.flush()
    assert _count(
        db_session,
        LearningPlanItem,
        LearningPlanItem.learning_plan_id == plan.id,
    ) == 0


def test_learning_plan_cross_job_validation_and_batch_atomicity(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    first_job = _create_job(db_session)
    second_job = _create_job(db_session)
    valid_skill = _attach_skill(
        db_session, first_job, _create_skill(db_session, "PlanValid")
    )
    foreign_skill = _attach_skill(
        db_session, second_job, _create_skill(db_session, "PlanForeign")
    )
    analysis_run = _create_analysis_run(db_session, first_job, resume)
    plan = _create_plan(db_session, analysis_run)
    repository = LearningPlanItemRepository(db_session)

    with pytest.raises(ValueError, match="does not belong"):
        repository.create_learning_plan_item(
            learning_plan_id=plan.id,
            **_item_data(foreign_skill.id),
        )

    with pytest.raises(ValueError, match="does not belong"):
        repository.create_learning_plan_items(
            learning_plan_id=plan.id,
            items=[
                _item_data(valid_skill.id, 1),
                _item_data(foreign_skill.id, 2),
            ],
        )

    assert _count(
        db_session,
        LearningPlanItem,
        LearningPlanItem.learning_plan_id == plan.id,
    ) == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Current schema has no composite constraint tying LearningPlanItem "
        "JobSkill.job_id to the LearningPlan AnalysisRun.job_id."
    ),
)
def test_database_blocks_cross_job_learning_item_when_repository_is_bypassed(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    resume = _create_resume(db_session, candidate)
    first_job = _create_job(db_session)
    second_job = _create_job(db_session)
    foreign_skill = _attach_skill(
        db_session, second_job, _create_skill(db_session, "DirectForeign")
    )
    analysis_run = _create_analysis_run(db_session, first_job, resume)
    plan = _create_plan(db_session, analysis_run)

    with pytest.raises(IntegrityError):
        db_session.add(
            LearningPlanItem(
                learning_plan_id=plan.id,
                **_item_data(foreign_skill.id),
            )
        )
        db_session.flush()


def test_flush_rollback_and_failed_transaction_recovery(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session)
    candidate_id = candidate.id
    assert db_session.in_transaction()

    db_session.rollback()
    assert db_session.get(Candidate, candidate_id) is None
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1

    skill_name = f"Transaction-{_token()}"
    db_session.add(Skill(name=skill_name))
    db_session.flush()
    db_session.add(Skill(name=skill_name.swapcase()))

    with pytest.raises(IntegrityError):
        db_session.flush()
    with pytest.raises(PendingRollbackError):
        db_session.execute(select(Skill))

    db_session.rollback()
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1
