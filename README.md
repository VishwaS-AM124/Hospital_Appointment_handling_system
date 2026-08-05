# Hospital Appointment Booking System

A full-stack appointment scheduler with **doctor** and **patient** roles, slot
availability management, strict double-booking prevention, and a fair **waiting queue**
with notifications.

**React (Vite)** · **FastAPI (Python 3.13)** · **MySQL 8.0**

The interesting part of this project is not the CRUD — it is the concurrency control, the
waiting queue, and the authorization boundaries. Those are argued in
**[docs/DESIGN.md](docs/DESIGN.md)**.

---

## What it does

| Role | Can | Cannot |
|---|---|---|
| **Doctor** | CRUD own services and slots; view, complete and cancel appointments on own schedule; see how many patients are queued for each slot | See or touch another doctor's schedule; browse the open-slot marketplace; edit or delete a slot that is booked |
| **Patient** | Browse open slots; book; cancel own appointments; view own history; queue for taken slots | Create slots; see another patient's appointments; see who booked a slot; jump a queue |

### The five business rules

| # | Rule | Enforced by |
|---|---|---|
| 1 | A slot holds **at most one** booked appointment at a time | `SELECT … FOR UPDATE` row lock **+** status re-check **+** `UNIQUE` index on a generated column — three independent layers |
| 2 | Only **OPEN** slots can be booked | status re-check inside the locked transaction |
| 3 | Cancelling an appointment **reopens** the slot | appointment → `CANCELLED` and slot → `OPEN` in one transaction |
| 4 | A doctor **cannot edit or delete** a booked slot | ownership + status check under `FOR UPDATE` |
| 5 | Each party sees only their own data | every query filtered by owner id; not-yours ⇒ `404`, wrong-role ⇒ `403` |

### Waiting queue and notifications

Losing a booking race is not a dead end:

- The patient who loses is placed in that slot's **FIFO queue** and told their position
  (`"you are #2 in the queue"`), both in the API response and in the UI.
- When the slot is released, the patient **at the head of the queue** is notified and gets
  an **exclusive claim window** (15 min by default) — during which any other patient
  trying to book it is refused with `409 SLOT_RESERVED`.
- If they let the window lapse, the offer passes down the queue automatically.
- The **doctor is notified** whenever a patient books, and the other party is notified on
  cancellation or completion.

Queue integrity is enforced by the database, not by hopeful application code: a `UNIQUE`
index on a generated column makes **more than one live offer per slot impossible**. See
[docs/DESIGN.md §4](docs/DESIGN.md).

---

## Prerequisites

- **Python 3.13** (3.11+ works)
- **Node.js 20+**
- **MySQL 8.0** running locally, and a user that can `CREATE DATABASE`

Developed and verified on Windows 11 with MySQL 8.0.44, Python 3.13.5, Node 24.19.

---

## Setup

All commands are PowerShell, run from the repository root.

### 1. Backend

```powershell
cd backend

python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env          # set DB_USER / DB_PASSWORD, and a JWT_SECRET
```

`.env` needs at minimum:

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-mysql-password
DB_NAME=appointment_db
JWT_SECRET=any-long-random-string
```

Generate a real secret with:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Create the schema and demo data

```powershell
# from backend/
.\venv\Scripts\python.exe -m scripts.init_db
```

Creates the database, applies [`sql/01_schema.sql`](backend/sql/01_schema.sql), and seeds
3 doctors, 4 patients, 6 services and 27 slots. Safe to re-run. `--drop --yes` rebuilds
from scratch; `--no-seed` gives an empty schema.

Seed dates are generated relative to *now*, so there are always upcoming appointments.

### 3. Run the API

```powershell
# from backend/
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- **Swagger UI: <http://127.0.0.1:8000/docs>** — the **Authorize** button works with any demo account
- Health: <http://127.0.0.1:8000/health>

### 4. Run the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open **<http://localhost:5173>**.

> Use `localhost`, not `127.0.0.1`. Vite binds to `localhost` (IPv6 `::1` on Windows), and
> that is the origin allow-listed for CORS.

---

## Demo accounts

All demo accounts use the password **`Passw0rd!`**. The login page has one-click
**Fill Doctor** / **Fill Patient** buttons.

| Role | Email |
|---|---|
| Doctor | `anita.rao@citycare-hospital.com` (Cardiology) |
| Doctor | `vikram.shah@citycare-hospital.com` (Orthopaedics) |
| Doctor | `leela.menon@citycare-hospital.com` (Dermatology) |
| Patient | `ravi.kumar@example.com` |
| Patient | `sana.iqbal@example.com` |
| Patient | `john.doe@example.com` |
| Patient | `mei.lin@example.com` |

---

## A 3-minute tour of the interesting behaviour

1. Sign in as **Ravi (patient)** → *Find an appointment* → **Book** any open slot.
2. In a private window, sign in as **Sana** and try to book **the same slot**. She is
   refused *and queued*: a toast reads **"you are #1 in the queue"**. Check
   *My appointments → Waiting list* to see her place. **Rules 1 + 2.**
3. Sign in as **Dr. Anita**. The 🔔 bell shows an unread **"Ravi Kumar booked an
   appointment"**. On *Availability*, the booked slot's **Edit**/**Delete** are disabled
   with a tooltip. **Rule 4.**
4. As **Ravi**, cancel the appointment.
5. Back as **Sana**: the bell now shows **"A slot you were waiting for is now free"**, and
   *Waiting list* shows **"This slot is being held for you"** with a countdown and a
   **Book it now** button. If a third patient tries that slot meanwhile they get
   `SLOT_RESERVED`. **Rule 3 + the queue.**
6. Note that Dr. Anita has **no way at all** to view another doctor's schedule —
   `GET /slots/open` returns `403` for a doctor account. **Rule 5.**

---

## Project layout

```
backend/
  app/
    api/v1/         routers — thin: validate, call a service, serialize
    services/       ALL business rules live here (the transactions)
    models/         SQLAlchemy 2.0 ORM
    schemas/        Pydantic v2 request/response DTOs
    core/           config, security (bcrypt + JWT), errors, timezone helpers
    db/             engine + session
  sql/01_schema.sql canonical DDL, heavily commented
  scripts/init_db.py create + migrate + seed
frontend/
  src/api/          fetch wrapper + one function per endpoint
  src/auth/         AuthContext + route guard
  src/components/   Button, Modal, Toast, NotificationBell, WaitlistPanel, …
  src/pages/        doctor/ and patient/ screens
  src/utils/        the client-side timezone boundary
docs/DESIGN.md      ← the reasoning: concurrency, the queue, authz, schema trade-offs
```

---

## Notable design decisions

Argued properly in [docs/DESIGN.md](docs/DESIGN.md); in brief:

- **Three layers against double-booking**, not one. The `UNIQUE` index is the layer that
  still holds if the application logic is ever wrong, because `FOR UPDATE` cannot lock a
  row that does not exist yet.
- **A generated column, not `UNIQUE(slot_id)`.** A plain unique key would also block
  re-booking after a cancellation, which rule 3 requires. MySQL has no partial indexes,
  so `occupies_slot_id` projects "does this row hold the slot?" into an indexable value
  that is `NULL` for cancelled rows. The same technique gives the queue its
  one-live-offer-per-slot guarantee.
- **`VIRTUAL`, not `STORED`.** With `STORED`, MySQL refuses to create the table at all
  (`ERROR 1215`), because it forbids `ON DELETE CASCADE` on the base column of a stored
  generated column. Found by testing the DDL, not by guessing.
- **One lock covers a slot, its appointments and its queue,** so the global lock order
  stays `slots → appointments` and cannot deadlock.
- **`404` for someone else's row, `403` only for wrong role.** A `403` would confirm the
  id exists and let anyone enumerate the tables.
- **Half-open intervals `[start, end)`.** 09:00–09:30 and 09:30–10:00 are neighbours, not
  a collision — otherwise a doctor could not publish a contiguous day.
- **UTC everywhere in the database; the API refuses offset-less datetimes** rather than
  guessing a timezone.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Access denied for user 'root'@'localhost'` | Wrong `DB_PASSWORD` in `backend/.env`. Confirm with `mysql -u root -p -e "SELECT 1"`. |
| `RuntimeError: 'cryptography' package is required` | `pip install -r requirements.txt` — MySQL 8 defaults to `caching_sha2_password`, which PyMySQL can only speak via `cryptography`. |
| `pydantic ValidationError: jwt_secret Field required` | `backend/.env` is missing or has no `JWT_SECRET`. |
| Frontend loads but every call fails | The API is not running on port 8000, or you opened `127.0.0.1:5173` instead of `localhost:5173` (CORS). |
| `Port 5173 is already in use` | A dev server is still running: `Get-Process node \| Stop-Process`. |
| `Port 8000 already in use` | Use `--port 8001` and set `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1` in `frontend/.env`. |
| `value is not a valid email address … reserved name` | Domains ending in `.test`/`.local` are rejected by RFC 6761. Use a normal domain. |

---

## What I would add next

- **Recurring availability** — a weekly template expanded into slots.
- **Rescheduling as one atomic operation** rather than cancel-then-rebook, so the patient
  cannot lose their place mid-move.
- **Email/SMS delivery** for the notifications that currently live in the in-app inbox,
  and **SSE** instead of polling for the unread badge.
- **Refresh tokens + rotation**; access tokens are long-lived (12 h) for demo convenience.
- **Rate limiting** on login and booking.
- **Audit log** table, since appointments are quasi-medical records.
