import Head from "next/head";
import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `key-${Date.now()}-${Math.random()}`;
}

function StatBar({ label, value, total, color }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="stat">
      <div className="stat-row">
        <span className="stat-label">{label}</span>
        <span className="stat-value">
          {value} <span className="stat-of">/ {total}</span>
        </span>
      </div>
      <div className="bar">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <style jsx>{`
        .stat {
          margin-bottom: 14px;
        }
        .stat-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 6px;
          font-size: 13px;
        }
        .stat-label {
          color: var(--text-muted);
          font-weight: 500;
        }
        .stat-value {
          font-weight: 600;
        }
        .stat-of {
          color: var(--text-muted);
          font-weight: 400;
        }
        .bar {
          height: 8px;
          border-radius: 999px;
          background: var(--border);
          overflow: hidden;
        }
        .bar-fill {
          height: 100%;
          border-radius: 999px;
          transition: width 0.4s ease;
        }
      `}</style>
    </div>
  );
}

export default function LeadershipScreen() {
  const [email, setEmail] = useState("denise@local27.example.org");
  const [password, setPassword] = useState("password123");
  const [session, setSession] = useState(null); // { token, role, local_id }
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  const [rawText, setRawText] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [classificationFilter, setClassificationFilter] = useState("");
  const [needsAck, setNeedsAck] = useState(true);
  const [aiNote, setAiNote] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey());
  const [sendError, setSendError] = useState("");
  const [sending, setSending] = useState(false);
  const [announcement, setAnnouncement] = useState(null); // latest counts payload

  const pollRef = useRef(null);

  async function api(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
        ...options.headers,
      },
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  }

  async function handleLogin(e) {
    e.preventDefault();
    setLoginError("");
    setLoggingIn(true);
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (data.role !== "leadership") {
        setLoginError("This screen is for leadership accounts only.");
        return;
      }
      setSession(data);
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoggingIn(false);
    }
  }

  function handleLogout() {
    setSession(null);
    setAnnouncement(null);
  }

  async function handleGenerateDraft() {
    if (!rawText.trim()) return;
    setAiLoading(true);
    setAiNote(null);
    try {
      const draft = await api("/ai/draft", {
        method: "POST",
        body: JSON.stringify({ raw_text: rawText }),
      });
      setTitle(draft.title);
      setBody(draft.body);
      if (draft.note) setAiNote(draft.note);
    } catch (err) {
      setAiNote(`AI draft failed: ${err.message}`);
    } finally {
      setAiLoading(false);
    }
  }

  async function handleSend(e) {
    e.preventDefault();
    setSendError("");
    setSending(true);
    try {
      const result = await api("/announcements", {
        method: "POST",
        body: JSON.stringify({
          title,
          body,
          classification_filter: classificationFilter || null,
          needs_ack: needsAck,
          idempotency_key: idempotencyKey,
        }),
      });
      setAnnouncement(result);
    } catch (err) {
      setSendError(err.message);
    } finally {
      setSending(false);
    }
  }

  function startNewCompose() {
    setTitle("");
    setBody("");
    setRawText("");
    setAiNote(null);
    setAnnouncement(null);
    setSendError("");
    setIdempotencyKey(newIdempotencyKey());
  }

  // Poll counts for the active announcement every 3s -- see DESIGN.md section 2
  // for why this is a poll against one cached/aggregated endpoint rather than
  // each viewer hammering the database directly.
  useEffect(() => {
    if (!announcement || !session) return;
    pollRef.current = setInterval(async () => {
      try {
        const fresh = await api(`/announcements/${announcement.id}`);
        setAnnouncement(fresh);
      } catch {
        // transient poll failure; try again on the next tick
      }
    }, 3000);
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcement?.id, session]);

  if (!session) {
    return (
      <>
        <Head>
          <title>CrewLink — Leadership Login</title>
        </Head>
        <div className="auth-page">
          <div className="auth-card">
            <div className="brand">
              <span className="brand-mark">C</span>
              <span className="brand-name">CrewLink</span>
            </div>
            <h1>Leadership sign-in</h1>
            <p className="subtitle">Send callouts and track delivery for your local.</p>

            <form onSubmit={handleLogin}>
              <div className="field">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                />
              </div>
              <div className="field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </div>
              {loginError && <p className="error-text">{loginError}</p>}
              <button className="btn btn-primary btn-block" type="submit" disabled={loggingIn}>
                {loggingIn ? "Signing in…" : "Sign in"}
              </button>
            </form>

            <div className="seed-hint">
              Seeded login: <code>denise@local27.example.org</code> / <code>password123</code>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Head>
        <title>CrewLink — Send a Callout</title>
      </Head>
      <div className="page">
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark">C</span>
            <span className="brand-name">CrewLink</span>
          </div>
          <div className="topbar-right">
            <span className="badge" title={session.local_id}>
              Local {session.local_id.slice(-4)}
            </span>
            <button className="btn btn-ghost" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </header>

        <main className="content">
          <section className="card">
            <div className="card-header">
              <span className="step-number">1</span>
              <h2>Paste the messy note</h2>
              <span className="optional-tag">optional</span>
            </div>
            <textarea
              className="textarea"
              rows={3}
              placeholder="emergency mtg thurs 6pm hall re: contractor pulling crews off the westside job..."
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
            />
            <div className="card-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleGenerateDraft}
                disabled={aiLoading || !rawText.trim()}
              >
                {aiLoading ? "Generating…" : "✦ Generate draft with AI"}
              </button>
            </div>
            {aiNote && <div className="banner banner-warning">{aiNote}</div>}
          </section>

          <section className="card">
            <div className="card-header">
              <span className="step-number">2</span>
              <h2>Review and send</h2>
            </div>
            <form onSubmit={handleSend}>
              <div className="field">
                <label>Title</label>
                <input value={title} onChange={(e) => setTitle(e.target.value)} required />
              </div>
              <div className="field">
                <label>Body</label>
                <textarea
                  className="textarea"
                  rows={4}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  required
                />
              </div>
              <div className="field-row">
                <div className="field">
                  <label>Classification filter</label>
                  <input
                    value={classificationFilter}
                    onChange={(e) => setClassificationFilter(e.target.value)}
                    placeholder="All classifications"
                  />
                </div>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={needsAck}
                    onChange={(e) => setNeedsAck(e.target.checked)}
                  />
                  Requires acknowledgement
                </label>
              </div>
              {sendError && <div className="banner banner-error">{sendError}</div>}
              <div className="card-actions">
                <button className="btn btn-primary" type="submit" disabled={sending}>
                  {sending ? "Sending…" : "Send callout"}
                </button>
                <button type="button" className="btn btn-ghost" onClick={startNewCompose}>
                  New announcement
                </button>
              </div>
            </form>
          </section>

          {announcement && (
            <section className="card results-card">
              <div className="results-header">
                <div>
                  <h2 className="results-title">{announcement.title}</h2>
                  <p className="results-body">{announcement.body}</p>
                </div>
                <span className="live-dot" title="Refreshing every 3s" />
              </div>

              <StatBar
                label="Sent"
                value={announcement.sent_count}
                total={announcement.total_recipients}
                color="var(--primary)"
              />
              <StatBar
                label="Read"
                value={announcement.read_count}
                total={announcement.total_recipients}
                color="#0ea5e9"
              />
              <StatBar
                label="Acknowledged"
                value={announcement.acknowledged_count}
                total={announcement.total_recipients}
                color="var(--success)"
              />

              <p className="live-text">Live · updating every 3 seconds</p>
            </section>
          )}
        </main>
      </div>
    </>
  );
}
