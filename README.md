# Scholarship agent (MVP)

FastAPI service that can scrape Buddy4study-style listing pages (configurable URL), store scholarships, accept user profiles and resumes (PDF/DOCX), and return ranked matches. A small Vite + React UI is included for manual testing.

## Prerequisites

- Python 3.11+
- Node.js 20+ (for the frontend)

## Backend setup

Database is **PostgreSQL** (e.g. **Neon**). Copy `example.env` to `.env` and set:

- `DATABASE_URL` — `postgresql://...` from Neon (often includes `?sslmode=require`)

Resume uploads are parsed from a **temporary file** only; nothing is stored under `./data/`.

Dependencies use **`psycopg`** (binary wheels) — no Rust toolchain, which avoids build failures on platforms like Render.

```powershell
cd "c:\Users\91813\Desktop\omnimise ai agent"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
alembic upgrade head
```

On Render, pin **Python 3.11** via `runtime.txt` if the default image uses a version without wheels for some packages.

Optional environment variables (see `app/config.py`):

- `ADMIN_TOKEN` — default `dev-admin-change-me` (change for any shared environment)
- `CORS_DEV` — default `true` (enables CORS for the Vite dev server)
- `BUDDY4STUDY_LIST_URL` — starting URL for discovery (default `https://www.buddy4study.com/scholarships`)
- `SCRAPE_INTERVAL_MINUTES` — scheduler interval (minimum 5 minutes enforced in code)
- `SCRAPE_REQUEST_DELAY_SECONDS` — delay between HTTP requests (default `1.0`)

Run the API:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `GET http://127.0.0.1:8000/health`

### Load sample scholarships (no scraping)

```powershell
curl -X POST "http://127.0.0.1:8000/admin/scholarships/import" `
  -H "Content-Type: application/json" `
  -H "X-Admin-Token: dev-admin-change-me" `
  -d "@data/seed_scholarships.json"
```

### Trigger a scrape

```powershell
curl -X POST "http://127.0.0.1:8000/admin/scrape/run" -H "X-Admin-Token: dev-admin-change-me"
```

## Frontend (test UI)

```powershell
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` if the API is not at `http://127.0.0.1:8000` (create `frontend/.env`).

Open the URL printed by Vite (typically `http://localhost:5173`).

## API summary

| Method | Path | Notes |
|--------|------|--------|
| POST | `/users` | JSON body `{"profile": { ... }}` |
| POST | `/users/{id}/resume` | multipart file field `file` (PDF or DOCX) |
| GET | `/users/{id}/matches` | query `limit` (default 50) |
| GET | `/scholarships` | query `skip`, `limit`, optional `tag` |
| POST | `/admin/scrape/run` | header `X-Admin-Token` |
| POST | `/admin/scholarships/import` | JSON body `{ "items": [ ... ] }` |

## Legal note

Scraping third-party sites may violate their terms of service. Use official APIs or data you are permitted to use in production. This project includes an import endpoint as a safer alternative for development.
