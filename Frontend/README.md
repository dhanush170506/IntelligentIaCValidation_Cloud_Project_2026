# IaC Assurance Console — Frontend

React front-end for the **Telemetry-Aware Multi-Agent Infrastructure-as-Code Assurance System
for Smart Manufacturing Cloud Environments**.

It is a real client for the real services: uploads go to the FastAPI backend, which forwards
the file to the ML assurance engine (`POST :9000/validate`), persists the report in MongoDB
and returns the actual pipeline result. The frontend contains **no simulated validation**,
no fake statistics and no fabricated history.

## Tech stack

- **React 18** + **Vite 5** (ES modules, fast HMR)
- **React Router 6** — routing
- **Tailwind CSS 3** — dark-first technical dashboard styling
- **lucide-react** — icons
- `fetch` / `XMLHttpRequest` — API layer (no extra HTTP dependency)

## Getting started

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

> The dev server runs on port **5173** because that origin is whitelisted by the backend's
> CORS configuration.

### Production build

```bash
npm run build      # outputs to dist/
npm run preview    # serve the production build locally
```

## Environment configuration

Copy `.env.example` to `.env` and adjust if needed (no secrets belong here):

| Variable              | Default                 | Purpose                                            |
| --------------------- | ----------------------- | -------------------------------------------------- |
| `VITE_API_BASE_URL`   | `http://localhost:8000` | FastAPI backend (uploads, reports, history, stats) |

There is deliberately **no ML engine variable**: the browser never talks to the ML engine.
The architecture is Frontend → Backend → ML, and the ML API exposes no CORS headers, so
the dashboard's system-status tile reports the engine as an indirect, server-side component
instead of guessing its state from the browser.

## API integration (verified contract)

| Endpoint (backend :8000)        | Used by                        | Notes                                                        |
| ------------------------------- | ------------------------------ | ------------------------------------------------------------ |
| `POST /validate` (multipart)    | New Validation page            | Full pipeline run; returns `report_id` + complete `validation` payload |
| `GET /reports/{report_id}`      | Validation Report page         | Stored report: summary, findings, recommendations             |
| `GET /history`                  | History page                   | `{ success, count, reports[] }`                               |
| `GET /dashboard`                | Dashboard                      | Aggregate stats + `recent_validations[]`                      |
| `GET /health`                   | System status tile             | Backend liveness                                              |
| `GET /health/database`          | System status tile             | MongoDB connectivity                                          |

`POST /validate` request: `multipart/form-data` with a single `file` field (`.tf`, `.yaml`,
`.yml`, `.json`). The response shape is guarded; malformed payloads raise a typed
`ApiError('invalid-response')` instead of rendering invented data.

### Report payload awareness

The **stored** report (`GET /reports/{id}`) intentionally contains only the summary,
findings and recommendations. The **full** agent/evidence/drift/blast-radius/remediation
payload exists in the synchronous `POST /validate` response and is passed to the report page
via router state immediately after an upload. The report page therefore:

- renders extended tabs (Agents, Evidence, Drift, Blast Radius, Remediation) **only** when
  that data is present in the current payload;
- shows a notice on stored reports explaining where full detail comes from;
- shows explicit empty states ("No findings available.", "Runtime drift information is not
  available for this validation.", …) rather than placeholders that look like data.

## Project structure

```
frontend/
├── index.html
├── vite.config.js            # dev server pinned to :5173 (CORS origin)
├── tailwind.config.js        # night/signal palette
├── .env.example
└── src/
    ├── App.jsx               # route table + protected routes
    ├── main.jsx              # React root, router, auth provider
    ├── styles.css            # Tailwind layers + component classes
    ├── layouts/
    │   ├── AppLayout.jsx     # sidebar + navbar shell (auth routes)
    │   └── AuthLayout.jsx    # centered shell (login/register)
    ├── pages/                # one component per route
    │   ├── DashboardPage.jsx
    │   ├── ValidatePage.jsx
    │   ├── ValidationReportPage.jsx
    │   ├── HistoryPage.jsx
    │   ├── ProjectsPage.jsx
    │   ├── ProfilePage.jsx
    │   ├── LoginPage.jsx
    │   ├── RegisterPage.jsx
    │   └── NotFoundPage.jsx
    ├── components/           # reusable UI
    │   ├── Navbar.jsx / Sidebar.jsx / PageHeader.jsx
    │   ├── StatCard.jsx / ScoreCard.jsx / StatusBadge.jsx / SeverityBadge.jsx
    │   ├── FileUploader.jsx / ValidationTable.jsx / FindingsTable.jsx / FindingCard.jsx
    │   ├── AgentCard.jsx / EvidencePanel.jsx / DriftPanel.jsx
    │   ├── BlastRadiusPanel.jsx / RemediationPanel.jsx / RecommendationPanel.jsx
    │   ├── SystemStatus.jsx / Modal.jsx
    │   └── LoadingState.jsx / EmptyState.jsx / ErrorState.jsx
    │   └── report/OverviewSidebar.jsx
    ├── services/             # centralized API layer (no fetches in components)
    │   ├── api.js            # base URL, timeout, error taxonomy
    │   ├── validationService.js
    │   ├── dashboardService.js
    │   ├── historyService.js
    │   ├── systemStatusService.js
    │   └── authService.js    # isolated auth seam (see below)
    ├── hooks/
    │   ├── useAuth.jsx       # session context
    │   ├── useAsync.js       # generic fetch hook
    │   └── useTheme.js
    └── utils/
        ├── apiFormatting…    # (format.js, formatFileType.js, uploadUtils.js)
        ├── severity.js       # severity/status/agent/category mappings
        └── reportMapper.js   # defensive payload → view-model mapping
```

## Authentication status (important)

The backend currently exposes **no authentication API** (checked via `/openapi.json`).
`services/authService.js` is the single, clearly-isolated seam for future real auth:

- today it maintains a **local, non-secure demo session** in browser storage,
  explicitly labelled as such in the UI (banner + login/register/profile notes);
- **no passwords are ever stored** — credentials are validated client-side for the
  demo UX and then discarded; there are no fake tokens and nothing is protected
  server-side;
- to connect real auth later: implement `login`/`register` against the real API and
  attach the issued token in `services/api.js`.

## Design notes

- Dark, technical aesthetic: deep navy surfaces, thin borders, mono numerals, subtle
  signal-blue accent; no decorative gradients or excessive rounding.
- Accessible: labelled inputs, `aria-invalid`/`role="alert"` on errors, visible
  `:focus-visible` rings, keyboard-operable uploader and modals, status changes announced
  via `aria-live`.
- Responsive: sidebar collapses to an overlay drawer under `lg`; tables scroll
  horizontally; grids reflow down to tablet widths.

## Backend / ML safety

This frontend never modifies `src/backend` or `src/ml_model`. It treats their HTTP
contracts as read-only and adapts to optional fields defensively.
