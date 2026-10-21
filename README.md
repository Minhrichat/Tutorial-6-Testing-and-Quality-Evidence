# Pizza Hut — Employee Onboarding & Training Management System (INS3282 – Tutorial 5/6)

Vertical slice **FR-ONB-03**: a new employee submits a training-module score; the system checks the pass mark and module order, then updates progress and the onboarding status (UI → API → SQLite).

## Requirements
Python 3.10+ (tested on 3.12). No separate database needed (SQLite).

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python manage.py setup             # migrate + seed (safe to re-run)
python manage.py run               # open http://127.0.0.1:5000
```

## Useful commands
| Command | Purpose |
|---|---|
| `python manage.py migrate` | Apply pending migrations |
| `python manage.py seed` | Load demo data (idempotent) |
| `python manage.py reset` | Delete the DB, recreate and seed |
| `pytest -v` | Run all tests (Tutorial 5 + Tutorial 6) |
| `python scripts/smoke_test.py` | End-to-end demo against a running server |
| `python scripts/load_test.py` | Load test (see script header) |
| `python scripts/backup_restore_test.py` | Backup / restore check |
| `bash scripts/clean_run_check.sh` | Clean run from scratch (new venv, new DB) |

## Structure
```
app.py  services.py  db.py  manage.py
migrations/001_init.sql     seeds/001_seed.sql
templates/index.html        tests/test_slice.py  tests/test_tutorial6.py
scripts/                    docs/RUNBOOK.md      evidence/
.github/workflows/ci.yml    .github/pull_request_template.md
```

## API
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/api/roles` | List roles |
| GET/POST | `/api/employees` | List / create employees (training plan assigned by role) |
| GET | `/api/employees/<id>/progress` | Onboarding progress |
| POST | `/api/employees/<id>/modules/<module_id>/complete` | Body `{"score": 0..100}` |

Errors use the shape `{"error": {"code": "...", "message": "..."}}` (400 / 404 / 409).

## Branch & commit conventions
`main` is always runnable · `feature/<issue>-<name>` · `fix/...` · commits: `feat(onboarding): ... (#12, FR-ONB-03)`.
