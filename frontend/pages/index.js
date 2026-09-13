import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `key-${Date.now()}-${Math.random()}`;
}

export default function LeadershipScreen() {
  const [email, setEmail] = useState("denise@local27.example.org");
  const [password, setPassword] = useState("password123");
  const [session, setSession] = useState(null); // { token, role, local_id }
  const [loginError, setLoginError] = useState("");

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
    }
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
      <main style={{ fontFamily: "sans-serif", maxWidth: 420, margin: "60px auto" }}>
        <h1>CrewLink — Leadership Login</h1>
        <form onSubmit={handleLogin}>
          <div>
            <label>Email</label>
            <br />
            <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%" }} />
          </div>
          <div style={{ marginTop: 8 }}>
            <label>Password</label>
            <br />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ width: "100%" }}
            />
          </div>
          {loginError && <p style={{ color: "crimson" }}>{loginError}</p>}
          <button type="submit" style={{ marginTop: 12 }}>
            Log in
          </button>
        </form>
        <p style={{ color: "#666", fontSize: 13 }}>
          Seeded leadership login: denise@local27.example.org / password123
        </p>
      </main>
    );
  }

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: 640, margin: "40px auto" }}>
      <h1>CrewLink — Send a Callout</h1>
      <p style={{ color: "#666" }}>
        Local: <code>{session.local_id}</code>
      </p>

      <section style={{ border: "1px solid #ccc", padding: 16, marginBottom: 16 }}>
        <h3>1. Paste the messy note (optional)</h3>
        <textarea
          rows={3}
          style={{ width: "100%" }}
          placeholder="emergency mtg thurs 6pm hall re: contractor pulling crews off the westside job..."
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
        />
        <button type="button" onClick={handleGenerateDraft} disabled={aiLoading || !rawText.trim()}>
          {aiLoading ? "Generating..." : "Generate draft with AI"}
        </button>
        {aiNote && <p style={{ color: "#a15c00" }}>{aiNote}</p>}
      </section>

      <form onSubmit={handleSend} style={{ border: "1px solid #ccc", padding: 16 }}>
        <h3>2. Review and send</h3>
        <div>
          <label>Title</label>
          <br />
          <input value={title} onChange={(e) => setTitle(e.target.value)} required style={{ width: "100%" }} />
        </div>
        <div style={{ marginTop: 8 }}>
          <label>Body</label>
          <br />
          <textarea
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ marginTop: 8 }}>
          <label>Classification filter (optional)</label>
          <br />
          <input
            value={classificationFilter}
            onChange={(e) => setClassificationFilter(e.target.value)}
            placeholder="e.g. Apprentice 3rd Year"
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ marginTop: 8 }}>
          <label>
            <input type="checkbox" checked={needsAck} onChange={(e) => setNeedsAck(e.target.checked)} />
            Requires acknowledgement
          </label>
        </div>
        {sendError && <p style={{ color: "crimson" }}>{sendError}</p>}
        <button type="submit" disabled={sending} style={{ marginTop: 12 }}>
          {sending ? "Sending..." : "Send"}
        </button>
        <button type="button" onClick={startNewCompose} style={{ marginTop: 12, marginLeft: 8 }}>
          New announcement
        </button>
      </form>

      {announcement && (
        <section style={{ marginTop: 16, border: "1px solid #ccc", padding: 16 }}>
          <h3>{announcement.title}</h3>
          <p>{announcement.body}</p>
          <table>
            <tbody>
              <tr>
                <td>Total recipients</td>
                <td>{announcement.total_recipients}</td>
              </tr>
              <tr>
                <td>Sent</td>
                <td>{announcement.sent_count}</td>
              </tr>
              <tr>
                <td>Read</td>
                <td>{announcement.read_count}</td>
              </tr>
              <tr>
                <td>Acknowledged</td>
                <td>{announcement.acknowledged_count}</td>
              </tr>
            </tbody>
          </table>
          <p style={{ color: "#666", fontSize: 13 }}>Updating every 3s...</p>
        </section>
      )}
    </main>
  );
}
