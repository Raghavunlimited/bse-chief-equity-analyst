"""
Optional BYO LLM analysis for a desk signal.

API key is used only for the outbound provider call — never logged or persisted.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 90
OPENAI_DEFAULT_MODEL = "gpt-4o"
ANTHROPIC_DEFAULT_MODEL = "claude-opus-4-20250514"

# Allow-list — reject arbitrary model strings from clients
ALLOWED_MODELS = {
    "openai": frozenset(
        {
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
        }
    ),
    "anthropic": frozenset(
        {
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-5-sonnet-20241022",
        }
    ),
}

DISCLAIMER = (
    "LLM research notes only — not investment advice. "
    "No profit or outcome guarantees. Verify independently. "
    "AI commentary is not an authoritative signal. "
    "Keys sent in the request body are used ephemerally; "
    "keys saved in Settings are encrypted at rest server-side and never returned to the browser."
)

SYSTEM = (
    "You are a professional markets research assistant for Indian equities and commodities. "
    "You NEVER promise profits or give personalized investment advice. "
    "Use only the provided signal JSON and context. "
    "Respond with compact JSON keys: summary, bull_case, bear_case, risks (string), "
    "checklist (array of strings). "
    "Emphasize risk, invalidation, and position sizing discipline."
)


class LlmAnalyzeError(Exception):
    """User-visible LLM failure (safe detail — never includes API keys)."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _parse_json_content(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise LlmAnalyzeError(f"Model returned non-JSON: {exc}") from exc
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as exc2:
            raise LlmAnalyzeError(f"Model returned non-JSON: {exc2}") from exc2
    if not isinstance(data, dict):
        raise LlmAnalyzeError("Model JSON must be an object")
    return data


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    checklist = data.get("checklist") or []
    if isinstance(checklist, str):
        checklist = [checklist]
    if not isinstance(checklist, list):
        checklist = [str(checklist)]
    risks = data.get("risks", "")
    if isinstance(risks, list):
        risks = "; ".join(str(x) for x in risks)
    return {
        "summary": str(data.get("summary") or "").strip(),
        "bull_case": str(data.get("bull_case") or "").strip(),
        "bear_case": str(data.get("bear_case") or "").strip(),
        "risks": str(risks).strip(),
        "checklist": [str(x).strip() for x in checklist if str(x).strip()][:20],
    }


def _openai(api_key: str, user_payload: str, model: str = OPENAI_DEFAULT_MODEL) -> Dict[str, Any]:
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_payload},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    out = _normalize(_parse_json_content(content))
    out["provider"] = "openai"
    out["model"] = model
    return out


def _anthropic(
    api_key: str,
    user_payload: str,
    model: str = ANTHROPIC_DEFAULT_MODEL,
) -> Dict[str, Any]:
    body = {
        "model": model,
        "max_tokens": 1600,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": user_payload}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )
    out = _normalize(_parse_json_content(text))
    out["provider"] = "anthropic"
    out["model"] = model
    return out


def _resolve_model(provider: str, model: Optional[str]) -> str:
    allowed = ALLOWED_MODELS[provider]
    if model:
        m = str(model).strip()
        if m not in allowed:
            raise LlmAnalyzeError(
                f"model not allowed for {provider}; choose one of: {', '.join(sorted(allowed))}",
                status_code=422,
            )
        return m
    return OPENAI_DEFAULT_MODEL if provider == "openai" else ANTHROPIC_DEFAULT_MODEL


def analyze_signal(
    signal: Dict[str, Any],
    provider: str,
    api_key: str,
    context: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Call OpenAI or Anthropic and return structured research JSON.

    Never logs ``api_key``. Timeout 90s (Opus / reasoning models). Research only.
    """
    if not isinstance(signal, dict) or not signal:
        raise LlmAnalyzeError("signal must be a non-empty object", status_code=422)

    provider = (provider or "openai").lower().strip()
    key = (api_key or "").strip()
    if not key:
        raise LlmAnalyzeError("api_key is required", status_code=422)
    if provider not in ("openai", "anthropic"):
        raise LlmAnalyzeError("provider must be openai or anthropic", status_code=422)

    resolved_model = _resolve_model(provider, model)

    logger.info(
        "LLM analyze start provider=%s model=%s signal_keys=%s has_context=%s",
        provider,
        resolved_model,
        sorted(signal.keys())[:20],
        bool(context),
    )

    payload = {
        "signal": signal,
        "context": context or {},
        "instruction": "Critique this research call; do not invent prices not in the payload.",
    }
    user_payload = json.dumps(payload, ensure_ascii=False, default=str)[:12000]

    try:
        if provider == "openai":
            return _openai(key, user_payload, model=resolved_model)
        return _anthropic(key, user_payload, model=resolved_model)
    except LlmAnalyzeError:
        raise
    except urllib.error.HTTPError as exc:
        # Do not include request headers (would leak key)
        logger.warning("LLM provider HTTP %s", exc.code)
        if exc.code in (401, 403):
            raise LlmAnalyzeError(
                "LLM authentication failed — check your API key",
                status_code=401,
            ) from exc
        if exc.code == 429:
            raise LlmAnalyzeError("LLM rate limit exceeded", status_code=429) from exc
        raise LlmAnalyzeError(f"LLM provider error {exc.code}", status_code=502) from exc
    except urllib.error.URLError as exc:
        logger.warning("LLM network error: %s", type(exc.reason).__name__ if exc.reason else "URLError")
        raise LlmAnalyzeError("LLM request failed (network)", status_code=502) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM analyze failed: %s", type(exc).__name__)
        raise LlmAnalyzeError("LLM analyze failed", status_code=502) from exc
