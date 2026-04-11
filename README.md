# Clinic NL2SQL — AI-Powered Natural Language to SQL

A production-ready **Natural Language to SQL** system for a clinic management database, built with **Vanna 2.0** and **FastAPI**.

Ask plain-English questions and get SQL results, summaries, and Plotly charts — no SQL knowledge required.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend   | Python 3.10+, FastAPI |
| AI Agent  | Vanna 2.0 (`Agent` + `DemoAgentMemory`) |
| LLM       | Google Gemini 2.5 Flash (default) — or Groq / Ollama |
| Database  | SQLite (`clinic.db`) |
| Charts    | Plotly |

---

## Project Structure

```
clinic_nl2sql/
├── setup_database.py   # Creates schema + inserts 200 patients, 500 appts…
├── vanna_setup.py      # Vanna 2.0 Agent initialisation
├── seed_memory.py      # Seeds agent memory with 15 known-good Q→SQL pairs
├── main.py             # FastAPI application
├── requirements.txt    # All dependencies
├── .env.example        # Environment variable template
├── README.md           # This file
├── RESULTS.md          # 20-question test results
└── clinic.db           # Generated SQLite database
```

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/codicecustode/clinic_nl_sql
cd clinic_nl_sql
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env and add your API key
```

**Option A — Google Gemini (default, free via AI Studio)**
```
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-key-here     # https://aistudio.google.com/apikey
```

**Option B — Groq (free tier)**
```
LLM_PROVIDER=groq
GROQ_API_KEY=your-key-here       # https://console.groq.com
```

**Option C — Ollama (fully local, no key needed)**
```
LLM_PROVIDER=ollama
# Run: ollama pull llama3
```

### 5. Create the database

```bash
python setup_database.py
```

Output:
```
✅ Database 'clinic.db' created successfully.
   Created 200 patients, 15 doctors, 500 appointments, 243 treatments, 300 invoices.
```

### 6. Seed agent memory

```bash
python seed_memory.py
```

This loads 15 verified Q→SQL pairs into the agent's in-memory store so it has good examples to reference.

### 7. Start the API server

```bash
uvicorn main:app --port 8000
```

Or with auto-reload during development:
```bash
uvicorn main:app --port 8000 --reload
```

### One-liner

```bash
pip install -r requirements.txt && python setup_database.py \
  && python seed_memory.py && uvicorn main:app --port 8000
```

---

## API Reference

### `POST /chat`

Ask a natural-language question.

**Request:**
```json
{
  "question": "Show me the top 5 patients by total spending"
}
```

**Response:**
```json
{
  "message": "Found 5 rows with columns: first_name, last_name, total_spent.",
  "sql_query": "SELECT p.first_name, p.last_name, SUM(i.total_amount) AS total_spent ...",
  "columns": ["first_name", "last_name", "total_spent"],
  "rows": [
    ["John", "Smith", 4823.50],
    ["Jane", "Doe",   3912.00]
  ],
  "row_count": 5,
  "chart": { "data": [...], "layout": {...} },
  "chart_type": "bar",
  "cached": false
}
```

**cURL example:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How many patients do we have?"}'
```

---

### `GET /health`

Liveness and readiness check.

**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 15
}
```

---

## Architecture Overview

```
User (HTTP)
    │
    ▼
FastAPI  (/chat)
    │  Input validation (Pydantic, length check)
    │  Rate limiting    (30 req/min per IP)
    │  Cache check      (5-minute TTL)
    │
    ▼
Vanna 2.0 Agent
    │  LLM Service (Gemini / Groq / Ollama)
    │  DemoAgentMemory  (few-shot examples)
    │  SearchSavedCorrectToolUsesTool
    │  RunSqlTool → SqliteRunner
    │  VisualizeDataTool
    │
    ▼
SQL Validation (SELECT-only guard)
    │
    ▼
SQLite Execution (clinic.db)
    │
    ▼
Plotly Chart Generation (optional)
    │
    ▼
JSON Response → User
```

---

## Security

- **SELECT-only enforcement** — any INSERT/UPDATE/DELETE/DROP/ALTER is rejected before execution.
- **Dangerous keyword guard** — EXEC, xp_, sp_, GRANT, REVOKE, SHUTDOWN are blocked.
- **System table guard** — sqlite_master and similar tables are blocked.
- **No hardcoded secrets** — all API keys are loaded from environment variables / `.env`.
- **Rate limiting** — 30 requests per 60 seconds per IP address.

---

## Bonus Features Implemented

| Feature | Status |
|---------|--------|
| Plotly chart generation | ✅ |
| Input validation (Pydantic, length) | ✅ |
| Query result caching (5-min TTL) | ✅ |
| Rate limiting (30 req/min) | ✅ |
| Structured logging | ✅ |

---

## LLM Provider Notes

This project defaults to **Google Gemini 2.5 Flash** because it is free via AI Studio and has strong SQL-generation capabilities. To switch providers, set `LLM_PROVIDER` in your `.env` file — no code changes required.

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| `ModuleNotFoundError: vanna` | Run `pip install -r requirements.txt` |
| `GOOGLE_API_KEY not set` | Add key to `.env` and run `source .env` or restart shell |
| `clinic.db not found` | Run `python setup_database.py` first |
| Port 8000 already in use | Use `uvicorn main:app --port 8001` |
| Ollama connection refused | Make sure the Ollama app is running: `ollama serve` |
