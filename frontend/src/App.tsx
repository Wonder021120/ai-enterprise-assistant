import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  BriefcaseBusiness,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Copy,
  FileText,
  GraduationCap,
  Layers3,
  Lightbulb,
  ListChecks,
  LoaderCircle,
  MapPin,
  Quote,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Target,
  Trophy,
  UserRound,
  WalletCards,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { analyzeWorkflow } from "./api";
import type {
  AnalysisWorkflowResponse,
  JDAnalysis,
  LearningPlanItem,
  MatchStatus,
  Priority,
  ResultTab,
  SkillMatchItem,
} from "./types";

interface FormState {
  jobDescription: string;
  resumeText: string;
  candidateId: string;
  candidateEmail: string;
  candidateDisplayName: string;
  resumeTitle: string;
}

const EMPTY_FORM: FormState = {
  jobDescription: "",
  resumeText: "",
  candidateId: "",
  candidateEmail: "",
  candidateDisplayName: "",
  resumeTitle: "",
};

const DEMO_FORM: FormState = {
  jobDescription:
    "职位：AI 产品经理\n\n公司：示例科技\n\n工作内容：\n负责 AI 应用产品需求分析、产品原型设计、用户调研和跨团队协作，参与企业级智能助手项目建设。\n\n任职要求：\n熟悉 AI 产品设计流程，了解大语言模型、Prompt Engineering、RAG 和 Agent 基础概念；具备 SQL 和数据分析基础。\n\n加分项：\n熟悉 Python、FastAPI，具有 AI 应用项目实践经验。",
  resumeText:
    "姓名：测试候选人\n\n教育背景：计算机科学硕士。\n\n项目经历：\n参与开发 CareerPilot AI 求职分析助手，使用 Python、FastAPI 和大语言模型实现岗位信息结构化分析、技能匹配和学习计划生成。\n\n技能：\nPython、SQL、FastAPI、Prompt Engineering，了解 RAG 和 Agent 基础概念。\n\n工作经历：\n参与 AI 应用需求整理、功能测试和项目文档编写。",
  candidateId: "",
  candidateEmail: "",
  candidateDisplayName: "测试候选人",
  resumeTitle: "AI 产品方向简历",
};

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const TAB_ITEMS: Array<{
  id: ResultTab;
  label: string;
  icon: LucideIcon;
}> = [
  { id: "jd", label: "岗位分析", icon: BriefcaseBusiness },
  { id: "matching", label: "技能匹配", icon: SearchCheck },
  { id: "plan", label: "学习计划", icon: GraduationCap },
];

function validateForm(form: FormState): string | null {
  if (!form.jobDescription.trim()) return "请填写岗位描述。";
  if (form.jobDescription.length > 20_000) {
    return "岗位描述不能超过 20,000 个字符。";
  }
  if (!form.resumeText.trim()) return "请填写简历内容。";
  if (form.resumeText.length > 30_000) {
    return "简历内容不能超过 30,000 个字符。";
  }
  if (form.candidateId && !UUID_PATTERN.test(form.candidateId.trim())) {
    return "候选人 ID 需要是有效的 UUID。";
  }
  if (form.candidateEmail && !EMAIL_PATTERN.test(form.candidateEmail.trim())) {
    return "请输入有效的候选人邮箱。";
  }
  if (form.candidateDisplayName.length > 200 || form.resumeTitle.length > 200) {
    return "候选人姓名和简历名称不能超过 200 个字符。";
  }
  return null;
}

function App() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [showCandidate, setShowCandidate] = useState(false);
  const [result, setResult] = useState<AnalysisWorkflowResponse | null>(null);
  const [activeTab, setActiveTab] = useState<ResultTab>("jd");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const resultsRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!isLoading) return;
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isLoading]);

  const updateField = (field: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    if (error) setError(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isLoading) return;

    const validationError = validateForm(form);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsLoading(true);
    setElapsedSeconds(0);
    setError(null);

    try {
      const response = await analyzeWorkflow({
        job_description: form.jobDescription,
        resume_text: form.resumeText,
        ...(form.candidateId.trim() && {
          candidate_id: form.candidateId.trim(),
        }),
        ...(form.candidateEmail.trim() && {
          candidate_email: form.candidateEmail.trim(),
        }),
        ...(form.candidateDisplayName.trim() && {
          candidate_display_name: form.candidateDisplayName.trim(),
        }),
        ...(form.resumeTitle.trim() && {
          resume_title: form.resumeTitle.trim(),
        }),
      });
      setResult(response);
      setActiveTab("jd");
      window.setTimeout(() => {
        if (window.innerWidth < 1080) {
          resultsRef.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }
      }, 100);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "分析请求失败，请稍后再试。",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const loadDemo = () => {
    if (isLoading) return;
    setForm(DEMO_FORM);
    setShowCandidate(true);
    setError(null);
    setResult(null);
  };

  const resetWorkspace = () => {
    if (isLoading) return;
    setForm(EMPTY_FORM);
    setResult(null);
    setError(null);
    setShowCandidate(false);
    setActiveTab("jd");
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CareerPilot AI 首页">
          <span className="brand-mark" aria-hidden="true">
            <BrainCircuit size={21} strokeWidth={2.2} />
          </span>
          <span>
            <strong>CareerPilot</strong>
            <em>AI</em>
          </span>
        </a>
        <div className="topbar-meta">
          <span className="status-dot" />
          三阶段智能分析
        </div>
      </header>

      <main id="top" className="page-content">
        <section className="hero">
          <div className="eyebrow">
            <Sparkles size={15} />
            AI 求职决策工作台
          </div>
          <h1>
            看清岗位差距，
            <span>把下一步变得具体。</span>
          </h1>
          <p>
            从岗位要求、简历证据到个性化学习计划，一次完成结构化分析，
            帮你把求职准备从“感觉”变成可执行的行动。
          </p>
          <div className="hero-flow" aria-label="分析流程">
            <span>岗位解析</span>
            <ArrowRight size={14} />
            <span>证据匹配</span>
            <ArrowRight size={14} />
            <span>学习计划</span>
          </div>
        </section>

        <div className="workspace-grid">
          <section className="input-panel" aria-labelledby="input-heading">
            <div className="panel-heading">
              <div>
                <span className="step-label">01 · 输入材料</span>
                <h2 id="input-heading">创建一次完整分析</h2>
              </div>
              <button
                type="button"
                className="text-button"
                onClick={loadDemo}
                disabled={isLoading}
              >
                载入示例
              </button>
            </div>

            <form onSubmit={handleSubmit} noValidate>
              <TextAreaField
                id="job-description"
                label="岗位描述"
                icon={BriefcaseBusiness}
                value={form.jobDescription}
                maxLength={20_000}
                placeholder="粘贴完整 JD，包括岗位职责、任职要求和加分项…"
                onChange={(value) => updateField("jobDescription", value)}
                disabled={isLoading}
              />

              <TextAreaField
                id="resume-text"
                label="简历内容"
                icon={FileText}
                value={form.resumeText}
                maxLength={30_000}
                placeholder="粘贴简历文本，包括项目、经历、技能和成果…"
                onChange={(value) => updateField("resumeText", value)}
                disabled={isLoading}
              />

              <div className={`candidate-section ${showCandidate ? "open" : ""}`}>
                <button
                  type="button"
                  className="candidate-toggle"
                  onClick={() => setShowCandidate((current) => !current)}
                  aria-expanded={showCandidate}
                  disabled={isLoading}
                >
                  <span>
                    <UserRound size={17} />
                    候选人信息
                    <small>选填</small>
                  </span>
                  <ChevronDown size={17} />
                </button>

                {showCandidate && (
                  <div className="candidate-fields">
                    <InputField
                      id="candidate-name"
                      label="姓名 / 展示名称"
                      value={form.candidateDisplayName}
                      placeholder="例如：测试候选人"
                      maxLength={200}
                      onChange={(value) =>
                        updateField("candidateDisplayName", value)
                      }
                      disabled={isLoading}
                    />
                    <InputField
                      id="candidate-email"
                      label="邮箱"
                      type="email"
                      value={form.candidateEmail}
                      placeholder="name@example.com"
                      maxLength={320}
                      onChange={(value) => updateField("candidateEmail", value)}
                      disabled={isLoading}
                    />
                    <InputField
                      id="resume-title"
                      label="简历名称"
                      value={form.resumeTitle}
                      placeholder="例如：AI 产品方向简历"
                      maxLength={200}
                      onChange={(value) => updateField("resumeTitle", value)}
                      disabled={isLoading}
                    />
                    <InputField
                      id="candidate-id"
                      label="已有候选人 ID"
                      value={form.candidateId}
                      placeholder="仅在复用已有档案时填写 UUID"
                      onChange={(value) => updateField("candidateId", value)}
                      disabled={isLoading}
                      fullWidth
                    />
                  </div>
                )}
              </div>

              {error && (
                <div className="error-banner" role="alert">
                  <CircleAlert size={18} />
                  <div>
                    <strong>本次分析未完成</strong>
                    <span>{error}</span>
                  </div>
                </div>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <LoaderCircle className="spin" size={19} />
                    正在分析 · {elapsedSeconds}s
                  </>
                ) : (
                  <>
                    开始完整分析
                    <ArrowRight size={19} />
                  </>
                )}
              </button>

              <div className="form-footnote">
                <ShieldCheck size={15} />
                内容仅发送至你的 CareerPilot 后端，不在浏览器中持久化
              </div>
            </form>
          </section>

          <section
            className="results-panel"
            ref={resultsRef}
            aria-labelledby="results-heading"
            aria-live="polite"
          >
            {isLoading ? (
              <LoadingState elapsedSeconds={elapsedSeconds} />
            ) : result ? (
              <ResultWorkspace
                result={result}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                onReset={resetWorkspace}
              />
            ) : (
              <EmptyState />
            )}
          </section>
        </div>
      </main>

      <footer className="site-footer">
        <span>CareerPilot AI</span>
        <span>把分析变成行动，把行动沉淀为证据。</span>
      </footer>
    </div>
  );
}

interface TextAreaFieldProps {
  id: string;
  label: string;
  icon: LucideIcon;
  value: string;
  maxLength: number;
  placeholder: string;
  onChange: (value: string) => void;
  disabled: boolean;
}

function TextAreaField({
  id,
  label,
  icon: Icon,
  value,
  maxLength,
  placeholder,
  onChange,
  disabled,
}: TextAreaFieldProps) {
  return (
    <div className="field-group textarea-group">
      <div className="field-label-row">
        <label htmlFor={id}>
          <Icon size={16} />
          {label}
          <span className="required-mark">必填</span>
        </label>
        <span className={value.length > maxLength ? "count over" : "count"}>
          {value.length.toLocaleString()} / {maxLength.toLocaleString()}
        </span>
      </div>
      <textarea
        id={id}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        rows={9}
      />
    </div>
  );
}

interface InputFieldProps {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  disabled: boolean;
  type?: "text" | "email";
  maxLength?: number;
  fullWidth?: boolean;
}

function InputField({
  id,
  label,
  value,
  placeholder,
  onChange,
  disabled,
  type = "text",
  maxLength,
  fullWidth = false,
}: InputFieldProps) {
  return (
    <div className={`compact-field ${fullWidth ? "full-width" : ""}`}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        autoComplete="off"
      />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-orbit" aria-hidden="true">
        <div className="orbit-ring ring-one" />
        <div className="orbit-ring ring-two" />
        <span className="orbit-core">
          <BrainCircuit size={32} />
        </span>
        <span className="orbit-node node-one"><Target size={17} /></span>
        <span className="orbit-node node-two"><SearchCheck size={17} /></span>
        <span className="orbit-node node-three"><BookOpenCheck size={17} /></span>
      </div>
      <span className="step-label">02 · 分析结果</span>
      <h2 id="results-heading">你的求职决策地图将在这里生成</h2>
      <p>提交岗位和简历后，CareerPilot 会完成三个彼此衔接的分析阶段。</p>
      <div className="empty-steps">
        <EmptyStep number="01" title="提炼岗位要求" text="区分必需技能与加分技能" />
        <EmptyStep number="02" title="核对简历证据" text="只保留简历原文中的真实依据" />
        <EmptyStep number="03" title="规划成长路径" text="生成有优先级和验收标准的任务" />
      </div>
    </div>
  );
}

function EmptyStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <div className="empty-step">
      <span>{number}</span>
      <div><strong>{title}</strong><small>{text}</small></div>
    </div>
  );
}

function LoadingState({ elapsedSeconds }: { elapsedSeconds: number }) {
  return (
    <div className="loading-state">
      <div className="loading-visual">
        <LoaderCircle className="spin" size={36} />
        <span className="pulse-dot pulse-one" />
        <span className="pulse-dot pulse-two" />
      </div>
      <span className="step-label">AI 正在工作</span>
      <h2 id="results-heading">正在构建你的求职分析</h2>
      <p>完整工作流包含三次深度分析，请保持页面开启。</p>
      <div className="loading-timeline">
        {TAB_ITEMS.map(({ label, icon: Icon }, index) => (
          <div className="loading-stage" key={label}>
            <span><Icon size={17} /></span>
            <div><strong>{label}</strong><small>阶段 {index + 1}</small></div>
          </div>
        ))}
      </div>
      <span className="elapsed">已用时 {elapsedSeconds} 秒</span>
    </div>
  );
}

interface ResultWorkspaceProps {
  result: AnalysisWorkflowResponse;
  activeTab: ResultTab;
  onTabChange: (tab: ResultTab) => void;
  onReset: () => void;
}

function ResultWorkspace({
  result,
  activeTab,
  onTabChange,
  onReset,
}: ResultWorkspaceProps) {
  const foundCount = [
    ...result.resume_matching.required_skill_matches,
    ...result.resume_matching.preferred_skill_matches,
  ].filter((item) => item.status === "evidence_found").length;
  const totalSkills =
    result.jd_analysis.required_skills.length +
    result.jd_analysis.preferred_skills.length;
  const totalHours = result.learning_plan.plan_items.reduce(
    (total, item) => total + item.estimated_hours,
    0,
  );

  return (
    <div className="result-workspace">
      <div className="result-header">
        <div>
          <span className="result-kicker"><CheckCircle2 size={15} /> 分析完成</span>
          <h2 id="results-heading">
            {result.jd_analysis.job_title ?? "岗位分析报告"}
          </h2>
          <p>
            {[result.jd_analysis.company, result.jd_analysis.location]
              .filter(Boolean)
              .join(" · ") || "已完成岗位、简历与学习路径的联合分析"}
          </p>
        </div>
        <button type="button" className="icon-button" onClick={onReset} title="重新分析">
          <RotateCcw size={17} />
          <span>重新分析</span>
        </button>
      </div>

      <div className="result-metrics">
        <Metric icon={Layers3} value={String(totalSkills)} label="岗位技能" />
        <Metric icon={SearchCheck} value={String(foundCount)} label="找到证据" />
        <Metric icon={ListChecks} value={String(result.learning_plan.plan_items.length)} label="行动任务" />
        <Metric icon={Clock3} value={`${totalHours}h`} label="预计投入" />
      </div>

      <div className="tabs" role="tablist" aria-label="分析结果视图">
        {TAB_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            className={activeTab === id ? "active" : ""}
            key={id}
            onClick={() => onTabChange(id)}
          >
            <Icon size={17} />
            {label}
          </button>
        ))}
      </div>

      <div className="tab-content" role="tabpanel">
        {activeTab === "jd" && <JDView analysis={result.jd_analysis} />}
        {activeTab === "matching" && (
          <MatchingView matching={result.resume_matching} />
        )}
        {activeTab === "plan" && (
          <LearningPlanView plan={result.learning_plan} />
        )}
      </div>

      <AnalysisId id={result.analysis_run_id} />
    </div>
  );
}

function Metric({ icon: Icon, value, label }: { icon: LucideIcon; value: string; label: string }) {
  return (
    <div className="metric">
      <span><Icon size={17} /></span>
      <div><strong>{value}</strong><small>{label}</small></div>
    </div>
  );
}

function JDView({ analysis }: { analysis: JDAnalysis }) {
  const details = [
    { icon: Building2, label: "公司", value: analysis.company },
    { icon: MapPin, label: "地点", value: analysis.location },
    { icon: BriefcaseBusiness, label: "招聘类型", value: analysis.recruitment_type },
    { icon: GraduationCap, label: "学历", value: analysis.education },
    { icon: Clock3, label: "经验要求", value: analysis.experience_requirement },
    { icon: WalletCards, label: "薪资", value: analysis.salary },
  ].filter((item) => item.value);

  return (
    <div className="view-stack">
      {details.length > 0 && (
        <div className="detail-grid">
          {details.map(({ icon: Icon, label, value }) => (
            <div className="detail-item" key={label}>
              <span><Icon size={16} /></span>
              <div><small>{label}</small><strong>{value}</strong></div>
            </div>
          ))}
        </div>
      )}
      {analysis.graduation_requirement && (
        <div className="notice-card"><GraduationCap size={18} /><div><strong>毕业要求</strong><p>{analysis.graduation_requirement}</p></div></div>
      )}
      <SkillSection
        title="必需技能"
        subtitle="岗位明确要求具备的核心能力"
        skills={analysis.required_skills}
        tone="required"
      />
      <SkillSection
        title="加分技能"
        subtitle="能够提升竞争力的额外能力"
        skills={analysis.preferred_skills}
        tone="preferred"
      />
    </div>
  );
}

function SkillSection({
  title,
  subtitle,
  skills,
  tone,
}: {
  title: string;
  subtitle: string;
  skills: string[];
  tone: "required" | "preferred";
}) {
  return (
    <section className="content-section">
      <div className="section-title"><div><h3>{title}</h3><p>{subtitle}</p></div><span>{skills.length} 项</span></div>
      {skills.length ? (
        <div className="skill-cloud">
          {skills.map((skill, index) => (
            <span className={`skill-chip ${tone}`} key={`${skill}-${index}`}>
              {tone === "required" ? <Target size={14} /> : <Sparkles size={14} />}
              {skill}
            </span>
          ))}
        </div>
      ) : (
        <div className="inline-empty">JD 中没有明确列出{title}</div>
      )}
    </section>
  );
}

function MatchingView({ matching }: { matching: AnalysisWorkflowResponse["resume_matching"] }) {
  const allMatches = [
    ...matching.required_skill_matches,
    ...matching.preferred_skill_matches,
  ];
  const foundCount = allMatches.filter((item) => item.status === "evidence_found").length;

  return (
    <div className="view-stack">
      <div className="summary-card">
        <div className="summary-icon"><SearchCheck size={22} /></div>
        <div><span>匹配结论</span><p>{matching.match_summary}</p></div>
        <strong>{foundCount}<small> / {allMatches.length}</small></strong>
      </div>
      <MatchGroup title="必需技能" matches={matching.required_skill_matches} />
      <MatchGroup title="加分技能" matches={matching.preferred_skill_matches} />
      <div className="suggestion-grid">
        <SuggestionCard icon={FileText} title="简历改进建议" items={matching.resume_improvement_suggestions} tone="blue" />
        <SuggestionCard icon={Lightbulb} title="学习与实践建议" items={matching.learning_practice_suggestions} tone="amber" />
      </div>
    </div>
  );
}

function MatchGroup({ title, matches }: { title: string; matches: SkillMatchItem[] }) {
  return (
    <section className="content-section">
      <div className="section-title"><div><h3>{title}</h3><p>基于简历原文逐项核对</p></div><span>{matches.length} 项</span></div>
      {matches.length ? (
        <div className="match-list">
          {matches.map((item, index) => (
            <MatchRow item={item} key={`${item.skill}-${index}`} />
          ))}
        </div>
      ) : (
        <div className="inline-empty">没有需要核对的{title}</div>
      )}
    </section>
  );
}

function MatchRow({ item }: { item: SkillMatchItem }) {
  const found = item.status === "evidence_found";
  return (
    <article className={`match-row ${found ? "found" : "missing"}`}>
      <span className="match-status-icon">
        {found ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
      </span>
      <div className="match-main">
        <div><strong>{item.skill}</strong><StatusBadge status={item.status} /></div>
        {item.evidence ? (
          <blockquote><Quote size={14} />{item.evidence}</blockquote>
        ) : (
          <p>简历中暂未找到足够证据，不代表你不具备该能力。</p>
        )}
      </div>
    </article>
  );
}

function StatusBadge({ status }: { status: MatchStatus }) {
  return (
    <span className={`status-badge ${status}`}>
      {status === "evidence_found" ? "已找到证据" : "暂未体现"}
    </span>
  );
}

function SuggestionCard({ icon: Icon, title, items, tone }: { icon: LucideIcon; title: string; items: string[]; tone: "blue" | "amber" }) {
  return (
    <section className={`suggestion-card ${tone}`}>
      <div className="suggestion-title"><span><Icon size={17} /></span><h3>{title}</h3></div>
      {items.length ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>暂无额外建议</p>}
    </section>
  );
}

function LearningPlanView({ plan }: { plan: AnalysisWorkflowResponse["learning_plan"] }) {
  const orderedItems = useMemo(
    () => [...plan.plan_items].sort((a, b) => a.priority_order - b.priority_order),
    [plan.plan_items],
  );
  const totalHours = orderedItems.reduce((total, item) => total + item.estimated_hours, 0);

  return (
    <div className="view-stack">
      <div className="plan-summary">
        <div><span><Trophy size={19} /></span><div><small>你的行动路线</small><p>{plan.plan_summary}</p></div></div>
        <strong>{totalHours}<small> 小时</small></strong>
      </div>
      <div className="plan-list">
        {orderedItems.map((item) => <PlanItemCard item={item} key={`${item.skill}-${item.priority_order}`} />)}
      </div>
    </div>
  );
}

function PlanItemCard({ item }: { item: LearningPlanItem }) {
  const taskLabels = {
    learning: "系统学习",
    project_practice: "项目实践",
    resume_revision: "简历优化",
  };
  return (
    <article className={`plan-card priority-${item.priority}`}>
      <div className="plan-order">{String(item.priority_order).padStart(2, "0")}</div>
      <div className="plan-body">
        <div className="plan-heading">
          <div><div className="plan-badges"><PriorityBadge priority={item.priority} /><span>{item.skill_category === "required" ? "必需技能" : "加分技能"}</span><span>{taskLabels[item.task_type]}</span></div><h3>{item.skill}</h3><p>{item.rationale}</p></div>
          <div className="hours"><Clock3 size={16} /><strong>{item.estimated_hours}h</strong></div>
        </div>
        <div className="objective"><Target size={17} /><div><small>学习目标</small><p>{item.learning_objective}</p></div></div>
        <div className="plan-columns">
          <PlanList icon={ListChecks} title="行动步骤" items={item.action_steps} />
          <PlanList icon={CheckCircle2} title="完成标准" items={item.completion_criteria} />
        </div>
        <div className="deliverables">
          <div><Wrench size={16} /><span><small>实践任务</small>{item.practice_task}</span></div>
          <div><Trophy size={16} /><span><small>最终产出</small>{item.deliverable}</span></div>
        </div>
      </div>
    </article>
  );
}

function PriorityBadge({ priority }: { priority: Priority }) {
  const labels: Record<Priority, string> = { high: "高优先级", medium: "中优先级", low: "低优先级" };
  return <span className={`priority-badge ${priority}`}>{labels[priority]}</span>;
}

function PlanList({ icon: Icon, title, items }: { icon: LucideIcon; title: string; items: string[] }) {
  return (
    <div className="plan-checklist"><h4><Icon size={16} />{title}</h4><ol>{items.map((item, index) => <li key={`${item}-${index}`}><span>{index + 1}</span>{item}</li>)}</ol></div>
  );
}

function AnalysisId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="analysis-id"><span>Analysis Run · {id}</span><button type="button" onClick={copyId} aria-label="复制分析 ID">{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "已复制" : "复制 ID"}</button></div>
  );
}

export default App;
