# ⚡ WattPilot AI — AI-Powered Smart Home Energy Optimizer

An **AI-powered smart home energy platform** that predicts per-appliance electricity
consumption, prices every action against your time-of-use tariff, and generates
personalized day-ahead optimization plans — then emails you a plain-language summary.

Built with **Microsoft Agent Framework** + **Azure OpenAI** for the AI agents,
**Prophet** ML models for per-appliance forecasting, **Open-Meteo / Nominatim** for
weather & geocoding, **FastAPI** for the backend API, and a **React (Vite)** dashboard.

---

## 📸 1. Application Screenshot

> **Placeholder** — add the application screenshot here.
>
> ```markdown
> ![WattPilot AI Dashboard](docs/screenshots/dashboard.png)
> ```

![Application Screenshot](docs/screenshots/dashboard.png)

---

## 🎯 2. Use Case

Household electricity bills keep climbing because power is consumed when it is
most expensive — during the **peak hours** of the day. Most families have no idea:

- which appliances draw the most power,
- how tomorrow's weather will change their usage,
- how much they could save simply by **shifting** usage to off-peak hours.

**WattPilot AI solves this** by treating your home like a small power grid:

1. It reads your appliance-level usage and the weather forecast for tomorrow.
2. Two AI agents simulate and optimize your schedule against your **time-of-use tariff**.
3. You get a clean, per-appliance plan (**raise AC set-point**, **run laundry off-peak**,
   **auto-sleep the PC**) with **kWh and ₹ savings** printed on every action.
4. The same plan is rewritten by an Email agent into a friendly report and
   delivered to your inbox.

> The end result: fewer kWh during peak, more savings every day, and zero effort
> required from the homeowner beyond pressing **"Build My Plan"**.

---

## 🧠 3. Project Overview

```
┌────────────────────────────┐         ┌──────────────────────────────────────────┐
│      React + Vite UI       │  proxy  │             FastAPI Backend              │
│  Home · Dashboard ·        │ ──────► │  ┌────────────────────────────────────┐  │
│  Forecast · Optimize       │  /api   │  │  Multi-Agent Orchestration          │  │
└────────────────────────────┘         │  │  ┌──────────────┐  ┌────────────┐  │  │
                                       │  │  │ Agent 1      │  │ Agent 2    │  │  │
                                       │  │  │ Usage        │► │ Energy     │  │  │
                                       │  │  │ Collector    │  │ Optimizer  │  │  │
                                       │  │  └──────┬───────┘  └─────┬──────┘  │  │
                                       │  │         │   ┌────────────┐│         │  │
                                       │  │         └──►│ Email      │◄┘         │  │
                                       │  │            │ Report     │            │  │
                                       │  │            └────────────┘            │  │
                                       │  │  Tools: weather · geocode · tariff    │  │
                                       │  │  Prophet forecast · savings calc      │  │
                                       │  └────────────────────────────────────┘  │
                                       └──────────────┬───────────────────────────┘
                                                      │
                              ┌───────────────────────┼───────────────────────────┐
                              │                       │                           │
                     ┌────────▼───────┐      ┌────────▼────────┐      ┌───────────▼────┐
                     │ Azure OpenAI   │      │  Prophet ML     │      │ Weather / Geo  │
                     │ (LLM agents)   │      │  (per-appliance)│      │ Open-Meteo ·   │
                     │                │      │                 │      │ Nominatim      │
                     └────────────────┘      └─────────────────┘      └────────────────┘
```

**Full architecture diagram:** [`Architecture_Diagrams/WattPilot AI - Logical Architecture Diagram.png`](Architecture_Diagrams/WattPilot%20AI%20-%20Logical%20Architecture%20Diagram.png)

---

## 🔄 4. Core Pipeline

A request to `POST /api/v1/recommendations` triggers the end-to-end flow:

| # | Step | Component | Where |
|---|------|-----------|-------|
| 1 | **Validate** the home config + tariff | Pydantic schemas | `Backend/Schemas/` |
| 2 | **Geocode** the city → lat/lon | Nominatim (OSM) | `Backend/Services/geocode_service.py` |
| 3 | **Agent 1 — Usage Collector**: gathers historical usage, next-day weather and the Prophet forecast | MAF + Azure OpenAI | `Backend/Agents/agent_1_energy_analysis.py` |
| 4 | **Validate** Agent 1's JSON through shared schemas | Pydantic (tolerant) | `Backend/Agents/Workflows/energy_optimization_workflow.py` |
| 5 | **Agent 2 — Energy Optimizer**: computes savings with the tariff tool and returns the plan | MAF + Azure OpenAI | `Backend/Agents/agent_2_energy_optimizer.py` |
| 6 | **Email Report Agent** rewrites the plan into a friendly email | MAF + SMTP | `Backend/Agents/email_agent.py` |
| 7 | Deliver via **SMTP** (best-effort — compose always works, send when configured) | `smtplib` | `Backend/Agents/email_agent.py` |

**Deterministic (non-LLM) endpoints** also exist for history & forecasting:
`GET /api/v1/energy/history` and `POST /api/v1/energy/forecast` run the prophet models
directly with no agent round-trip.

### 👷 Training the ML models (once, before first forecast)

The forecasting models are fit per appliance from the dataset. Train them in a few
minutes:

```bash
python Backend/Models/model_loader.py
```

Artifacts are written to `Backend/Artifacts/` (models as pickle, test-window
predictions as CSV, metrics summary as JSON, plus a `model_registry.json`).
The notebook version lives at `Backend/Notebook/ml_model_training.ipynb`.

---

## 📁 5. Directory Structure

```
.
├── main.py                          # FastAPI entry point (uvicorn main:app)
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project metadata (uv-managed)
├── uv.lock                          # Locked dependency versions (uv)
├── .env                             # Local secrets (git-ignored)
│
├── Architecture_Diagrams/
│   └── WattPilot AI - Logical Architecture Diagram.png
│
├── Backend/
│   ├── Agents/
│   │   ├── agent_factory.py         # Centralized MAF + Azure OpenAI wiring
│   │   ├── agent_1_energy_analysis.py   # "Usage Collector" agent
│   │   ├── agent_2_energy_optimizer.py  # "Energy Optimizer" agent
│   │   ├── email_agent.py           # Email Report agent + SMTP delivery
│   │   ├── Prompts/                 # System prompts (prompt store)
│   │   └── Workflows/energy_optimization_workflow.py  # Orchestration layer
│   ├── api/Routes/
│   │   ├── health.py                # GET  /health
│   │   ├── energy.py                # GET  /api/v1/energy/history · POST .../forecast
│   │   ├── recommendations.py       # POST /api/v1/recommendations
│   │   └── email_plan.py            # POST /api/v1/email/plan
│   ├── Config/settings.py           # Env vars, paths, WMO codes, logging, SMTP
│   ├── Dataset/                     # Appliance-usage CSV datasets
│   ├── Models/
│   │   ├── model_loader.py          # Trains + persists Prophet models
│   │   └── energy_predictor.py      # Inference against saved models
│   ├── Notebook/ml_model_training.ipynb  # Interactive training notebook
│   ├── Schemas/                     # Pydantic models (home, energy, forecast, email...)
│   ├── Services/                    # energy_service · geocode_service
│   ├── Tools/                       # weather · geocode · tariff · ML · savings · usage
│   └── Artifacts/                   # trained models / predictions / accuracy (generated)
│
└── Frontend/                        # React (Vite) single-page app
    ├── vite.config.js               # Dev server + /api & /health proxy → :8000
    ├── package.json
    ├── index.html
    ├── public/bolt.svg
    └── src/
        ├── main.jsx                 # React entry point
        ├── App.jsx                  # Router (/, /dashboard, /forecast, /optimize)
        ├── api/client.js            # fetch wrapper for the backend API
        ├── components/              # Navbar · Footer · Loader · ApplianceSelector
        ├── pages/                   # Home · Dashboard · Forecast · Optimize
        └── styles/index.css         # Dark-theme design system
```

---

## 🧰 6. Requirements

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | **3.14+** (see `.python-version`) | Backend runtime |
| **uv** | 0.9.x | Python package manager (virtualenv + deps) |
| **Node.js** | 20+ (tested on 25.x) | Frontend build/dev server |
| **npm** | 10+ | Frontend packages |

Everything else (numpy, pandas, prophet, fastapi, openai, agent-framework…) is
installed automatically from `requirements.txt`.

---

## ☁️ 7. Azure Resources & External Services

| Service | Type | Used For | Required? |
|---------|------|----------|-----------|
| **[Azure OpenAI Service](https://azure.microsoft.com/en-us/products/ai-services/openai-service)** | Cloud AI | LLM behind all three agents (Responses API) | ✅ Required (agent features) |
| **Azure OpenAI deployment** | Cloud AI | A deployed chat model (e.g. `gpt-4o`) in the same resource | ✅ Required (agent features) |
| **[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)** | Python SDK | Multi-agent orchestration + tool calling | ✅ Bundled via `requirements.txt` |
| **[Open-Meteo](https://open-meteo.com/)** | Free API | Day-ahead weather forecast (no key needed) | Optional (has fallback) |
| **[Nominatim — OpenStreetMap](https://nominatim.openstreetmap.org/)** | Free API | City → coordinates geocoding (no key needed) | Optional |
| **SMTP provider** (e.g. Gmail + App Password) | Email | Delivering the emailed plan | Optional (best-effort) |
| **Prophet + scikit-learn** | Local ML | Per-appliance forecasting models | Bundled via requirements |

> **Creating the Azure OpenAI deployment:**
> 1. In the Azure portal / AI Foundry, create an **Azure OpenAI** resource.
> 2. Create a **deployment** of a chat model (e.g. `gpt-4o`) and note the *deployment name*.
> 3. Grab the resource **endpoint** (https://`<your-resource>`openai.azure.com/) and an **API key**.
> 4. Fill them into `.env` (see section 10).

---

## 🚀 8. Create the Environment

> This project uses the **`uv` package manager** (not `pip`).
> Install it first — https://docs.astral.sh/uv/

### Windows (PowerShell)

```powershell
# 1. Create a virtual environment in the project folder (.venv/)
uv venv

# 2. Activate it
.venv\Scripts\Activate.ps1

# 3. Confirm the interpreter
python --version   # -> Python 3.14.x
```

### Linux / macOS

```bash
# 1. Create a virtual environment in the project folder (.venv/)
uv venv

# 2. Activate it
source .venv/bin/activate

# 3. Confirm the interpreter
python --version   # -> Python 3.14.x
```

---

## 📦 9. Install Dependencies

With the virtual environment active, install all required packages from
`requirements.txt` (uv resolves and locks everything — no pip):

```bash
uv add -r requirements.txt
```

> All command-line tools below (Python, uvicorn…) run inside this environment,
> so make sure it stays activated in every terminal you use.

---

## ⚙️ 10. Configure Environment Variables

Create a `.env` file at the project root. The repo ships a commented example —
start from the keys below. **Never commit real secrets.**

### Variable Reference

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `ENVIRONMENT` | no | `development` | `development` / `staging` / `production` (production fails fast on missing secrets) |
| `AZURE_OPENAI_ENDPOINT` | **yes*** | — | Azure OpenAI resource endpoint, e.g. `https://my-resource.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | **yes*** | — | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | yes* | — | Deployment name of your chat model |
| `AZURE_OPENAI_API_VERSION` | no | `2024-06-01` | Azure API version |
| `AZURE_OPENAI_CHAT_MODEL` | no | `AZURE_OPENAI_DEPLOYMENT` | Alias for the deployment name (used by agents) |
| `AZURE_OPENAI_CHAT_VERSION` | no | `AZURE_OPENAI_API_VERSION` | Alias for the API version |
| `WEATHER_USER_AGENT` | no | `AI-Powered.../1.0` | Identifies your app to Open-Meteo / Nominatim |
| `WEATHER_API_KEY` | no | — | Paid weather provider key (optional; free APIs work without it) |
| `SMTP_HOST` | no | — | SMTP server host, e.g. `smtp.gmail.com` |
| `SMTP_PORT` | no | `587` | SMTP submission port |
| `SMTP_USERNAME` | no | — | Mailbox login |
| `SMTP_PASSWORD` | no | — | Mailbox password / **app-password** |
| `SMTP_FROM` | no | `SMTP_USERNAME` | Sender address |
| `SMTP_TO_EMAIL` | no | — | Default report recipient |
| `SMTP_USE_STARTTLS` | no | `true` | Enable STARTTLS |
| `SMTP_TIMEOUT` | no | `15` | SMTP connect timeout (seconds) |
| `MODEL_PATH` | no | `Backend/Artifacts/Models` | Where trained models are loaded from |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` | Log verbosity |
| `LOG_FORMAT` | no | `%(asctime)s \| %(levelname)-8s \| %(name)s \| %(message)s` | Log line format |

\* Required only for the **AI agent** features (`/api/v1/recommendations`,
`/api/v1/email/plan`). Without them, history, forecasting and the whole UI still
run; agent calls fail gracefully with a clear error.

### Example `.env` template

```dotenv
# --- App ---
ENVIRONMENT=development

# --- Azure OpenAI (agents) ---
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-openai-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-06-01

# --- Weather (optional — free APIs work without a key) ---
WEATHER_USER_AGENT=WattPilot-AI/1.0 (contact@example.com)

# --- SMTP (optional — email reports; Gmail: use an App Password) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=xxxxxxxxxxxxxxxx        # Gmail App Password
SMTP_FROM=you@gmail.com
SMTP_TO_EMAIL=you@gmail.com
SMTP_USE_STARTTLS=true

# --- Logging ---
LOG_LEVEL=DEBUG
```

#### 📧 Generate Email Password/Token

Follow the link below to generate the email password or token:

**Generate Email Password/Token** → https://myaccount.google.com/apppasswords

> This is the **App Password** you paste into `SMTP_PASSWORD` for Gmail (you must
> have 2-Step Verification enabled on your Google account to create one). For
> other providers, use the equivalent SMTP authorization token / password.

---

## ▶️ 11. Run the Backend

```bash
# Simple: lives in the project's own interactive docs & serves on 127.0.0.1:8000
python main.py

# Or with hot reload during development
uvicorn main:app --reload
```

| URL | What it is |
|-----|-----------|
| http://127.0.0.1:8000/ | Service overview (routes + health) |
| http://127.0.0.1:8000/docs | Interactive Swagger API docs |
| http://127.0.0.1:8000/health | Liveness check |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/v1/energy/history?limit=N` | Historical appliance-level usage |
| `POST` | `/api/v1/energy/forecast` | Day-ahead per-appliance forecast (Prophet, no LLM) |
| `POST` | `/api/v1/recommendations` | Two-agent optimization plan (slow, ~2–3 min) |
| `POST` | `/api/v1/email/plan` | Format & email an optimization plan |

---

## 🖥️ 12. Frontend (React UI)

A modern, responsive single-page dashboard built with **React 18 + Vite**,
**recharts** (charts), **lucide-react** (icons) and **react-router-dom**.

### Directory Structure (Frontend)

```
Frontend/
├── vite.config.js        # Dev server on :5173, proxies /api & /health → :8000
├── package.json
├── index.html
├── public/bolt.svg       # Favicon
└── src/
    ├── main.jsx          # React entry (BrowserRouter)
    ├── App.jsx           # Routes: / · /dashboard · /forecast · /optimize
    ├── api/client.js     # fetchHealth · fetchHistory · postForecast
    │                     # postRecommendations · postEmailPlan
    ├── components/
    │   ├── Navbar.jsx            # Sticky nav (mobile hamburger)
    │   ├── Footer.jsx            # Site footer
    │   ├── Loader.jsx            # Spinner + message
    │   └── ApplianceSelector.jsx # Multiselect chips
    ├── pages/
    │   ├── Home.jsx       # Landing page (hero · features · steps · CTA)
    │   ├── Dashboard.jsx  # Usage stats + area/bar charts + event table
    │   ├── Forecast.jsx   # HomeProfile form → per-appliance forecast
    │   └── Optimize.jsx   # Tariff form → AI plan + action cards + email modal
    └── styles/index.css    # Dark-theme design system
```

### Run the Frontend

```bash
cd Frontend

# 1. Install dependencies
npm install

# 2. Start the dev server (proxies /api and /health to the backend on :8000)
npm run dev
```

Open **http://localhost:5173** — make sure the backend is running on
**127.0.0.1:8000** so the proxy works.

### Production build

```bash
npm run build     # outputs an optimized bundle to Frontend/dist
npm run preview   # locally preview the production build
```

---

## ✨ 13. Features

- 🤖 **Multi-agent AI (Microsoft Agent Framework + Azure OpenAI)**
  - Agent 1 *Energy Usage Collector* — pulls history, weather & ML forecasts.
  - Agent 2 *Energy Optimizer* — designs the savings plan per appliance.
  - Agent 3 *Email Report* — rewrites the plan into a friendly, formatted email.
- 📈 **Day-ahead, per-appliance forecasting** — Prophet models + weather + household size + weekend flag, with 95% prediction intervals.
- 🌤️ **Weather & location aware** — Open-Meteo forecast, Nominatim geocoding, WMO condition mapping, best-effort fallbacks.
- 💰 **Time-of-use tariff optimization** — peak/off-peak pricing, per-action **kWh + ₹ savings** in INR.
- 📧 **Email reports** — SMTP delivery is best-effort; the composed email (`to/subject/body`) is always returned, so the UI can render a preview even without mail configured.
- 📊 **Interactive React dashboard** — stat cards, historical charts, forecast table, action cards and an email preview modal.
- 🧱 **Tolerant-by-design validation** — Pydantic schemas floor-check agent output without ever killing the pipeline; malformed dataset rows are skipped, not fatal.
- 🧪 **Interactive API docs** — auto-generated Swagger UI at `/docs`.
- 🔐 **Secret-safe configuration** — zero hardcoded secrets; env-driven with strict production fail-fast.

---

## 🧾 14. License

Distributed under the terms of the project's [LICENSE](LICENSE).