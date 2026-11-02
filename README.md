# CareerPilot AI

An AI-powered job analysis and learning-planning platform built with FastAPI, DeepSeek, PostgreSQL, and React.

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139.2-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111827)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

> CareerPilot AI turns a job description and a text resume into structured job requirements, evidence-based skill matching, and an actionable learning plan. It is a backend-orchestrated, three-stage AI workflow—not an autonomous agent or a RAG system.

## Project Overview

Job descriptions are often unstructured, while resumes do not make every relevant skill easy to verify. CareerPilot AI helps job seekers convert those two documents into a practical preparation plan.

The application is designed for students, graduates, and career changers who want to answer three questions:

1. What does this role actually require?
2. Which requirements are supported by evidence in my resume?
3. What should I learn, build, or improve next?

The project combines LLM-based semantic analysis with deterministic Python validation. DeepSeek generates structured content; Pydantic and service-layer rules validate the output, reconcile skills, verify quoted resume evidence, and assign learning priorities. The complete workflow can persist its inputs and outputs to PostgreSQL for traceability.

## Core Features

### Job Description Analysis

- Accepts raw job-description text up to 20,000 characters.
- Extracts company, role, location, recruitment type, education, graduation requirements, experience requirements, salary, required skills, and preferred skills.
- Deduplicates skills case-insensitively while preserving their first spelling and order.
- Removes required skills from the preferred-skill list when the same skill appears in both.

### Resume-to-Job Matching

- Matches only the required and preferred skills produced by JD analysis.
- Uses the LLM for semantic judgment across projects, responsibilities, technologies, and outcomes.
- Requires `evidence_found` items to include a short verbatim excerpt from the resume.
- Rechecks each excerpt in Python; unsupported evidence is downgraded to `not_found_in_resume`.
- Fills omitted skills deterministically and removes skills that were not present in the JD.

### Skill Gap Identification

- Separates required skills from preferred skills throughout the pipeline.
- Treats missing resume evidence as an evidence gap, not proof that the candidate lacks the skill.
- Produces resume-improvement and learning/practice suggestions without inventing experience.

### Personalized Learning Plan

- Produces one task for every JD skill, with a rationale, learning objective, action steps, practice task, deliverable, completion criteria, and estimated hours.
- Assigns category, evidence basis, priority, and execution order in deterministic Python code.
- Prioritizes missing evidence for required skills before lower-impact items.
- Rejects missing, duplicate, extra, or structurally invalid learning tasks.

### Multi-stage AI Workflow

- Orchestrates JD Analysis → Resume Matching → Learning Plan Generation.
- Keeps each LLM stage independently validated and observable.
- Uses short database transactions instead of holding a transaction open during LLM calls.
- Records success or failure state, current/failure stage, model metadata, and structured outputs.

### Persistent Data Management

- Stores candidates, versioned resumes, jobs, normalized skills, analysis runs, skill matches, and learning plans.
- Uses SQLAlchemy 2.x repositories to separate persistence from workflow logic.
- Uses PostgreSQL constraints, JSONB fields, foreign keys, unique indexes, and Alembic migrations.
- Returns database UUIDs together with all three structured analysis results from the full workflow endpoint.

## System Architecture

```mermaid
flowchart LR
    User[Job Seeker] --> UI[React + TypeScript Frontend]
    UI -->|HTTP /analyze/workflow| API[FastAPI Backend]

    subgraph Application[Application Layer]
        API --> Workflow[AnalysisWorkflowService]
        Workflow --> JD[JD Analysis Service]
        Workflow --> Match[Resume Matching Service]
        Workflow --> Plan[Learning Plan Service]
    end

    JD --> SDK[OpenAI Python SDK]
    Match --> SDK
    Plan --> SDK
    SDK -->|JSON Output mode| DeepSeek[DeepSeek Chat Completions API]

    Workflow --> Repositories[Repository Layer]
    Repositories --> ORM[SQLAlchemy ORM]
    ORM --> DB[(PostgreSQL)]
    Alembic[Alembic Migrations] -. schema versioning .-> DB
```

The React development server proxies `/analyze` and `/health` to FastAPI. In the Docker topology, Nginx serves the production frontend and proxies the same paths to the backend container.

## AI Workflow

```mermaid
flowchart TD
    Input[JD text + resume text] --> Validate[Pydantic request validation]
    Validate --> S1[Stage 1: JD Analysis]
    S1 --> JDResult[Validated JDLLMResult]
    JDResult --> S2[Stage 2: Resume Matching]
    Input --> S2
    S2 --> Evidence[Skill reconciliation + verbatim evidence check]
    Evidence --> MatchResult[Validated ResumeMatchingResponse]
    JDResult --> S3[Stage 3: Learning Plan Generation]
    MatchResult --> S3
    S3 --> Rules[Deterministic category, basis, priority, and order]
    Rules --> PlanResult[Validated LearningPlanResponse]
    JDResult --> Persist[PostgreSQL persistence]
    MatchResult --> Persist
    PlanResult --> Persist
    Persist --> Response[Workflow response + database UUIDs]
```

### Stage 1: JD Analysis

The backend sends the raw JD to DeepSeek and requests a JSON object. The response is decoded with `json.loads()` and validated as `JDLLMResult`. Pydantic then normalizes duplicate and cross-list skills without changing unrelated fields.

### Stage 2: Resume Matching

The matching service sends the validated required/preferred skills and resume text to DeepSeek. The model classifies every skill as `evidence_found` or `not_found_in_resume`. Python then restores the JD's canonical skill names and order, removes extra skills, fills omissions, and verifies that every quoted evidence fragment occurs verbatim in the resume.

### Stage 3: Learning Plan Generation

The learning-plan service receives only the structured JD and resume-matching result—not the full resume. DeepSeek generates the learning content, while Python determines the business-critical fields:

| Skill category | Resume evidence | Priority |
|---|---|---|
| Required | Not found | High |
| Required | Found | Medium |
| Preferred | Not found | Medium |
| Preferred | Found | Low |

Items are ordered by required before preferred, missing evidence before existing evidence, and original JD order within the same level. The final `priority_order` is continuous and starts at 1.

### Structured-output safeguards

All three stages use DeepSeek's JSON Output mode through the OpenAI-compatible SDK. Provider output is not trusted on its own. The services also check:

- missing choices, empty content, model refusal, abnormal finish reasons, and token truncation;
- JSON decoding failures and Pydantic schema violations;
- missing, duplicate, extra, or cross-category skills;
- fabricated resume evidence;
- unsupported learning-plan tasks and invalid priorities/order.

SDK rate-limit, connection, timeout, and provider status errors are mapped to safe HTTP responses without returning prompts, resume text, API keys, or raw model responses.

## Technology Stack

| Area | Technology | Role in CareerPilot AI |
|---|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn | API, dependency injection, request orchestration, and serving |
| Validation | Pydantic v2 | Request constraints, LLM output validation, and response contracts |
| AI / LLM | DeepSeek API via OpenAI Python SDK | Semantic JD extraction, resume matching, and learning-content generation |
| Database | PostgreSQL 18, psycopg 3 | Relational persistence and JSONB structured outputs |
| Data access | SQLAlchemy 2.x | Typed ORM models, sessions, constraints, and repository queries |
| Migrations | Alembic | Versioned PostgreSQL schema management |
| Frontend | React 19, TypeScript 5.9, Vite 7 | Responsive single-page analysis workspace |
| UI | Lucide React, custom CSS | Icons, result tabs, loading/error/empty states, and responsive layout |
| Testing | pytest, FastAPI TestClient, httpx | Schema, service, API, repository, workflow, and PostgreSQL integration tests |
| DevOps | Docker, Docker Compose, Nginx | Three-service local deployment and frontend reverse proxy |

There is currently no RAG, embedding/vector database, autonomous-agent loop, authentication, or resume file parser in the codebase.

## Project Structure

```text
ai-enterprise-assistant/
├── app/
│   ├── main.py                          # FastAPI app and HTTP error mapping
│   ├── schemas.py                       # Public Pydantic request/response models
│   ├── llm_service.py                   # DeepSeek client and JD analysis
│   ├── services/
│   │   ├── resume_matching_service.py   # Semantic matching + evidence checks
│   │   ├── learning_plan_service.py     # Plan generation + deterministic priority rules
│   │   └── analysis_workflow_service.py # Three-stage orchestration and persistence
│   ├── db/
│   │   ├── base.py                      # Declarative Base and naming convention
│   │   ├── session.py                   # Lazy Engine, Session factory, get_db
│   │   └── models/                      # Nine SQLAlchemy ORM models
│   └── repositories/                    # Candidate, resume, job, skill, analysis, and plan access
├── alembic/
│   ├── env.py                           # Metadata and Engine integration
│   └── versions/                        # Versioned PostgreSQL migrations
├── frontend/
│   ├── src/App.tsx                      # Form, workflow state, and result views
│   ├── src/api.ts                       # Real /analyze/workflow client
│   ├── src/types.ts                     # TypeScript API contracts
│   ├── vite.config.ts                   # Local FastAPI proxy
│   ├── Dockerfile                       # Node build + Nginx runtime
│   └── nginx.conf                       # SPA hosting and backend proxy
├── tests/
│   ├── integration/                     # Real PostgreSQL repository tests
│   └── test_*.py                        # Schema, service, API, ORM, and workflow tests
├── data/                                # JD evaluation fixtures and sample text
├── Dockerfile                           # Python 3.11 backend image
├── docker-compose.yml                   # Frontend + backend + PostgreSQL topology
├── .env.docker.example                  # Secret-free Docker environment template
├── alembic.ini
├── requirements.txt
└── requirements-dev.txt
```

## API Documentation

FastAPI exposes interactive OpenAPI documentation at `http://127.0.0.1:8000/docs` when the backend is running.

| Method | Endpoint | Request | Response |
|---|---|---|---|
| `GET` | `/health` | None | Service name and `status: "ok"` |
| `POST` | `/analyze/jd` | `job_description` (1–20,000 chars) | Structured job metadata plus required/preferred skills |
| `POST` | `/analyze/resume-match` | `job_description`, `resume_text` (1–30,000 chars) | Required/preferred skill matches, evidence, summary, and suggestions |
| `POST` | `/analyze/learning-plan` | `job_description`, `resume_text` | A prioritized learning plan; internally runs all three AI stages |
| `POST` | `/analyze/workflow` | JD, resume, and optional candidate metadata | Persisted three-stage result plus database record UUIDs |

### Full workflow request

```json
{
  "job_description": "Backend Engineer role requiring Python, FastAPI, SQL, and Docker...",
  "resume_text": "Built a FastAPI service in Python and designed PostgreSQL queries...",
  "candidate_display_name": "Demo Candidate",
  "candidate_email": "demo@example.com",
  "resume_title": "Backend Resume"
}
```

Optional workflow fields:

- `candidate_id`: reuse an existing candidate by UUID;
- `candidate_email`: reuse a uniquely matching candidate or create a new one;
- `candidate_display_name`: display name for a newly created candidate;
- `resume_title`: label for the new resume version.

The workflow response contains `candidate_id`, `resume_id`, `job_id`, `analysis_run_id`, `learning_plan_id`, related item IDs, and the complete `jd_analysis`, `resume_matching`, and `learning_plan` objects.

The three standalone analysis endpoints do not expose repository operations directly. Only `/analyze/workflow` persists the complete pipeline through `AnalysisWorkflowService`.

## Database Design

```mermaid
erDiagram
    CANDIDATES ||--o{ RESUMES : owns
    JOBS ||--o{ JOB_SKILLS : defines
    SKILLS ||--o{ JOB_SKILLS : classifies
    JOBS ||--o{ ANALYSIS_RUNS : analyzed_in
    RESUMES o|--o{ ANALYSIS_RUNS : used_by
    ANALYSIS_RUNS ||--o{ ANALYSIS_SKILL_MATCHES : produces
    JOB_SKILLS ||--o{ ANALYSIS_SKILL_MATCHES : matched_as
    ANALYSIS_RUNS ||--o| LEARNING_PLANS : produces
    LEARNING_PLANS ||--o{ LEARNING_PLAN_ITEMS : contains
    JOB_SKILLS ||--o{ LEARNING_PLAN_ITEMS : targets
```

The nine ORM models are:

- **Candidate** — optional display name/email and resume ownership.
- **Resume** — versioned content snapshot, SHA-256 hash, candidate-scoped version, and one-current-resume constraint.
- **Job** — source JD, hash, extracted metadata, and schema version.
- **Skill** — canonical display name plus unique `strip().casefold()` lookup key.
- **JobSkill** — required/preferred category, original name snapshot, and JD-relative position.
- **AnalysisRun** — run type/status/stage, model metadata, JSONB stage outputs, summaries, and safe failure metadata.
- **AnalysisSkillMatch** — per-run skill status and optional verified evidence.
- **LearningPlan** — one plan per analysis run, including the complete JSONB output.
- **LearningPlanItem** — per-skill priority, basis, task, deliverables, criteria, and estimated hours.

Repositories accept an existing SQLAlchemy `Session`, use SQLAlchemy 2.x `select()`/`flush()`, and leave transaction boundaries to the workflow service. Repository checks ensure that normal writes link skill-match and learning-plan items to skills from the analysis run's job. PostgreSQL independently enforces foreign keys and field-level check/unique constraints; the cross-job invariant is not encoded as a single database constraint if callers bypass the repositories.

Alembic imports the shared `Base.metadata`, registers all nine models, and reuses the application's cached Engine in online migration mode.

## Installation & Usage (Windows)

### 1. Clone the repository

```powershell
git clone https://github.com/Wonder021120/ai-enterprise-assistant.git
cd ai-enterprise-assistant
```

### 2. Create a Python 3.11 environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes the runtime dependencies plus pytest and httpx. Use `requirements.txt` instead for a runtime-only installation.

### 3. Configure environment variables

Create a local `.env` file in the repository root. It is ignored by Git.

```dotenv
DEEPSEEK_API_KEY=replace_with_your_key
DEEPSEEK_MODEL=deepseek-flash
DATABASE_URL=postgresql+psycopg://careerpilot_user:replace_with_your_password@127.0.0.1:5432/careerpilot_db
```

Do not place API keys or database credentials in source code, frontend files, or committed configuration.

### 4. Prepare PostgreSQL and apply migrations

Create the database/user referenced by `DATABASE_URL`, then run:

```powershell
python -m alembic upgrade head
python -c "from app.db.session import check_database_connection; print(check_database_connection())"
```

The connection layer creates the Engine lazily with `pool_pre_ping=True`; importing the module does not connect to PostgreSQL.

### 5. Start FastAPI

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- Health check: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

### 6. Start the frontend

Node.js 26 and pnpm 11 are recommended to match the Docker build environment.

```powershell
cd frontend
npm install --global pnpm@11.25.0
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/analyze` and `/health` to the FastAPI server at port 8000, so no development CORS change is required.

## Docker Deployment

The repository includes Docker configuration for a Python 3.11 backend, a Node.js 26 multi-stage frontend build served by Nginx, and an isolated PostgreSQL 18 container with a named volume.

```powershell
Copy-Item .env.docker.example .env.docker
# Edit .env.docker and replace the placeholder database password and DeepSeek key.

docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f backend frontend db
```

Open the production frontend at `http://127.0.0.1:8080`. The backend remains available at `http://127.0.0.1:8000`, while PostgreSQL is only reachable on the internal Compose network.

The backend waits for the database health check and runs `alembic upgrade head` before starting Uvicorn. Nginx proxies `/analyze/*` and `/health` to FastAPI.

Stop the stack without deleting the persistent database volume:

```powershell
docker compose --env-file .env.docker down
```

> **Verification status:** Compose configuration has been statically validated, but a full image build and container startup have not yet been completed in the current development environment because its Docker Engine was unavailable. Treat the deployment as configured but pending runtime verification.

## Testing

The pytest suite covers:

- Pydantic boundary, blank-input, literal, deduplication, and cross-field rules;
- DeepSeek client configuration, JSON Output parameters, finish reasons, and invalid output;
- deterministic skill reconciliation, evidence checks, and learning priority/order;
- API success, validation, stage-specific error mapping, and safe logging;
- ORM metadata, PostgreSQL DDL compilation, constraints, and Alembic configuration;
- repository CRUD/query behavior, transaction ownership, and cross-job consistency;
- complete workflow orchestration, persistence calls, rollback, and failure recording;
- optional real-PostgreSQL constraint, cascade, and transaction behavior.

Run the default suite:

```powershell
python -m pytest -q
```

Latest local verification on **2026-11-02**:

```text
338 passed, 10 skipped in 3.06s
```

The 10 skipped tests are the PostgreSQL integration suite. They intentionally require `TEST_DATABASE_URL` to target a database named exactly `careerpilot_test_db`; they never fall back to `DATABASE_URL`.

To run them safely, prepare and migrate that dedicated database, then set:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://test_user:replace_with_your_password@127.0.0.1:5432/careerpilot_test_db"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
python -m alembic upgrade head
python -m pytest tests/integration -q
```

The integration fixtures verify both the URL database name and `SELECT current_database()` before running, and they compare the database Alembic revision with the repository head.

Frontend checks:

```powershell
cd frontend
pnpm typecheck
pnpm build
```

All automated LLM tests use mocks and do not consume DeepSeek quota.

## Future Improvements

- Add repeatable LLM quality evaluation, regression datasets, and bad-case tracking for all three stages.
- Improve skill normalization with aliases and taxonomy-aware canonicalization while preserving explainability.
- Add secure PDF/DOCX resume parsing and section extraction instead of text-only input.
- Expose candidate analysis history through authenticated APIs and frontend views.
- Add authentication, authorization, privacy controls, retention policies, and encrypted secret management.
- Add CI pipelines for backend tests, frontend builds, migration checks, and container builds.
- Complete Docker runtime verification and define a production deployment target with TLS and observability.
- Improve performance and cost controls with request tracing, metrics, token accounting, and carefully bounded retries.
- Strengthen database-level cross-job invariants for skill matches and plan items without duplicating business data.

## Current Scope and Limitations

- The workflow is deterministic service orchestration; it does not implement an autonomous Agent loop.
- RAG, embeddings, pgvector, and knowledge retrieval were intentionally removed from the project scope.
- The frontend accepts pasted text and does not upload or parse resume files.
- Database persistence is available through `/analyze/workflow`; there is no history-management UI yet.
- The project does not currently include login, multi-user isolation, or production security hardening.
- Real LLM quality still depends on the configured DeepSeek model and should be evaluated beyond mocked tests.

## License

No license file is currently included. Add one before distributing or accepting external contributions.
