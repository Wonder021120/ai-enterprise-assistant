"""CareerPilot AI 核心 ORM Models。"""

from app.db.models.analysis import AnalysisRun, AnalysisSkillMatch
from app.db.models.candidate import Candidate, Resume
from app.db.models.job import Job, JobSkill, Skill
from app.db.models.learning import LearningPlan, LearningPlanItem


__all__ = [
    "AnalysisRun",
    "AnalysisSkillMatch",
    "Candidate",
    "Job",
    "JobSkill",
    "LearningPlan",
    "LearningPlanItem",
    "Resume",
    "Skill",
]
