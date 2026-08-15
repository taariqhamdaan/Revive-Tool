# Revive Tool — Rivive SCH Laboratory Module (v4.2)

Flask-based Laboratory Information System covering the full lab workflow:
registration → sample collection → result entry → approval → report, plus a
test-master settings screen with reference ranges and automatic H/L/HH/LL flagging.

## Stack

| Layer | Choice |
|---|---|
| Framework | Flask 3 (application-factory pattern) |
| ORM | Flask-SQLAlchemy 3.1 / SQLAlchemy 2.0 |
| Auth | Flask-Login + Werkzeug password hashing |
| Forms/CSRF | Flask-WTF |
| Migrations | Flask-Migrate (Alembic) |
| DB | SQLite locally, PostgreSQL on Railway |
| Server | Gunicorn |

## Project layout

```
app/
├── __init__.py              application factory, config, blueprint registration
├── extensions.py            db / login_manager / csrf / migrate singletons
├── seed.py                  idempotent starter data (branch, roles, admin, tests)
├── blueprints/
│   ├── auth/routes.py       login / logout
│   └── lab/routes.py        6-stage lab workflow + settings CRUD
├── models/
│   ├── foundation.py        Branch, Role, User, Department, Patient, Bill, Doctor
│   └── lab.py               LabCategory, TestMaster, LabOrder, LabOrderItem,
│                            SampleCollection, LabResult, LabApproval
└── templates/
    ├── auth/login.html
    └── lab/*.html
wsgi.py                      Gunicorn entrypoint (`wsgi:app`)
```

## Local development

Requires **Python 3.12** and **Git**.

```powershell
git clone https://github.com/DS-Hariprakash/Revive-Tool.git
cd Revive-Tool

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

Copy-Item .env.example .env      # then edit SECRET_KEY and SEED_ADMIN_PASSWORD

$env:FLASK_APP = "wsgi.py"
flask seed                       # creates tables + starter data
python wsgi.py
```

Open http://127.0.0.1:5000 — you'll be redirected to the login page.
Sign in with the `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` from your `.env`.

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | **Yes in production** | `rivive-dev-2026` | Session signing. Generate a long random value. |
| `DATABASE_URL` | No | `sqlite:///rivive.db` | `postgres://` is auto-rewritten to `postgresql://`. |
| `WTF_CSRF_ENABLED` | No | `1` | Keep `1` in production. |
| `SEED_ADMIN_USERNAME` | No | `admin` | Used only by `flask seed`. |
| `SEED_ADMIN_EMAIL` | No | `admin@rivive.local` | Used only by `flask seed`. |
| `SEED_ADMIN_PASSWORD` | Yes, to seed | — | Seeding aborts if unset when creating a new admin. |

## Deploying to Railway

1. **Create the project** — [railway.app](https://railway.app) → *New Project* →
   *Deploy from GitHub repo* → authorise GitHub → pick `DS-Hariprakash/Revive-Tool`.
   Nixpacks auto-detects Python from `requirements.txt`; `railway.json` supplies
   the start command and the `/healthz` health check.

2. **Add PostgreSQL** — in the project canvas: *New* → *Database* → *Add PostgreSQL*.

3. **Set variables** — open the web service → *Variables*:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference, not a literal) |
   | `SECRET_KEY` | a long random string |
   | `SEED_ADMIN_PASSWORD` | a strong password |
   | `FLASK_APP` | `wsgi.py` |

4. **Expose it** — *Settings* → *Networking* → *Generate Domain*. This is the
   URL you share for testing access.

5. **Create the schema and admin user** — once, after the first successful deploy:

   ```bash
   railway ssh
   flask seed
   ```

   If `railway ssh` is unavailable on your plan, run it locally against the
   remote database instead:

   ```bash
   railway link          # select the project and service
   railway run flask seed
   ```

6. **Verify** — `https://<your-domain>/healthz` should return `{"status":"ok"}`,
   and `/` should redirect to the login page.

### Redeploys

Railway watches the `main` branch. Every `git push origin main` triggers a
rebuild and deploy automatically.

### Schema changes

The seed calls `db.create_all()`, which creates missing tables but never alters
existing ones. Once the schema is live, use migrations:

```bash
flask db init      # first time only
flask db migrate -m "describe the change"
flask db upgrade   # run against Railway via `railway run`
```

## A note on Vercel

Vercel is serverless with an ephemeral filesystem, so SQLite cannot persist
there and `flask db upgrade` has nowhere to run. If you later want a Vercel
deployment, it must point `DATABASE_URL` at an external managed Postgres
(Railway's, Neon, or Supabase). Railway alone is sufficient for testing access.

## Licence

Internal project — all rights reserved.
