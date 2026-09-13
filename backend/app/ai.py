"""The AI draft feature. What matters here, per the brief, is the integration
shape, not the prompt: a slow/down provider must degrade to something usable
instead of failing the request, and nothing this function returns is ever sent
to a member -- it only pre-fills the compose form for a human to review and
explicitly submit via POST /announcements (see routers/announcements.py)."""

import json
import re

import httpx

from app.config import settings
from app.schemas import AiDraftResponse

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = (
    "You turn a union business manager's rushed, informal message into a clear "
    "callout announcement. Respond with ONLY a JSON object with keys "
    '"title" (short, plain), "body" (1-3 sentences, keep every concrete fact: '
    "date, time, place, reason), and \"push_preview\" (<=120 characters, the "
    "most urgent fact first). No markdown, no commentary, just the JSON object."
)


def _heuristic_draft(raw_text: str, *, degraded: bool, note: str) -> AiDraftResponse:
    """Deterministic, no-dependency fallback: used when no provider is
    configured at all, and when a configured provider is slow, errors, or
    returns something we can't parse."""
    cleaned = re.sub(r"\s+", " ", raw_text).strip()
    first_clause = re.split(r"[.!]\s|,\s", cleaned, maxsplit=1)[0]
    title = (first_clause[:70] + "...") if len(first_clause) > 70 else first_clause
    title = title[:1].upper() + title[1:] if title else "Announcement"
    body = cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned
    preview = body if len(body) <= 120 else body[:117] + "..."
    return AiDraftResponse(
        title=title or "Announcement",
        body=body or raw_text,
        push_preview=preview,
        mode="heuristic",
        degraded=degraded,
        note=note,
    )


def generate_draft(raw_text: str) -> AiDraftResponse:
    if not settings.anthropic_api_key:
        return _heuristic_draft(
            raw_text,
            degraded=False,
            note="No AI provider configured (ANTHROPIC_API_KEY unset) -- using a plain-text draft.",
        )

    try:
        response = httpx.post(
            ANTHROPIC_URL,
            timeout=settings.ai_timeout_seconds,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 400,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": raw_text}],
            },
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"]
        parsed = json.loads(text)
        title = str(parsed["title"]).strip()
        body = str(parsed["body"]).strip()
        preview = str(parsed["push_preview"]).strip()[:120]
        return AiDraftResponse(
            title=title,
            body=body,
            push_preview=preview,
            mode="llm",
            degraded=False,
            note=None,
        )
    except httpx.TimeoutException:
        return _heuristic_draft(
            raw_text,
            degraded=True,
            note=f"AI provider timed out after {settings.ai_timeout_seconds}s -- showing a plain-text draft instead.",
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        return _heuristic_draft(
            raw_text,
            degraded=True,
            note=f"AI provider error ({type(exc).__name__}) -- showing a plain-text draft instead.",
        )
