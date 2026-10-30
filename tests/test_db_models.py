from __future__ import annotations

import uuid

import pytest
from sqlalchemy import (
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, dialect
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
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


EXPECTED_TABLES = {
    "analysis_runs",
    "analysis_skill_matches",
    "candidates",
    "job_skills",
    "jobs",
    "learning_plan_items",
    "learning_plans",
    "resumes",
    "skills",
}

EXPECTED_COLUMNS = {
    "candidates": {
        "id": (UUID, False),
        "display_name": (String, True),
        "email": (String, True),
        "created_at": (DateTime, False),
        "updated_at": (DateTime, False),
    },
    "resumes": {
        "id": (UUID, False),
        "candidate_id": (UUID, False),
        "title": (String, True),
        "resume_text": (Text, False),
        "content_sha256": (CHAR, False),
        "version": (Integer, False),
        "is_current": (Boolean, False),
        "created_at": (DateTime, False),
        "updated_at": (DateTime, False),
    },
    "jobs": {
        "id": (UUID, False),
        "source_text": (Text, False),
        "source_sha256": (CHAR, False),
        "company": (Text, True),
        "job_title": (Text, True),
        "location": (Text, True),
        "recruitment_type": (Text, True),
        "education": (Text, True),
        "graduation_requirement": (Text, True),
        "experience_requirement": (Text, True),
        "salary": (Text, True),
        "schema_version": (SmallInteger, False),
        "created_at": (DateTime, False),
        "analyzed_at": (DateTime, True),
    },
    "skills": {
        "id": (UUID, False),
        "name": (Text, False),
        "normalized_name": (Text, False),
        "created_at": (DateTime, False),
    },
    "job_skills": {
        "id": (UUID, False),
        "job_id": (UUID, False),
        "skill_id": (UUID, False),
        "skill_name_snapshot": (Text, False),
        "skill_category": (String, False),
        "position": (SmallInteger, False),
        "created_at": (DateTime, False),
    },
    "analysis_runs": {
        "id": (UUID, False),
        "job_id": (UUID, False),
        "resume_id": (UUID, True),
        "run_type": (String, False),
        "status": (String, False),
        "current_stage": (String, True),
        "model_provider": (String, False),
        "model_name": (String, False),
        "pipeline_version": (String, False),
        "jd_analysis_output": (JSONB, True),
        "resume_matching_output": (JSONB, True),
        "match_summary": (Text, True),
        "resume_improvement_suggestions": (JSONB, True),
        "learning_practice_suggestions": (JSONB, True),
        "failure_stage": (String, True),
        "error_type": (String, True),
        "error_code": (String, True),
        "started_at": (DateTime, False),
        "completed_at": (DateTime, True),
        "created_at": (DateTime, False),
    },
    "analysis_skill_matches": {
        "id": (UUID, False),
        "analysis_run_id": (UUID, False),
        "job_skill_id": (UUID, False),
        "status": (String, False),
        "evidence": (Text, True),
        "created_at": (DateTime, False),
    },
    "learning_plans": {
        "id": (UUID, False),
        "analysis_run_id": (UUID, False),
        "plan_summary": (String, False),
        "full_output": (JSONB, False),
        "schema_version": (SmallInteger, False),
        "created_at": (DateTime, False),
    },
    "learning_plan_items": {
        "id": (UUID, False),
        "learning_plan_id": (UUID, False),
        "job_skill_id": (UUID, False),
        "priority": (String, False),
        "priority_order": (SmallInteger, False),
        "basis": (String, False),
        "task_type": (String, False),
        "rationale": (String, False),
        "learning_objective": (String, False),
        "action_steps": (JSONB, False),
        "practice_task": (String, False),
        "deliverable": (String, False),
        "completion_criteria": (JSONB, False),
        "estimated_hours": (SmallInteger, False),
        "created_at": (DateTime, False),
    },
}

EXPECTED_FOREIGN_KEYS = {
    ("resumes", "candidate_id"): ("candidates.id", "CASCADE"),
    ("job_skills", "job_id"): ("jobs.id", "CASCADE"),
    ("job_skills", "skill_id"): ("skills.id", "RESTRICT"),
    ("analysis_runs", "job_id"): ("jobs.id", "RESTRICT"),
    ("analysis_runs", "resume_id"): ("resumes.id", "CASCADE"),
    ("analysis_skill_matches", "analysis_run_id"): (
        "analysis_runs.id",
        "CASCADE",
    ),
    ("analysis_skill_matches", "job_skill_id"): (
        "job_skills.id",
        "RESTRICT",
    ),
    ("learning_plans", "analysis_run_id"): (
        "analysis_runs.id",
        "CASCADE",
    ),
    ("learning_plan_items", "learning_plan_id"): (
        "learning_plans.id",
        "CASCADE",
    ),
    ("learning_plan_items", "job_skill_id"): (
        "job_skills.id",
        "RESTRICT",
    ),
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    "resumes": {("candidate_id", "version")},
    "skills": {("normalized_name",)},
    "job_skills": {
        ("job_id", "skill_id"),
        ("job_id", "skill_category", "position"),
    },
    "analysis_skill_matches": {("analysis_run_id", "job_skill_id")},
    "learning_plans": {("analysis_run_id",)},
    "learning_plan_items": {
        ("learning_plan_id", "job_skill_id"),
        ("learning_plan_id", "priority_order"),
    },
}

EXPECTED_CHECK_NAMES = {
    "resumes": {
        "ck_resumes_version_positive",
        "ck_resumes_resume_text_length",
        "ck_resumes_resume_text_nonblank",
    },
    "jobs": {
        "ck_jobs_source_text_length",
        "ck_jobs_source_text_nonblank",
        "ck_jobs_schema_version_positive",
    },
    "skills": {
        "ck_skills_name_nonblank",
        "ck_skills_normalized_name_nonblank",
    },
    "job_skills": {
        "ck_job_skills_skill_category_allowed",
        "ck_job_skills_position_positive",
        "ck_job_skills_skill_name_snapshot_nonblank",
    },
    "analysis_runs": {
        "ck_analysis_runs_run_type_allowed",
        "ck_analysis_runs_status_allowed",
        "ck_analysis_runs_current_stage_allowed",
        "ck_analysis_runs_failure_stage_allowed",
        "ck_analysis_runs_jd_analysis_output_object",
        "ck_analysis_runs_resume_matching_output_object",
        "ck_analysis_runs_resume_improvement_suggestions_array",
        "ck_analysis_runs_learning_practice_suggestions_array",
        "ck_analysis_runs_resume_required_for_pipeline_run",
    },
    "analysis_skill_matches": {
        "ck_analysis_skill_matches_status_allowed",
        "ck_analysis_skill_matches_evidence_matches_status",
    },
    "learning_plans": {
        "ck_learning_plans_plan_summary_nonblank",
        "ck_learning_plans_schema_version_positive",
        "ck_learning_plans_full_output_object",
    },
    "learning_plan_items": {
        "ck_learning_plan_items_priority_allowed",
        "ck_learning_plan_items_priority_order_positive",
        "ck_learning_plan_items_basis_allowed",
        "ck_learning_plan_items_task_type_allowed",
        "ck_learning_plan_items_estimated_hours_range",
        "ck_learning_plan_items_rationale_nonblank",
        "ck_learning_plan_items_learning_objective_nonblank",
        "ck_learning_plan_items_practice_task_nonblank",
        "ck_learning_plan_items_deliverable_nonblank",
        "ck_learning_plan_items_action_steps_array_length",
        "ck_learning_plan_items_completion_criteria_array_length",
    },
}


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _check_names(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_all_nine_models_are_exported_and_registered() -> None:
    assert {
        Candidate,
        Resume,
        Job,
        Skill,
        JobSkill,
        AnalysisRun,
        AnalysisSkillMatch,
        LearningPlan,
        LearningPlanItem,
    }
    assert set(Base.metadata.tables) == EXPECTED_TABLES


@pytest.mark.parametrize("table_name", sorted(EXPECTED_COLUMNS))
def test_column_types_and_nullability(table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    expected = EXPECTED_COLUMNS[table_name]

    assert set(table.columns.keys()) == set(expected)
    for column_name, (expected_type, expected_nullable) in expected.items():
        column = table.c[column_name]
        assert isinstance(column.type, expected_type)
        assert column.nullable is expected_nullable


def test_primary_keys_are_application_generated_postgresql_uuids() -> None:
    for table_name in EXPECTED_TABLES:
        table = Base.metadata.tables[table_name]
        assert [column.name for column in table.primary_key.columns] == ["id"]
        id_column = table.c.id
        assert isinstance(id_column.type, UUID)
        assert id_column.type.as_uuid is True
        assert id_column.default is not None
        assert id_column.default.arg.__wrapped__ is uuid.uuid4
        assert isinstance(id_column.default.arg(None), uuid.UUID)


def test_declared_string_lengths_and_timezone_columns() -> None:
    expected_lengths = {
        ("candidates", "display_name"): 200,
        ("candidates", "email"): 320,
        ("resumes", "title"): 200,
        ("resumes", "content_sha256"): 64,
        ("jobs", "source_sha256"): 64,
        ("job_skills", "skill_category"): 10,
        ("analysis_runs", "run_type"): 32,
        ("analysis_runs", "status"): 16,
        ("analysis_runs", "current_stage"): 32,
        ("analysis_runs", "model_provider"): 50,
        ("analysis_runs", "model_name"): 100,
        ("analysis_runs", "pipeline_version"): 32,
        ("analysis_runs", "failure_stage"): 32,
        ("analysis_runs", "error_type"): 100,
        ("analysis_runs", "error_code"): 100,
        ("analysis_skill_matches", "status"): 32,
        ("learning_plans", "plan_summary"): 1000,
        ("learning_plan_items", "priority"): 10,
        ("learning_plan_items", "basis"): 50,
        ("learning_plan_items", "task_type"): 32,
        ("learning_plan_items", "rationale"): 500,
        ("learning_plan_items", "learning_objective"): 500,
        ("learning_plan_items", "practice_task"): 500,
        ("learning_plan_items", "deliverable"): 500,
    }
    for (table_name, column_name), length in expected_lengths.items():
        assert Base.metadata.tables[table_name].c[column_name].type.length == length

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True
                if not column.nullable or column.name == "created_at":
                    assert column.server_default is not None


def test_foreign_key_targets_and_delete_rules() -> None:
    actual = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                actual[(table.name, column.name)] = (
                    foreign_key.target_fullname,
                    foreign_key.ondelete,
                )

    assert actual == EXPECTED_FOREIGN_KEYS


def test_skill_normalized_name_is_derived_in_python() -> None:
    skill = Skill(name="  PyThOn  ")
    assert skill.name == "  PyThOn  "
    assert skill.normalized_name == "python"

    skill.name = "Straße"
    assert skill.normalized_name == "strasse"


def test_unique_constraints_match_design() -> None:
    for table_name in EXPECTED_TABLES:
        assert _unique_column_sets(table_name) == EXPECTED_UNIQUE_CONSTRAINTS.get(
            table_name,
            set(),
        )


def test_named_check_constraints_match_design() -> None:
    for table_name in EXPECTED_TABLES:
        assert _check_names(table_name) == EXPECTED_CHECK_NAMES.get(
            table_name,
            set(),
        )


def test_jsonb_array_checks_use_safe_case_expressions() -> None:
    item_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables[
            "learning_plan_items"
        ].constraints
        if isinstance(constraint, CheckConstraint)
    }
    for suffix in (
        "action_steps_array_length",
        "completion_criteria_array_length",
    ):
        expression = item_checks[f"ck_learning_plan_items_{suffix}"].lower()
        assert expression.startswith("case when jsonb_typeof")
        assert "jsonb_array_length" in expression
        assert "between 1 and 8" in expression
        assert "else false end" in expression


def test_index_names_and_columns_match_design() -> None:
    actual = {
        table.name: {
            index.name: tuple(
                getattr(expression, "name", None)
                for expression in index.expressions
            )
            for index in table.indexes
        }
        for table in Base.metadata.tables.values()
    }

    assert actual == {
        "candidates": {},
        "resumes": {
            "uq_resumes_candidate_id_current": ("candidate_id",),
        },
        "jobs": {
            "ix_jobs_job_title": ("job_title",),
            "ix_jobs_source_sha256": ("source_sha256",),
        },
        "skills": {},
        "job_skills": {
            "ix_job_skills_skill_id": ("skill_id",),
        },
        "analysis_runs": {
            "ix_analysis_runs_job_id_created_at_desc": (
                "job_id",
                None,
            ),
            "ix_analysis_runs_resume_id_created_at_desc": (
                "resume_id",
                None,
            ),
            "ix_analysis_runs_run_type_created_at_desc": (
                "run_type",
                None,
            ),
            "ix_analysis_runs_status_created_at_desc": (
                "status",
                None,
            ),
            "ix_analysis_runs_failure_stage_error_code": (
                "failure_stage",
                "error_code",
            ),
        },
        "analysis_skill_matches": {
            "ix_analysis_skill_matches_job_skill_id": ("job_skill_id",),
            "ix_analysis_skill_matches_status": ("status",),
        },
        "learning_plans": {},
        "learning_plan_items": {
            "ix_learning_plan_items_job_skill_id": ("job_skill_id",),
            "ix_learning_plan_items_priority": ("priority",),
        },
    }

    current_index = next(iter(Base.metadata.tables["resumes"].indexes))
    assert current_index.unique is True
    assert str(current_index.dialect_options["postgresql"]["where"]) == (
        "is_current"
    )

    all_index_names = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }
    assert "ix_job_skills_job_id_skill_category_position" not in all_index_names
    assert "ix_analysis_skill_matches_analysis_run_id" not in all_index_names
    assert "ix_learning_plan_items_learning_plan_id_priority_order" not in (
        all_index_names
    )


def test_relationships_configure_with_expected_back_populates() -> None:
    configure_mappers()
    expected = {
        Candidate: {"resumes": "candidate"},
        Resume: {"candidate": "resumes", "analysis_runs": "resume"},
        Job: {"job_skills": "job", "analysis_runs": "job"},
        Skill: {"job_skills": "skill"},
        JobSkill: {
            "job": "job_skills",
            "skill": "job_skills",
            "analysis_skill_matches": "job_skill",
            "learning_plan_items": "job_skill",
        },
        AnalysisRun: {
            "job": "analysis_runs",
            "resume": "analysis_runs",
            "skill_matches": "analysis_run",
            "learning_plan": "analysis_run",
        },
        AnalysisSkillMatch: {
            "analysis_run": "skill_matches",
            "job_skill": "analysis_skill_matches",
        },
        LearningPlan: {"analysis_run": "learning_plan", "items": "learning_plan"},
        LearningPlanItem: {
            "learning_plan": "items",
            "job_skill": "learning_plan_items",
        },
    }

    for model, relationships in expected.items():
        assert {
            relationship.key: relationship.back_populates
            for relationship in model.__mapper__.relationships
        } == relationships


def test_postgresql_ddl_and_indexes_compile_without_execution() -> None:
    postgresql = dialect()

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=postgresql))
        assert f"CREATE TABLE {table.name}" in ddl
        for index in table.indexes:
            index_ddl = str(CreateIndex(index).compile(dialect=postgresql))
            assert index.name in index_ddl

    learning_item_ddl = str(
        CreateTable(Base.metadata.tables["learning_plan_items"]).compile(
            dialect=postgresql
        )
    )
    assert "JSONB" in learning_item_ddl
    assert "CASE WHEN jsonb_typeof(action_steps) = 'array'" in learning_item_ddl
