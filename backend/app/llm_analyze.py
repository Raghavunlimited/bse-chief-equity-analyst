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
LOCAL_DEFAULT_MODEL = "llama3.2"
LOCAL_KEY_SENTINEL = "local-no-key-required"

# Allow-list — reject arbitrary model strings from cloud clients.
# Provider ``local`` uses a safe name pattern instead (Ollama/LM Studio tags).
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
    "local": frozenset(
        {
            "llama3.2",
            "llama3.1",
            "llama3",
            "mistral",
            "qwen2.5",
            "phi3",
            "gemma2",
            "codellama",
        }
    ),
}

_LOCAL_MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,79}$")

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


def assert_loopback_base_url(base_url: str) -> str:
    """
    SSRF guard: local LLM base URL must target loopback only.
    Accepts http://127.0.0.1:PORT/v1 or http://localhost:PORT/v1.
    """
    from urllib.parse import urlparse

    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        raise LlmAnalyzeError("local LLM base URL is empty", status_code=422)
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise LlmAnalyzeError("local LLM URL must be http(s)", status_code=422)
    host = (parsed.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise LlmAnalyzeError(
            "local LLM URL must use 127.0.0.1 or localhost (loopback only)",
            status_code=422,
        )
    if parsed.username or parsed.password:
        raise LlmAnalyzeError("local LLM URL must not embed credentials", status_code=422)
    return raw


def _openai_compatible(
    api_key: str,
    user_payload: str,
    *,
    model: str,
    base_url: str,
    provider_label: str,
) -> Dict[str, Any]:
    """OpenAI chat-completions shape — used for openai cloud and local (Ollama/LM Studio)."""
    root = assert_loopback_base_url(base_url) if provider_label == "local" else base_url.rstrip("/")
    url = f"{root}/chat/completions"
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": user_payload
                + "\n\nRespond with JSON object keys: summary, bull_case, bear_case, risks, checklist.",
            },
        ],
    }
    # Cloud OpenAI supports response_format; many local servers do not — omit for local.
    if provider_label == "openai":
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key or LOCAL_KEY_SENTINEL}",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    try:
        text = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmAnalyzeError("Unexpected LLM response shape") from exc
    out = _normalize(_parse_json_content(text))
    out["provider"] = provider_label
    out["model"] = model
    if provider_label == "local":
        out["local_base_host"] = "loopback"
    return out


def _resolve_model(provider: str, model: Optional[str]) -> str:
    if provider == "local":
        from app.config import config

        default = config.local_llm_default_model or LOCAL_DEFAULT_MODEL
        if not model:
            return default
        m = str(model).strip()
        if m in ALLOWED_MODELS["local"]:
            return m
        if _LOCAL_MODEL_RE.match(m):
            return m
        raise LlmAnalyzeError(
            "local model id must be alphanumeric (and ._:/-), max 80 chars",
            status_code=422,
        )
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
    *,
    local_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Call OpenAI, Anthropic, or a loopback OpenAI-compatible local server.

    Never logs ``api_key``. Research commentary only — does not create/alter signals.
    """
    if not isinstance(signal, dict) or not signal:
        raise LlmAnalyzeError("signal must be a non-empty object", status_code=422)

    provider = (provider or "openai").lower().strip()
    if provider not in ("openai", "anthropic", "local"):
        raise LlmAnalyzeError(
            "provider must be openai, anthropic, or local",
            status_code=422,
        )

    key = (api_key or "").strip()
    if provider == "local":
        key = key or LOCAL_KEY_SENTINEL
    elif not key:
        raise LlmAnalyzeError("api_key is required", status_code=422)

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
        "instruction": (
            "Critique this research call; do not invent prices not in the payload. "
            "Disclose missing or stale inputs. Do not create or change BUY/SELL/HOLD."
        ),
    }
    user_payload = json.dumps(payload, ensure_ascii=False, default=str)[:12000]

    try:
        if provider == "openai":
            return _openai(key, user_payload, model=resolved_model)
        if provider == "anthropic":
            return _anthropic(key, user_payload, model=resolved_model)
        from app.config import config

        base = assert_loopback_base_url(
            local_base_url or config.local_llm_base_url
        )
        return _openai_compatible(
            key,
            user_payload,
            model=resolved_model,
            base_url=base,
            provider_label="local",
        )
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
        if provider == "local":
            raise LlmAnalyzeError(
                "Local LLM unreachable — is Ollama/LM Studio running on LOCAL_LLM_BASE_URL?",
                status_code=502,
            ) from exc
        raise LlmAnalyzeError("LLM request failed (network)", status_code=502) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM analyze failed: %s", type(exc).__name__)
        raise LlmAnalyzeError("LLM analyze failed", status_code=502) from exc
