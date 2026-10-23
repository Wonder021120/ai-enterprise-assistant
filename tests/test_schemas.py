from app.schemas import JDLLMResult


def make_jd_result(
    required_skills: list[str],
    preferred_skills: list[str],
    **overrides,
) -> JDLLMResult:
    data = {
        "company": None,
        "job_title": None,
        "location": None,
        "recruitment_type": None,
        "education": None,
        "graduation_requirement": None,
        "experience_requirement": None,
        "salary": None,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
    }
    data.update(overrides)
    return JDLLMResult(**data)


def test_skill_lists_remove_exact_duplicates():
    result = make_jd_result(
        required_skills=["Python", "SQL", "Python", "SQL"],
        preferred_skills=["Docker", "Docker", "RAG", "RAG"],
    )

    assert result.required_skills == ["Python", "SQL"]
    assert result.preferred_skills == ["Docker", "RAG"]


def test_skill_lists_remove_case_insensitive_duplicates():
    result = make_jd_result(
        required_skills=["Python", "python", "PYTHON", "SQL"],
        preferred_skills=["FastAPI", "fastapi", "FASTAPI", "Docker"],
    )

    assert result.required_skills == ["Python", "SQL"]
    assert result.preferred_skills == ["FastAPI", "Docker"]


def test_required_skills_take_priority_over_preferred_skills():
    result = make_jd_result(
        required_skills=["Python", "SQL"],
        preferred_skills=["python", "Docker", "sql", "RAG", "PYTHON"],
    )

    assert result.required_skills == ["Python", "SQL"]
    assert result.preferred_skills == ["Docker", "RAG"]


def test_normal_skill_lists_and_other_fields_remain_unchanged():
    result = make_jd_result(
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker", "FastAPI"],
        company="示例科技",
        job_title="AI应用开发工程师",
        location="上海",
        recruitment_type="校招",
        education="硕士学历",
        graduation_requirement="2026届",
        experience_requirement="有后端项目经验",
        salary="20k-30k",
    )

    assert result.model_dump() == {
        "company": "示例科技",
        "job_title": "AI应用开发工程师",
        "location": "上海",
        "recruitment_type": "校招",
        "education": "硕士学历",
        "graduation_requirement": "2026届",
        "experience_requirement": "有后端项目经验",
        "salary": "20k-30k",
        "required_skills": ["Python", "SQL"],
        "preferred_skills": ["Docker", "FastAPI"],
    }


def test_empty_skill_lists_remain_empty():
    result = make_jd_result(
        required_skills=[],
        preferred_skills=[],
    )

    assert result.required_skills == []
    assert result.preferred_skills == []
