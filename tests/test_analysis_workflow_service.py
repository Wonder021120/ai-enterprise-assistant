from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.llm_service import LLMOutputError
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
from app.schemas import (
    JDLLMResult,
    LearningPlanItem,
    LearningPlanResponse,
    ResumeMatchingResponse,
    SkillMatchItem,
)
from app.services.analysis_workflow_service import (
    AnalysisWorkflowConsistencyError,
    AnalysisWorkflowService,
    WorkflowRepositories,
)


def _id(number: int) -> uuid.UUID:
    return uuid.UUID(int=number)


def _jd_analysis() -> JDLLMResult:
    return JDLLMResult(
        company="Example",
        job_title="Backend Engineer",
        location="Shanghai",
        recruitment_type="社招",
        education="本科",
        graduation_requirement=None,
        experience_requirement="2年后端经验",
        salary="20k-30k",
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker"],
    )


def _resume_matching() -> ResumeMatchingResponse:
    return ResumeMatchingResponse(
        required_skill_matches=[
            SkillMatchItem(
                skill="python",
                status="evidence_found",
                evidence="使用Python开发API",
            ),
            SkillMatchItem(
                skill="SQL",
                status="not_found_in_resume",
                evidence=None,
            ),
        ],
        preferred_skill_matches=[
            SkillMatchItem(
                skill="DOCKER",
                status="evidence_found",
                evidence="使用Docker部署服务",
            )
        ],
        match_summary="Python 与 Docker 有简历证据。",
        resume_improvement_suggestions=["补充SQL项目证据"],
        learning_practice_suggestions=["完成SQL练习"],
    )


def _learning_plan() -> LearningPlanResponse:
    return LearningPlanResponse(
        plan_summary="先补强必需技能，再深化加分技能。",
        plan_items=[
            LearningPlanItem(
                skill="SQL",
                skill_category="required",
                priority="high",
                priority_order=1,
                basis="resume_evidence_missing",
                task_type="project_practice",
                rationale="通过实践形成真实证据。",
                learning_objective="掌握常用查询。",
                action_steps=["设计表结构", "编写查询"],
                practice_task="完成数据查询项目。",
                deliverable="SQL脚本和测试结果。",
                completion_criteria=["查询结果正确"],
                estimated_hours=8,
            ),
            LearningPlanItem(
                skill="Python",
                skill_category="required",
                priority="medium",
                priority_order=2,
                basis="existing_evidence_to_strengthen",
                task_type="project_practice",
                rationale="深化已有项目证据。",
                learning_objective="提高后端工程质量。",
                action_steps=["补充测试"],
                practice_task="完善现有API。",
                deliverable="测试报告。",
                completion_criteria=["测试通过"],
                estimated_hours=6,
            ),
            LearningPlanItem(
                skill="docker",
                skill_category="preferred",
                priority="low",
                priority_order=3,
                basis="existing_evidence_to_strengthen",
                task_type="resume_revision",
                rationale="清晰呈现真实部署经验。",
                learning_objective="量化已有项目成果。",
                action_steps=["整理部署过程"],
                practice_task="复盘部署项目。",
                deliverable="项目说明。",
                completion_criteria=["信息可核验"],
                estimated_hours=3,
            ),
        ],
    )


@dataclass
class Harness:
    session: MagicMock
    repositories: WorkflowRepositories
    jd_analyzer: MagicMock
    resume_matcher: MagicMock
    learning_plan_generator: MagicMock
    candidate: SimpleNamespace
    resume: SimpleNamespace
    job: SimpleNamespace
    analysis_run: SimpleNamespace
    learning_plan_record: SimpleNamespace
    job_skill_ids: dict[tuple[str, str], uuid.UUID]

    def service(self) -> AnalysisWorkflowService:
        return AnalysisWorkflowService(
            self.session,
            repositories=self.repositories,
            jd_analyzer=self.jd_analyzer,
            resume_matcher=self.resume_matcher,
            learning_plan_generator=self.learning_plan_generator,
            model_name_getter=lambda: "deepseek-flash",
        )


@pytest.fixture
def harness() -> Harness:
    session = MagicMock(spec=Session)
    candidate_repository = MagicMock(spec=CandidateRepository)
    resume_repository = MagicMock(spec=ResumeRepository)
    job_repository = MagicMock(spec=JobRepository)
    skill_repository = MagicMock(spec=SkillRepository)
    job_skill_repository = MagicMock(spec=JobSkillRepository)
    analysis_run_repository = MagicMock(spec=AnalysisRunRepository)
    skill_match_repository = MagicMock(spec=AnalysisSkillMatchRepository)
    learning_plan_repository = MagicMock(spec=LearningPlanRepository)
    learning_plan_item_repository = MagicMock(
        spec=LearningPlanItemRepository
    )

    candidate = SimpleNamespace(id=_id(1), display_name="Alice")
    resume = SimpleNamespace(id=_id(2), version=1, is_current=True)
    job = SimpleNamespace(id=_id(3))
    analysis_run = SimpleNamespace(id=_id(4), job_id=job.id)
    learning_plan_record = SimpleNamespace(id=_id(5))

    candidate_repository.list_candidates.return_value = []
    candidate_repository.create_candidate.return_value = candidate
    resume_repository.get_current_resume.return_value = None
    resume_repository.list_resume_history.return_value = []
    resume_repository.create_resume.return_value = resume
    job_repository.create_job.return_value = job
    analysis_run_repository.create_analysis_run.return_value = analysis_run
    analysis_run_repository.update_analysis_run.return_value = analysis_run
    learning_plan_repository.create_learning_plan.return_value = (
        learning_plan_record
    )

    skill_ids = {
        "python": _id(11),
        "sql": _id(12),
        "docker": _id(13),
    }
    job_skill_ids = {
        ("required", "python"): _id(21),
        ("required", "sql"): _id(22),
        ("preferred", "docker"): _id(23),
    }

    def create_skill(*, name: str) -> SimpleNamespace:
        normalized = name.strip().casefold()
        return SimpleNamespace(id=skill_ids[normalized], name=name)

    skill_repository.create_skill.side_effect = create_skill

    def attach_skill_to_job(
        *,
        job_id: uuid.UUID,
        skill_id: uuid.UUID,
        skill_category: str,
        position: int,
    ) -> SimpleNamespace:
        normalized = next(
            name for name, identifier in skill_ids.items() if identifier == skill_id
        )
        return SimpleNamespace(
            id=job_skill_ids[(skill_category, normalized)],
            job_id=job_id,
            skill_id=skill_id,
            skill_category=skill_category,
            position=position,
        )

    job_skill_repository.attach_skill_to_job.side_effect = attach_skill_to_job
    skill_match_repository.create_skill_matches.return_value = [
        SimpleNamespace(id=_id(31)),
        SimpleNamespace(id=_id(32)),
        SimpleNamespace(id=_id(33)),
    ]
    learning_plan_item_repository.create_learning_plan_items.return_value = [
        SimpleNamespace(id=_id(41)),
        SimpleNamespace(id=_id(42)),
        SimpleNamespace(id=_id(43)),
    ]

    repositories = WorkflowRepositories(
        candidates=candidate_repository,
        resumes=resume_repository,
        jobs=job_repository,
        skills=skill_repository,
        job_skills=job_skill_repository,
        analysis_runs=analysis_run_repository,
        skill_matches=skill_match_repository,
        learning_plans=learning_plan_repository,
        learning_plan_items=learning_plan_item_repository,
    )
    return Harness(
        session=session,
        repositories=repositories,
        jd_analyzer=MagicMock(return_value=_jd_analysis()),
        resume_matcher=MagicMock(return_value=_resume_matching()),
        learning_plan_generator=MagicMock(return_value=_learning_plan()),
        candidate=candidate,
        resume=resume,
        job=job,
        analysis_run=analysis_run,
        learning_plan_record=learning_plan_record,
        job_skill_ids=job_skill_ids,
    )


def _run(harness: Harness):
    return harness.service().run(
        job_description="招聘 Python 后端工程师",
        resume_text="使用Python开发API，使用Docker部署服务",
        candidate_display_name="Alice",
        candidate_email="alice@example.com",
        resume_title="Backend Resume",
    )


def test_complete_workflow_persists_all_results(harness: Harness) -> None:
    result = _run(harness)

    assert result.candidate_id == harness.candidate.id
    assert result.resume_id == harness.resume.id
    assert result.job_id == harness.job.id
    assert result.analysis_run_id == harness.analysis_run.id
    assert result.learning_plan_id == harness.learning_plan_record.id
    assert result.required_job_skill_ids == (_id(21), _id(22))
    assert result.preferred_job_skill_ids == (_id(23),)
    assert result.analysis_skill_match_ids == (_id(31), _id(32), _id(33))
    assert result.learning_plan_item_ids == (_id(41), _id(42), _id(43))
    assert result.jd_analysis == _jd_analysis()
    assert result.resume_matching == _resume_matching()
    assert result.learning_plan == _learning_plan()
    assert harness.session.commit.call_count == 3
    harness.session.rollback.assert_not_called()


def test_llm_stages_receive_outputs_in_order(harness: Harness) -> None:
    events: list[str] = []
    harness.session.commit.side_effect = lambda: events.append("commit")
    harness.jd_analyzer.side_effect = lambda _jd: (
        events.append("jd_analysis") or _jd_analysis()
    )
    harness.resume_matcher.side_effect = lambda _jd, _resume: (
        events.append("resume_matching") or _resume_matching()
    )
    harness.learning_plan_generator.side_effect = lambda _jd, _match: (
        events.append("learning_plan") or _learning_plan()
    )

    _run(harness)

    assert events == [
        "jd_analysis",
        "commit",
        "resume_matching",
        "commit",
        "learning_plan",
        "commit",
    ]
    harness.jd_analyzer.assert_called_once_with("招聘 Python 后端工程师")
    harness.resume_matcher.assert_called_once_with(
        _jd_analysis(),
        "使用Python开发API，使用Docker部署服务",
    )
    harness.learning_plan_generator.assert_called_once_with(
        _jd_analysis(),
        _resume_matching(),
    )


def test_reuses_candidate_by_email(harness: Harness) -> None:
    existing = SimpleNamespace(id=_id(90), display_name="Existing")
    harness.repositories.candidates.list_candidates.return_value = [existing]
    harness.candidate = existing
    harness.repositories.resumes.create_resume.return_value = SimpleNamespace(
        id=_id(91), version=1, is_current=True
    )

    result = _run(harness)

    assert result.candidate_id == existing.id
    harness.repositories.candidates.create_candidate.assert_not_called()
    harness.repositories.resumes.create_resume.assert_called_once()
    assert (
        harness.repositories.resumes.create_resume.call_args.kwargs[
            "candidate_id"
        ]
        == existing.id
    )


def test_creates_candidate_when_email_is_not_found(harness: Harness) -> None:
    _run(harness)

    harness.repositories.candidates.create_candidate.assert_called_once_with(
        display_name="Alice",
        email="alice@example.com",
    )


def test_resume_version_increments_from_current_and_history(
    harness: Harness,
) -> None:
    harness.repositories.resumes.get_current_resume.return_value = (
        SimpleNamespace(version=3)
    )
    harness.repositories.resumes.list_resume_history.return_value = [
        SimpleNamespace(version=1),
        SimpleNamespace(version=2),
    ]

    _run(harness)

    create_kwargs = harness.repositories.resumes.create_resume.call_args.kwargs
    assert create_kwargs["version"] == 4
    assert create_kwargs["is_current"] is True


def test_job_skills_preserve_category_and_source_order(
    harness: Harness,
) -> None:
    _run(harness)

    calls = harness.repositories.job_skills.attach_skill_to_job.call_args_list
    assert [(item.kwargs["skill_category"], item.kwargs["position"]) for item in calls] == [
        ("required", 1),
        ("required", 2),
        ("preferred", 1),
    ]
    assert [item.kwargs["skill_id"] for item in calls] == [
        _id(11),
        _id(12),
        _id(13),
    ]


def test_skill_matches_are_saved_against_current_job_skills(
    harness: Harness,
) -> None:
    _run(harness)

    kwargs = harness.repositories.skill_matches.create_skill_matches.call_args.kwargs
    assert kwargs["analysis_run_id"] == harness.analysis_run.id
    assert kwargs["matches"] == [
        {
            "job_skill_id": _id(21),
            "status": "evidence_found",
            "evidence": "使用Python开发API",
        },
        {
            "job_skill_id": _id(22),
            "status": "not_found_in_resume",
            "evidence": None,
        },
        {
            "job_skill_id": _id(23),
            "status": "evidence_found",
            "evidence": "使用Docker部署服务",
        },
    ]


def test_learning_plan_and_items_are_saved_with_mapped_skills(
    harness: Harness,
) -> None:
    _run(harness)

    plan_kwargs = (
        harness.repositories.learning_plans.create_learning_plan.call_args.kwargs
    )
    assert plan_kwargs["analysis_run_id"] == harness.analysis_run.id
    assert plan_kwargs["full_output"] == _learning_plan().model_dump(mode="json")
    item_kwargs = (
        harness.repositories.learning_plan_items.create_learning_plan_items
        .call_args.kwargs
    )
    assert item_kwargs["learning_plan_id"] == harness.learning_plan_record.id
    assert [item["job_skill_id"] for item in item_kwargs["items"]] == [
        _id(22),
        _id(21),
        _id(23),
    ]
    assert [item["priority_order"] for item in item_kwargs["items"]] == [
        1,
        2,
        3,
    ]


@pytest.mark.parametrize(
    ("failed_stage", "expected_commits"),
    [
        ("jd_analysis", 0),
        ("resume_matching", 2),
        ("learning_plan", 3),
    ],
)
def test_llm_stage_failures_preserve_original_error_and_mark_stage(
    harness: Harness,
    failed_stage: str,
    expected_commits: int,
) -> None:
    error = LLMOutputError(f"{failed_stage} failed")
    if failed_stage == "jd_analysis":
        harness.jd_analyzer.side_effect = error
    elif failed_stage == "resume_matching":
        harness.resume_matcher.side_effect = error
    else:
        harness.learning_plan_generator.side_effect = error

    with pytest.raises(LLMOutputError) as captured:
        _run(harness)

    assert captured.value is error
    assert f"analysis_workflow_stage={failed_stage}" in error.__notes__
    assert harness.session.commit.call_count == expected_commits
    if failed_stage == "jd_analysis":
        harness.repositories.analysis_runs.create_analysis_run.assert_not_called()
        harness.repositories.analysis_runs.update_analysis_run.assert_not_called()
    else:
        failure_call = (
            harness.repositories.analysis_runs.update_analysis_run.call_args_list[
                -1
            ]
        )
        assert failure_call.kwargs["status"] == "failed"
        assert failure_call.kwargs["failure_stage"] == failed_stage
        assert failure_call.kwargs["error_type"] == "LLMOutputError"
        assert failure_call.kwargs["error_code"] == "analysis_failed"


def test_database_integrity_error_rolls_back_then_records_failure(
    harness: Harness,
) -> None:
    error = IntegrityError("INSERT", {}, Exception("constraint"))
    (
        harness.repositories.learning_plan_items.create_learning_plan_items
        .side_effect
    ) = error

    with pytest.raises(IntegrityError) as captured:
        _run(harness)

    assert captured.value is error
    assert harness.session.rollback.call_count == 1
    assert harness.session.commit.call_count == 3
    failure_call = (
        harness.repositories.analysis_runs.update_analysis_run.call_args_list[-1]
    )
    assert failure_call.kwargs["status"] == "failed"
    assert failure_call.kwargs["failure_stage"] == "learning_plan"
    assert failure_call.kwargs["error_type"] == "IntegrityError"
    assert (
        failure_call.kwargs["error_code"]
        == "database_persistence_failed"
    )
    assert (
        "analysis_workflow_failure_kind=database_persistence"
        in error.__notes__
    )


def test_invalid_skill_mapping_is_rejected_before_match_rows_are_added(
    harness: Harness,
) -> None:
    harness.resume_matcher.return_value = ResumeMatchingResponse(
        required_skill_matches=[
            SkillMatchItem(
                skill="Python",
                status="evidence_found",
                evidence="使用Python开发API",
            )
        ],
        preferred_skill_matches=_resume_matching().preferred_skill_matches,
        match_summary="缺少SQL匹配项。",
    )

    with pytest.raises(
        AnalysisWorkflowConsistencyError,
        match="required skill matches",
    ) as captured:
        _run(harness)

    harness.repositories.skill_matches.create_skill_matches.assert_not_called()
    failure_call = (
        harness.repositories.analysis_runs.update_analysis_run.call_args_list[-1]
    )
    assert failure_call.kwargs["failure_stage"] == "resume_matching"
    assert failure_call.kwargs["error_code"] == "skill_mapping_failed"
    assert (
        "analysis_workflow_failure_kind=skill_mapping"
        in captured.value.__notes__
    )


def test_duplicate_normalized_jd_skill_is_rejected_before_persistence(
    harness: Harness,
) -> None:
    duplicate_jd = _jd_analysis().model_copy(
        update={"required_skills": ["Python", " Python "]}
    )
    harness.jd_analyzer.return_value = duplicate_jd

    with pytest.raises(
        AnalysisWorkflowConsistencyError,
        match="duplicate skills",
    ):
        _run(harness)

    harness.repositories.candidates.create_candidate.assert_not_called()
    harness.session.commit.assert_not_called()


def test_initial_persistence_failure_rolls_back_and_stops_pipeline(
    harness: Harness,
) -> None:
    error = IntegrityError("INSERT", {}, Exception("constraint"))
    harness.repositories.jobs.create_job.side_effect = error

    with pytest.raises(IntegrityError) as captured:
        _run(harness)

    assert captured.value is error
    harness.session.rollback.assert_called_once_with()
    harness.session.commit.assert_not_called()
    harness.resume_matcher.assert_not_called()
    harness.learning_plan_generator.assert_not_called()


def test_rollback_failure_does_not_replace_original_llm_error(
    harness: Harness,
) -> None:
    original_error = LLMOutputError("matching failed")
    harness.resume_matcher.side_effect = original_error
    harness.session.rollback.side_effect = RuntimeError("rollback failed")

    with pytest.raises(LLMOutputError) as captured:
        _run(harness)

    assert captured.value is original_error
    assert "analysis_workflow_rollback=RuntimeError" in original_error.__notes__
    harness.repositories.analysis_runs.update_analysis_run.assert_not_called()


def test_ambiguous_candidate_email_is_not_silently_reused(
    harness: Harness,
) -> None:
    harness.repositories.candidates.list_candidates.return_value = [
        SimpleNamespace(id=_id(80)),
        SimpleNamespace(id=_id(81)),
    ]

    with pytest.raises(ValueError, match="unique"):
        _run(harness)

    harness.repositories.candidates.create_candidate.assert_not_called()
    harness.repositories.resumes.create_resume.assert_not_called()
    harness.session.rollback.assert_called_once_with()


def test_workflow_uses_only_existing_repository_interfaces() -> None:
    repository_specs = (
        CandidateRepository,
        ResumeRepository,
        JobRepository,
        SkillRepository,
        JobSkillRepository,
        AnalysisRunRepository,
        AnalysisSkillMatchRepository,
        LearningPlanRepository,
        LearningPlanItemRepository,
    )

    expected_methods = (
        (CandidateRepository, "create_candidate"),
        (CandidateRepository, "get_candidate_by_id"),
        (CandidateRepository, "list_candidates"),
        (ResumeRepository, "create_resume"),
        (ResumeRepository, "get_current_resume"),
        (ResumeRepository, "list_resume_history"),
        (JobRepository, "create_job"),
        (SkillRepository, "create_skill"),
        (JobSkillRepository, "attach_skill_to_job"),
        (AnalysisRunRepository, "create_analysis_run"),
        (AnalysisRunRepository, "update_analysis_run"),
        (AnalysisSkillMatchRepository, "create_skill_matches"),
        (LearningPlanRepository, "create_learning_plan"),
        (LearningPlanItemRepository, "create_learning_plan_items"),
    )

    assert len(repository_specs) == 9
    assert all(hasattr(repository, method) for repository, method in expected_methods)
