# Revive Tool — Rivive (v4.1)

Full Hospital Management System covering registration, OPD, IPD, pharmacy, lab,
radiology, billing, insurance, HR, payroll, reports and settings, built with
Flask (application-factory pattern), Flask-SQLAlchemy, Flask-Login and
PostgreSQL.

## User guide

A non-technical walkthrough — access links, login, hosting status, and a
module-by-module reference — lives at [`docs/Revive-User-Guide.docx`](docs/Revive-User-Guide.docx).

## Local development

```powershell
git clone https://github.com/taariqhamdaan/Revive-Tool.git
cd Revive-Tool

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env      # then edit SECRET_KEY, ENCRYPTION_KEY, SEED_ADMIN_PASSWORD

$env:FLASK_APP = "wsgi.py"
flask db upgrade                 # or, for a first run: python -c "from app import create_app; from app.extensions import db; app=create_app(); app.app_context().push(); db.create_all()"
flask seed                       # creates the SuperAdmin login
python wsgi.py
```

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | Yes | Session signing |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ENCRYPTION_KEY` | Yes | Fernet key for encrypting sensitive fields |
| `MAIL_SUPPRESS_SEND` | No | Keep `1` until SMTP is configured |
| `SEED_ADMIN_USERNAME` / `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | Once, to seed | Used only by `flask seed` |

## Deployment

Deployed to both **Railway** (`web` service, GitHub-connected, auto-deploys on
push to `main`) and **Vercel** (serverless, via `api/index.py` + `vercel.json`).
Both point at the same Railway-hosted Postgres — Railway over its private
network, Vercel over the public TCP proxy — so there is one shared database.

Vercel's function filesystem is read-only outside `/tmp`; uploads, exports and
file logging fall back to `/tmp` there automatically (see `config.py` and
`app/__init__.py`).
