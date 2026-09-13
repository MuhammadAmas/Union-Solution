# DESIGN.md

## Part 0 — Requirements

**What I'm building, in plain terms**

A callout/announcement system for union locals: leadership at a local can write a message, target it at their local (optionally narrowed to one or more work classifications), and send it. Every targeted member gets a per-recipient record so leadership can watch, in near-real-time, how many were sent, read, and acknowledged. Members can be offline for hours or days without breaking anything — the system has to hold state for them until they reconnect, not assume delivery happens once, immediately. Two things are non-negotiable regardless of how the rest is built: a local's data (members, contact info, announcements) is never visible outside that local, and a leader's send action never reaches the same member twice, even if the send is retried or a process crashes mid-send.

**Assumptions**

- "Immediately" means the system *attempts* a push at send time; there's no separate "urgent" delivery tier beyond the normal send path. Offline members simply see it (as unread) whenever they next open the app.
- RSVP ("coming" / "can't") is optional per-announcement, mirroring the existing `needs_ack` flag — not every callout requires a response.
- "Done" for Part B means: an announcement is created and sent to a real audience, recipient rows exist per member, a member can read/acknowledge it via an endpoint, and the leadership screen shows live counts — with both rules demonstrably enforced, not just assumed.
- A leadership account is scoped to exactly one local; nobody manages multiple locals in this exercise.
- A member belongs to exactly one local.
- "Read" and "acknowledged" are distinct, ordered states (acknowledging implies having read).
- The 5–10% silent push failures are invisible to my backend (no hard error from the provider) — I treat "no read receipt yet" as the normal state for those, not as a failure needing special-case retry logic. Retries are only ever leadership-initiated ("this looks stuck"), never automatic per-recipient.

**What concerns me**

The apprentice contact-info issue is phrased like it might already be happening ("someone mentioned that during onboarding"), not a hypothetical risk — that reads like a live data leak, not a design constraint to prevent going forward. It needs an explicit access-control audit and a regression test, not just "the new design won't do that." Separately: Denise wants to know "who's coming," but nothing says what a non-response means. If the system (or leadership, reading the UI) treats silence as "not coming," that's a misreading baked into the product — silence has to render as its own state, distinct from an explicit decline.

**Questions I'd ask Denise (and what I assumed instead)**

1. Is RSVP mandatory for every callout, or only some? → Assumed optional per-announcement, controlled by `needs_ack`.
2. Should retired or suspended members ever receive a callout (e.g., a contract ratification vote that affects them too)? → Assumed no; only `active` members are ever targeted.
3. When you say "outside our local," do you mean other members only, or other locals' *leadership* as well? → Assumed both — no one outside a local, member or leader, can see that local's roster or contact info.

---

## Part A — Design

### 1. Data model

```
locals(id, name)

members(id, local_id -> locals, full_name, email, classification, status)
  -- the union roster; status: active | retired | suspended

accounts(id, local_id -> locals, member_id -> members NULL, role, email, password_hash)
  -- login identity, separate from "members" because a business manager
  -- isn't necessarily a member row. role: 'member' | 'leadership'.
  -- local_id lives here directly (not derived via member_id) so every
  -- authorization check has one non-nullable field to filter on.

announcements(id, local_id -> locals, created_by -> accounts, title, body,
              classification_filter text NULL, needs_ack boolean,
              sent_at timestamptz NULL, created_at timestamptz)

recipients(id, announcement_id -> announcements, member_id -> members,
           status, sent_at, read_at, acknowledged_at, rsvp text NULL)
  -- UNIQUE (announcement_id, member_id)
  -- status: pending -> sent -> read -> acknowledged
  -- rsvp: null | 'yes' | 'no'  (independent of status/needs_ack)

send_jobs(id, announcement_id -> announcements UNIQUE, status, started_at, finished_at)
  -- one job per announcement, ever; this is what makes "press Send twice"
  -- and "retry a stuck send" safe at the job level, before we even get
  -- to per-recipient idempotency.
```

One recipient row per targeted member is both the audience list *and* the status ledger — it's created once, at fan-out time, and only ever updated afterward (never re-inserted), which is what makes rule 2 structural rather than behavioral (see §3).

### 2. The send path

Leadership presses Send at 14:02:

1. The request hits the load balancer, lands on one of N app instances.
2. That instance validates the session, confirms the account's `role == leadership`, and — critically — sets `announcement.local_id` from the *account's* `local_id`, never from anything the client sent. It inserts the announcement row and a `send_jobs` row keyed uniquely by `announcement_id`. Both inserts happen in one transaction.
3. The request returns (e.g., `202 Accepted`) as soon as that transaction commits — this is milliseconds, not proportional to audience size. The UI flips to "sending."
4. A background worker picks up the job and does the actual fan-out: bulk-inserts recipient rows for the ~22,400 targeted members using `INSERT ... ON CONFLICT (announcement_id, member_id) DO NOTHING`, batched (e.g., 1–5k rows per batch) so a crash mid-fan-out just resumes from wherever it left off — already-inserted rows are silently skipped, not duplicated.
5. For each recipient row, a push-send task fires; success or provider failure, the recipient row's `status` moves to `sent` once the attempt is made (a push failure doesn't roll anything back — it's a UI/analytics distinction, not a resend trigger).
6. `send_jobs.status` and `announcement.sent_at` are set once fan-out is complete.

Live counts, watched by four people in the office: they don't poll Postgres directly. A lightweight periodic aggregator (every 2–3s, or event-driven) computes `sent/read/acknowledged` counts once per announcement and writes them to a cache (Redis key or a small `announcement_counts` row). The frontend either polls that cache endpoint or subscribes over SSE/WebSocket for push updates. Either way, the expensive aggregation happens once server-side per interval and is shared across every viewer, instead of once per browser per second.

### 3. The two rules, by design

**Rule 1 — isolation.** Enforced at the query layer, not per-endpoint. Every query touching `members`, `announcements`, or `recipients` goes through a manager method that takes the requesting account and mandatorily injects `local_id = account.local_id` — there's no code path that queries these tables without it, because the base ViewSet applies it automatically rather than leaving it to each new view to remember. That's the answer to "what happens when someone adds an endpoint next year and forgets": they inherit the scoping by extending the base class; bypassing it means visibly not using the shared query path, which stands out in review. Postgres row-level security is the backstop under that, in case a raw query ever slips through. The member/leadership boundary is a second, independent check — a permission class on the viewset (e.g. `IsLeadershipOfLocal`) gating create/send actions — so local-scoping and role-checking can't be bypassed by only remembering one of the two.
Detection in production: a scheduled synthetic check logs in as a leadership account for Local A and attempts to read Local B's members/announcements, alerting if it doesn't get zero rows / 403. Access logs are tagged with `(account.local_id, resource.local_id)`; any line where they differ is an active alert, not just something to notice in a report later.

**Rule 2 — exactly-once.** The mechanism is the `UNIQUE (announcement_id, member_id)` constraint on `recipients`, combined with `ON CONFLICT DO NOTHING` inserts — not an in-memory "have we sent this" flag, which is exactly what breaks the moment there's a second process (the trap called out in the bonus section). A retried "Send" click hits the same `send_jobs` row (unique on `announcement_id`), so it's a no-op at the job level too, before fan-out is even considered. A worker that crashes mid-batch and restarts just re-runs the same insert, which the unique constraint reduces to updating nothing for rows that already exist. Push dispatch is idempotent per recipient the same way: each task checks `recipient.status` before sending; already-`sent` is a no-op, so a restarted worker re-walking a job doesn't re-push.
Detection: a scheduled check comparing `count(distinct member_id)` to `count(*)` in `recipients` per announcement (must be equal — any excess means duplicate rows slipped past the constraint somehow), plus alerting on any push-provider log showing two message IDs for the same (member, announcement) pair.

### 4. Diagram

See `diagram.md` (Mermaid) in the repo root.