# CrewLink — Member Callout (exercise submission)

Design and rationale: [DESIGN.md](DESIGN.md). Diagram: [Diagram.md](Diagram.md). AI chat log: [AI-CONVERSATIONS.md](AI-CONVERSATIONS.md).

**Verification note:** the dev sandbox this was built in has no Docker (and no
passwordless sudo to install it), so `docker-compose.yml` itself is written
and reviewed but not container-tested. What *is* tested, end-to-end, against
the exact code that ships in the containers: the backend on the same port
Compose exposes (8000) backed by a fresh seed, and the Next.js frontend built
against it — full journey run over real HTTP (AI draft → send → idempotent
retry → live counts → member ack → counts update → both isolation checks).
Please run `docker compose up --build` yourself once before submitting.

Stack note: built in **FastAPI + SQLAlchemy + Postgres** rather than the
preferred Django+DRF, since that's the stack I'm strongest in for explicit,
dependency-based authorization (see DESIGN.md's Rule 1 section for how that
maps to the ViewSet-mixin idea in the original design).

## Run it

```
docker compose up --build
docker compose exec backend python -m app.seed   # 2 locals, ~2,200 members, one already-sent announcement
```

- API: http://localhost:8000 (interactive docs at `/docs`)
- Leadership screen: http://localhost:3000
- Auth: `Authorization: Bearer <token>` from `POST /auth/login`

No Docker? `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m app.seed && .venv/bin/uvicorn app.main:app --reload` (falls back to SQLite). Frontend: `cd frontend && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev`.

## Member read/ack flow (curl)

```
TOKEN=$(curl -s -X POST localhost:8000/auth/login -d '{"email":"carlos.johnson.0@example.org","password":"password123"}' | jq -r .token)
curl -s localhost:8000/me/inbox -H "Authorization: Bearer $TOKEN"                 # find a recipient_id
curl -s -X POST localhost:8000/recipients/<recipient_id>/read -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/recipients/<recipient_id>/ack  -H "Authorization: Bearer $TOKEN"
```

## Rule 1 — cross-local isolation (curl)

```
T9=$(curl -s -X POST localhost:8000/auth/login -d '{"email":"leadership@local9.example.org","password":"password123"}' | jq -r .token)
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/announcements/20000000-0000-0000-0000-000000000001 -H "Authorization: Bearer $T9"
# -> 404: Local 9's leadership token cannot see Local 27's announcement, existing or not
```

## Rule 2 — retried send doesn't double-deliver

Verified by re-POSTing `/announcements` with the same `idempotency_key` twice
(same request, e.g. a UI double-click or a network retry) and asserting
`total_recipients`/`sent_count` are identical both times — no second fan-out,
no second push. See the curl sequence in DESIGN.md §3, or run it yourself:
the same `idempotency_key` in two consecutive `POST /announcements` calls
returns the same announcement id and identical counts.

## TEST ACCOUNTS

```json
{
  "local_27": {
    "leadership_login": { "email": "denise@local27.example.org", "password": "password123" },
    "member_login": { "email": "carlos.johnson.0@example.org", "password": "password123" },
    "existing_announcement_id": "20000000-0000-0000-0000-000000000001"
  },
  "local_9": {
    "leadership_login": { "email": "leadership@local9.example.org", "password": "password123" },
    "member_login": { "email": "karen.smith.0@example.org", "password": "password123" },
    "member_id": "10000000-0000-0000-0000-000000000009"
  },
  "endpoints": [
    { "method": "POST", "path": "/auth/login", "auth": "none", "body": "{email, password}" },
    { "method": "GET",  "path": "/announcements", "auth": "Bearer token, leadership role" },
    { "method": "GET",  "path": "/announcements/{id}", "auth": "Bearer token, leadership role, scoped to own local" },
    { "method": "POST", "path": "/announcements", "auth": "Bearer token, leadership role", "body": "{title, body, classification_filter?, needs_ack, idempotency_key}" },
    { "method": "GET",  "path": "/me/inbox", "auth": "Bearer token, member role" },
    { "method": "POST", "path": "/recipients/{id}/read", "auth": "Bearer token, member role, own recipient row only" },
    { "method": "POST", "path": "/recipients/{id}/ack", "auth": "Bearer token, member role, own recipient row only" },
    { "method": "POST", "path": "/ai/draft", "auth": "Bearer token, leadership role", "body": "{raw_text}" }
  ]
}
```
