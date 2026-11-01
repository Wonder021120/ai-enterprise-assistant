"""CareerPilot AI 数据访问层。"""

from app.repositories.analysis_repository import (
    AnalysisRunRepository,
    AnalysisSkillMatchRepository,
)
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.job_repository import JobRepository
from app.repositories.job_skill_repository import JobSkillRepository
from app.repositories.learning_plan_repository import (
    LearningPlanItemRepository,
    LearningPlanRepository,
)
from app.repositories.resume_repository import ResumeRepository
from app.repositories.skill_repository import SkillRepository


__all__ = [
    "AnalysisRunRepository",
    "AnalysisSkillMatchRepository",
    "CandidateRepository",
    "JobRepository",
    "JobSkillRepository",
    "LearningPlanItemRepository",
    "LearningPlanRepository",
    "ResumeRepository",
    "SkillRepository",
]
