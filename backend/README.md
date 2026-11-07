# AUSSNSC Backend (FastAPI)

REST + WebSocket API for the AUSSNSC Android app. Python 3.11+, FastAPI, SQLAlchemy 2, SQLite by default
(PostgreSQL by changing `DATABASE_URL`).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit; export the values or use your host's env settings
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs  (interactive API docs)
pytest                          # smoke tests
```

First start creates the tables, classes 6–10 (A/B), the default channels, and an **admin** from
`ADMIN_PHONE` / `ADMIN_PASSWORD`. With `SEED_DEMO=1` it also creates demo users (password `Demo12345`):
student `01700000001`, teacher `01700000002`, parent `01700000003`. **Turn demo data off in production.**

Docker: `docker build -t aussnsc-api . && docker run -p 8000:8000 --env-file .env aussnsc-api`
(mount a volume for `UPLOAD_DIR` and the SQLite file, or use PostgreSQL).

## Roles and access (this replaces the app's preview-only role selector)

| Role | How it is obtained | Can do |
|---|---|---|
| Guest | no login | notices, result search, calendar, routines, gallery, teacher directory, admission info + application |
| `public` | self-registration | everything a guest can, plus profile/settings; **no academic data** |
| `student` | admin links the account to a student record | own attendance/results, class assignments, submissions, materials, class channels |
| `parent` | admin approves a child-link request | linked child's attendance/results/assignments, read-only class channels |
| `teacher` | admin links the account to a teacher profile | only their assigned classes: roster, attendance, assignments, reviews, materials, moderation |
| `admin` | bootstrap env vars | everything under `/api/v1/admin/*` |

Roles are checked on the server for every request; the app's role dropdown can no longer grant access.

## Endpoint map (prefix `/api/v1`)

- **Auth/account**: `POST /auth/register|login|refresh|logout-all`, `POST /auth/otp/request|verify`, `POST /auth/password/reset`,
  `GET|PATCH /me` (language `en|bn`, theme), `POST /me/password`, `POST|DELETE /me/devices` (push tokens)
- **Public**: `GET /classes /notices /notices/{id} /calendar /teachers /content/{about|admission} /gallery/albums[/{id}]`,
  `GET /routines/class/{id}`, `GET /routines/exam`, `GET /results/search?roll=&class_name=&exam=` or `?name=`, `GET /results/exams`,
  `POST /admission/applications`
- **Student/Parent**: `GET /me/student /me/attendance /me/results /me/submissions /assignments /materials`,
  `GET /students/{id}/attendance|results` (parents: linked children only), `POST /parent/links`, `GET /parent/links|children`,
  `POST /assignments/{id}/submissions`
- **Teacher**: `GET /teacher/classes`, `GET /classes/{id}/students`, `GET|POST /classes/{id}/attendance` / `POST /attendance`,
  `POST|PUT|DELETE /assignments`, `GET /assignments/{id}/submissions`, `PATCH /submissions/{id}/review`, `POST|DELETE /materials`, `POST /uploads`
- **Community**: `GET /channels`, `GET|POST /channels/{id}/messages`, `GET /channels/{id}/pinned`, `DELETE /messages/{id}`,
  `POST /messages/{id}/report|pin`, `GET /moderation/reports`, `POST /moderation/reports/{id}/resolve`,
  `POST|DELETE /channels/{id}/restrictions`, **WebSocket** `/ws/channels/{id}` (header `Authorization: Bearer …` or `?token=`; send `{"body":"…"}`)
- **Admin**: `/admin/stats`, `/admin/users`, `/admin/students` (+ CSV import), `/admin/teachers` (+ class assignment), `/admin/classes`,
  `/admin/parent-links`, `/admin/notices`, `/admin/results` (+ CSV import, publish), `/admin/routines/*`, `/admin/calendar`,
  `/admin/gallery/*`, `/admin/content/{key}`, `/admin/admission/applications`, `/admin/channels`, `/admin/reports/attendance`, `/admin/audit`

Lists accept `limit`/`offset`. Dates are ISO (`2026-11-10`), timestamps are UTC with a `Z`. Routine weekdays: 0 = Sunday … 6 = Saturday.
Attendance rate = (present + late) ÷ days recorded.

## Connecting the Android app

1. Add Retrofit/OkHttp (or Ktor) and a token store; send `Authorization: Bearer <access_token>`; on 401 call `/auth/refresh`.
2. Base URL: `http://10.0.2.2:8000/api/v1/` from the emulator. A real phone needs your server's address, and
   **release builds need HTTPS** (Android blocks plain HTTP by default) – put the API behind a TLS proxy (Caddy/nginx/your host).
3. Add `<uses-permission android:name="android.permission.INTERNET"/>` to the manifest (the preview doesn't have it yet).
4. Replace each `AppPage` sample list with the matching call above; use the WebSocket for live channel chat.
5. Uploaded files are returned as `/uploads/<name>`; prefix them with the server's base URL.

## Production checklist

- Set `ENV=production`, a long random `SECRET_KEY`, `SEED_DEMO=0`, strong `ADMIN_PASSWORD`, and `CORS_ORIGINS` if you add a web client.
- Use PostgreSQL and back it up; add Alembic migrations before changing the schema (tables are created with `create_all` today).
- Run behind HTTPS; set `TRUST_PROXY=1` if the proxy sets `X-Forwarded-For` so rate limits see real client IPs.
- **SMS/email are placeholders**: OTP codes are only logged until you wire a gateway in `app/notifications.py`
  (`SMS_WEBHOOK_URL` for a generic JSON webhook, or adapt `send_sms` to your provider; add SMTP/email in `send_email`).
- **Push** works through Firebase Admin when `FIREBASE_CREDENTIALS` is set and `firebase-admin` is installed; otherwise it only logs.
- Rate limiting and the WebSocket hub are in-memory (one process). For several workers/servers use Redis.
- Uploaded files are served by random, unguessable URL (not login-gated). Don't upload anything sensitive; for that, add signed URLs.
- Result search by name is public by design in the app. It's limited to published results, 3+ characters, 10 matches and rate-limited,
  but think about whether name search is appropriate for student privacy before enabling it for real data.
