import pytest
from pydantic import ValidationError

from app.schemas import (
    JDAnalysisRequest,
    JDLLMResult,
    ResumeMatchingRequest,
    ResumeMatchingResponse,
    SkillMatchItem,
)


def test_valid_resume_matching_request_passes():
    request = ResumeMatchingRequest(
        job_description="招聘Python工程师，要求熟悉FastAPI。",
        resume_text="使用Python和FastAPI开发过后端项目。",
    )

    assert request.job_description == "招聘Python工程师，要求熟悉FastAPI。"
    assert request.resume_text == "使用Python和FastAPI开发过后端项目。"


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("job_description", ""),
        ("job_description", " \t\n"),
        ("resume_text", ""),
        ("resume_text", " \t\n"),
    ],
)
def test_resume_matching_request_rejects_empty_or_blank_text(
    field_name,
    invalid_value,
):
    data = {
        "job_description": "招聘Python工程师。",
        "resume_text": "拥有Python项目经验。",
    }
    data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        ResumeMatchingRequest(**data)


def test_job_description_length_boundaries():
    request = ResumeMatchingRequest(
        job_description="A" * 20_000,
        resume_text="有效简历内容",
    )

    assert len(request.job_description) == 20_000

    with pytest.raises(ValidationError):
        ResumeMatchingRequest(
            job_description="A" * 20_001,
            resume_text="有效简历内容",
        )


def test_resume_text_length_boundaries():
    request = ResumeMatchingRequest(
        job_description="有效JD内容",
        resume_text="A" * 30_000,
    )

    assert len(request.resume_text) == 30_000

    with pytest.raises(ValidationError):
        ResumeMatchingRequest(
            job_description="有效JD内容",
            resume_text="A" * 30_001,
        )


@pytest.mark.parametrize("evidence", [None, "", " \t\n"])
def test_evidence_found_rejects_missing_or_blank_evidence(evidence):
    with pytest.raises(ValidationError):
        SkillMatchItem(
            skill="Python",
            status="evidence_found",
            evidence=evidence,
        )


def test_not_found_in_resume_rejects_non_none_evidence():
    with pytest.raises(ValidationError):
        SkillMatchItem(
            skill="Docker",
            status="not_found_in_resume",
            evidence="简历中提到了Docker",
        )


def test_both_valid_skill_match_statuses_pass():
    evidence_found = SkillMatchItem(
        skill="Python",
        status="evidence_found",
        evidence="使用Python开发数据处理服务",
    )
    not_found = SkillMatchItem(
        skill="Docker",
        status="not_found_in_resume",
    )

    assert evidence_found.evidence == "使用Python开发数据处理服务"
    assert not_found.evidence is None


@pytest.mark.parametrize("skill", ["", " \t\n"])
def test_skill_match_item_rejects_empty_or_blank_skill(skill):
    with pytest.raises(ValidationError):
        SkillMatchItem(
            skill=skill,
            status="not_found_in_resume",
        )


def test_response_list_defaults_are_independent():
    first = ResumeMatchingResponse(match_summary="第一份匹配结果")
    second = ResumeMatchingResponse(match_summary="第二份匹配结果")

    first.required_skill_matches.append(
        SkillMatchItem(
            skill="Python",
            status="not_found_in_resume",
        )
    )
    first.preferred_skill_matches.append(
        SkillMatchItem(
            skill="Docker",
            status="not_found_in_resume",
        )
    )
    first.resume_improvement_suggestions.append("补充项目成果")
    first.learning_practice_suggestions.append("完成一个FastAPI项目")

    assert second.required_skill_matches == []
    assert second.preferred_skill_matches == []
    assert second.resume_improvement_suggestions == []
    assert second.learning_practice_suggestions == []


def test_existing_jd_schemas_keep_their_behavior():
    request = JDAnalysisRequest(job_description="有效JD内容")
    result = JDLLMResult(
        company=None,
        job_title="Python工程师",
        location=None,
        recruitment_type=None,
        education=None,
        graduation_requirement=None,
        experience_requirement=None,
        salary=None,
        required_skills=["Python", "python", "SQL"],
        preferred_skills=["PYTHON", "Docker"],
    )

    assert request.job_description == "有效JD内容"
    assert result.required_skills == ["Python", "SQL"]
    assert result.preferred_skills == ["Docker"]
