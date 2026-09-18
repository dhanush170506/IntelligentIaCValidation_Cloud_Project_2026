# Demo Guide — IaC Assurance Console

A presentation-ready walkthrough of the **Telemetry-Aware Multi-Agent IaC Assurance
System** frontend. Everything shown is a real run: real upload → real FastAPI backend →
real ML assurance engine → real MongoDB record → real report in the browser.

---

## The 30-second pitch (say this first)

> "This is the operator console for our multi-agent IaC assurance research system. An
> engineer uploads a Terraform or CloudFormation file. The FastAPI backend stores the
> upload, forwards the content to the ML assurance engine, which runs the full
> multi-agent pipeline — parsing into a unified resource graph, static security
> validation, six validation agents, telemetry-aware drift detection, evidence-grounded
> consensus, blast-radius analysis, and gated remediation. The result is persisted in
> MongoDB and rendered here as an evidence-backed report. The console never invents
> data — if the pipeline didn't return something, the UI says so."

---

## Pre-flight checklist (do this 10 minutes before the demo)

Run all services from the project root (the folder containing `src/` and `venv/`),
using the **project venv interpreter**. Git Bash commands shown; PowerShell/CMD
equivalents noted inline.

```bash
# 1. MongoDB (Windows service — verify it is RUNNING)
sc query MongoDB

# 2. One-time: static-security scanner (checkov) in the project venv
venv/Scripts/python.exe -m pip install checkov

# 3. ML assurance engine on :9000  (Git Bash)
PYTHONUTF8=1 \
CHECKOV_EXECUTABLE="$(pwd)/venv/Scripts/checkov-venv.cmd" \
venv/Scripts/python.exe -m uvicorn src.ml_model.api:app --host 0.0.0.0 --port 9000
#    PowerShell:
#    $env:PYTHONUTF8="1"; $env:CHECKOV_EXECUTABLE="$pwd\venv\Scripts\checkov-venv.cmd"; \
#    .\venv\Scripts\python.exe -m uvicorn src.ml_model.api:app --host 0.0.0.0 --port 9000

# 4. Backend on :8000 — AI_ENGINE_MOCK=false is what makes it call the real ML engine
AI_ENGINE_MOCK=false AI_ENGINE_TIMEOUT=300 \
venv/Scripts/python.exe -m uvicorn src.backend.main:app --port 8000
#    PowerShell:
#    $env:AI_ENGINE_MOCK="false"; $env:AI_ENGINE_TIMEOUT="300"; \
#    .\venv\Scripts\python.exe -m uvicorn src.backend.main:app --port 8000

# 5. Frontend
cd frontend
npm install        # first time only
npm run dev        # http://localhost:5173
```

Why each flag exists (all verified on this machine):

- **`AI_ENGINE_MOCK=false`** — the backend defaults to a labelled dummy response
  (`"source": "mock"`) instead of calling the ML engine.
- **`AI_ENGINE_TIMEOUT=300`** — the real pipeline (checkov scan included) takes a few
  seconds; the default 30s timeout is fine, the larger value removes demo-day risk.
- **`CHECKOV_EXECUTABLE`** — on Windows the pip `checkov.cmd` shim can resolve to the
  system Python (which lacks checkov). The project ships `venv/Scripts/checkov-venv.cmd`,
  an explicit launcher that guarantees the venv interpreter runs checkov.
- **`PYTHONUTF8=1`** — checkov on Windows otherwise decodes IaC files as cp1252 and
  crashes on UTF-8 files containing non-ASCII characters.
- The ML engine now wires **Checkov** as its Module 3 static validator (the same wiring
  the project's own integration test uses), which is what produces real security
  findings for the Security Agent.

Verify all three are healthy (paste in a browser):

| URL | Expected |
| --- | --- |
| `http://localhost:9000/health` | `{"status":"ok","service":"ml-assurance"}` |
| `http://localhost:8000/health` | `{"success":true,...}` |
| `http://localhost:8000/health/database` | `"message":"MongoDB connection successful"` |
| `http://localhost:5173` | Login page |

**Demo files are in `frontend/demo-assets/`:**

| File | What it shows |
| --- | --- |
| `risky-manufacturing.tf` | Terraform with a public S3 policy, open SSH, wildcard IAM → **Security Score 0**, real checkov findings |
| `clean-manufacturing.tf` | Conservative Terraform → **Security Score 100** (contrast the Security tab) |
| `risky-sensor-stack.yaml` | CloudFormation (YAML) with a public bucket + open RDP → proves multi-format support |

Sign in on the login page first (any email + password — see "Authentication" below for
how to present that honestly).

---

## The demo script (10–12 minutes)

### Act 1 — Dashboard (1 min)
Open `http://localhost:5173`. Point out:
- **All numbers are live from `GET /dashboard`** — totals, pass/fail/review counts,
  average security and drift scores. Nothing is hardcoded in the frontend.
- **System status card**: Backend API and MongoDB are probed through real health
  endpoints (`/health`, `/health/database`). The ML engine row honestly says it has no
  browser health check — it is invoked **server-side** by the backend, which is the
  intended architecture (Frontend → Backend → ML).
- Recent validations table with View Report links.

### Act 2 — The risky upload (3 min)
1. Go to **New Validation**. Drag `demo-assets/risky-manufacturing.tf` into the drop
   zone. The card shows filename, size, and detected format (`terraform`).
2. Before clicking, say: *"The moment I click Validate, the browser sends the file as
   multipart/form-data to the backend. The backend stores the upload in MongoDB, then
   calls the ML engine's `/validate` with the content. There is no simulated
   validation in this UI — the progress bar you saw is the real upload; after that the
   pipeline runs server-side."*
3. Click **Validate**. The report opens at `/validation/<report-id>`.
4. **Refresh the page now** and say: *"The report is fetched back from the backend by
   its ID — the browser doesn't carry hidden state. This is a stored MongoDB record."*

### Act 3 — Walk the report (4 min)
- **Header**: filename, format, timestamp, validation ID, overall verdict (**FAIL** —
  the pipeline found the public bucket policy, open SSH and wildcard IAM).
- **Score cards**: security 0/100 (the checkov-backed security agent flagged the
  misconfigurations), drift 0 (no runtime drift observed — telemetry found no deployed
  counterpart), confidence ~87%, deployment readiness 0 (a public bucket blocks
  deployment).
- **Overview → Findings table**: real findings with rule IDs (CKV_AWS_*), resources,
  and per-finding confidence.
- **Security tab**: findings grouped by severity (Critical/High/...).
- **Drift tab**: *"Telemetry-aware drift — each resource has a desired state from the
  IaC and, when available, an observed runtime state. This file was never deployed, so
  the agent explicitly reports insufficient runtime evidence instead of guessing."*
- **Agents tab**: six agents (Syntax, Security, Deployment, Drift, Cost, Evidence),
  each with status + confidence + its own findings.
- **Evidence tab**: the evidence registry that findings and consensus reference.
- **Blast Radius tab**: dependency impact per resource with direct/transitive
  dependents from the UIR graph.
- **Remediation tab**: dry-run, gate-checked proposals — *"The system is assurance-
  only; it never modifies infrastructure. Note the BLOCKED/APPROVED decisions and
  blast-radius-aware rankings."*
- **Recommendations tab**: grouped by Security / Reliability / Drift / Cost /
  Deployment, each with confidence and evidence-grounding flags.

### Act 4 — History & the clean contrast (2 min)
1. Open **History**: every stored run with search, status and format filters. *"This
   is the `validation_reports` MongoDB collection."*
2. Validate `demo-assets/clean-manufacturing.tf`. Open the **Security** tab and
   compare: Security Score is **100** here vs **0** for the risky file, and none of
   the dangerous patterns appear — no public bucket policy, no open SSH, no wildcard
   IAM. What remains are hygiene suggestions (encryption, versioning, logging) at
   INFO/MEDIUM level. The overall verdict is computed by the recommendation module's
   penalty model, which stays deliberately conservative while runtime evidence is
   missing (each unevidenced resource feeds a reliability recommendation). Say:
   *"Same pipeline, two very different risk profiles — the verdict integrates
   security, reliability, drift evidence and deployment readiness, not security
   alone."*

### Act 5 — CloudFormation (1 min)
Validate `demo-assets/risky-sensor-stack.yaml`. The console detects the format, the
CloudFormation parser runs, and the report shows the public bucket + open RDP
findings. *"Same assurance pipeline, second IaC dialect."*

---

## Architecture slide (what to draw/say)

```
Browser (React 18 + Vite + Tailwind)
   │  POST /validate  (multipart/form-data)
   ▼
FastAPI backend :8000 ── stores upload ──► MongoDB (uploads, validation_reports)
   │  POST :9000/validate  {upload_id, filename, file_type, content}
   ▼
ML assurance engine (FastAPI :9000)
   └─ AssuranceOrchestrator:
      parse → UIR graph → static validation → 6 validation agents
      → LLM integration → runtime telemetry (drift) → consensus
      → blast radius → gated remediation → recommendations → evaluation
   ▼
Result stored in MongoDB  →  GET /reports/{id}, /history, /dashboard
   ▼
Report rendered in the browser (fetchable by ID, survives refresh)
```

Frontend talking points:
- Centralized API layer (`services/api.js`) with timeout + a typed error taxonomy
  (network / timeout / http / parse / invalid-response) — every screen has loading,
  empty and error states.
- `reportMapper.js` maps the real pipeline payload defensively — missing optional
  fields render as "not available", never as invented data.
- Status badges use the backend's own PASS / FAIL / REVIEW_REQUIRED / ERROR values.

## Mock mode — a point to make *proactively*

The backend ships with a deliberate research switch, `AI_ENGINE_MOCK` (in
`src/backend/services/ai_service.py`), defaulting to `true`, which makes the backend
return a tiny labelled dummy (`"source": "mock"`) instead of calling the ML engine.
This demo runs with **`AI_ENGINE_MOCK=false`** so every report comes from the real
pipeline. If a report ever looks suspiciously tiny (2 generic recommendations,
security 85, confidence 0.91), it's the mock payload — restart the backend with the
env var set to `false`. The frontend also surfaces `source: mock` and `ERROR` results
honestly rather than hiding them.

## Authentication — how to answer "is that real auth?"

Be direct: *"The backend API doesn't expose authentication endpoints yet — I verified
that against its OpenAPI spec. The login page is a clearly-labelled local stand-in so
the console UX is complete; it stores no passwords and the data APIs are open. The
auth seam is isolated in `services/authService.js`, so when the backend ships JWT
endpoints, I wire them in one place."* Examiners reward honesty over fake security.

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Report has 2 generic recommendations, security 85, confidence 91% | Backend running with default `AI_ENGINE_MOCK=true` | Restart backend with `AI_ENGINE_MOCK=false` |
| Security tab always empty; warning mentions "Checkov executable not found" | ML engine started without `CHECKOV_EXECUTABLE` | Restart ML engine with `CHECKOV_EXECUTABLE="...checkov-venv.cmd"` |
| Warning mentions `UnicodeDecodeError` / cp1252 | Non-ASCII characters in the IaC file with a cp1252 locale | Restart ML engine with `PYTHONUTF8=1` (already in the commands above) |
| "Backend service is unavailable" toast/banner | Backend not running / wrong port | Start uvicorn on :8000; check `VITE_API_BASE_URL` in `frontend/.env` |
| Validation spins then times out | ML engine not running on :9000 | Start the ML uvicorn; backend returns a structured ERROR result otherwise |
| Login loops / 404 on refresh of `/validation/...` | Vite dev server not on 5173 (CORS whitelist) | Keep `npm run dev` default port 5173 |
| "Unsupported IaC file format" | File extension outside `.tf/.yaml/.yml/.json` | Use one of the demo files |
| Dashboard shows "No validation reports yet." | Fresh MongoDB | That's the honest empty state — run the risky file first |

---

## One-line answers to likely questions

- **"Where do the scores come from?"** — Each from the pipeline: security from the
  static-validation agent aggregate, drift from the telemetry module, confidence from
  consensus across agents, readiness from the recommendation module's penalty model.
  The UI renders them verbatim.
- **"Can it change my infrastructure?"** — No. Remediation is dry-run and gate-checked;
  the console has no apply action by design.
- **"What if the ML field is missing?"** — The tab shows an explicit "not available"
  empty state; the mapper never fabricates data.
- **"Why is drift 0 when nothing is deployed?"** — The drift agent distinguishes
  "no drift" from "no runtime evidence" and reports `DRIFT_INSUFFICIENT_EVIDENCE`
  findings at INFO severity — that's evidence-grounding, not a bug.
