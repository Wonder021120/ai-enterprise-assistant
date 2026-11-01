export type SkillCategory = "required" | "preferred";
export type MatchStatus = "evidence_found" | "not_found_in_resume";
export type Priority = "high" | "medium" | "low";

export interface AnalysisWorkflowRequest {
  job_description: string;
  resume_text: string;
  candidate_id?: string;
  candidate_email?: string;
  candidate_display_name?: string;
  resume_title?: string;
}

export interface JDAnalysis {
  company: string | null;
  job_title: string | null;
  location: string | null;
  recruitment_type: string | null;
  education: string | null;
  graduation_requirement: string | null;
  experience_requirement: string | null;
  salary: string | null;
  required_skills: string[];
  preferred_skills: string[];
}

export interface SkillMatchItem {
  skill: string;
  status: MatchStatus;
  evidence: string | null;
}

export interface ResumeMatchingResponse {
  required_skill_matches: SkillMatchItem[];
  preferred_skill_matches: SkillMatchItem[];
  match_summary: string;
  resume_improvement_suggestions: string[];
  learning_practice_suggestions: string[];
}

export interface LearningPlanItem {
  skill: string;
  skill_category: SkillCategory;
  priority: Priority;
  priority_order: number;
  basis: "resume_evidence_missing" | "existing_evidence_to_strengthen";
  task_type: "learning" | "project_practice" | "resume_revision";
  rationale: string;
  learning_objective: string;
  action_steps: string[];
  practice_task: string;
  deliverable: string;
  completion_criteria: string[];
  estimated_hours: number;
}

export interface LearningPlanResponse {
  plan_summary: string;
  plan_items: LearningPlanItem[];
}

export interface AnalysisWorkflowResponse {
  candidate_id: string;
  resume_id: string;
  job_id: string;
  analysis_run_id: string;
  learning_plan_id: string;
  required_job_skill_ids: string[];
  preferred_job_skill_ids: string[];
  analysis_skill_match_ids: string[];
  learning_plan_item_ids: string[];
  jd_analysis: JDAnalysis;
  resume_matching: ResumeMatchingResponse;
  learning_plan: LearningPlanResponse;
}

export type ResultTab = "jd" | "matching" | "plan";
