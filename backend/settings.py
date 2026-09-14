"""Configuration for the retrieval and grounded-chat API."""

from dataclasses import dataclass
import os
import re
import unicodedata
from urllib.parse import urlsplit

SERVICE_NAME = "bis-toys-retrieval-api"

ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

ALLOWED_METHODS = ("GET", "POST")
ALLOWED_HEADERS = ("Content-Type", "X-Request-ID")
EXPOSED_HEADERS = ("X-Request-ID",)


def get_allowed_origins() -> tuple[str, ...]:
    """Return explicit CORS origins from the environment or safe local defaults."""
    raw_origins = os.getenv("ALLOWED_ORIGINS")
    if raw_origins is None or not raw_origins.strip():
        return ALLOWED_ORIGINS

    valid: list[str] = []
    for candidate in raw_origins.split(","):
        origin = candidate.strip().rstrip("/")
        if not origin or "*" in origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            continue
        if origin not in valid:
            valid.append(origin)
    return tuple(valid) if valid else ALLOWED_ORIGINS

DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
DEFAULT_GROQ_MAX_COMPLETION_TOKENS = 2048
MIN_GROQ_MAX_COMPLETION_TOKENS = 256
MAX_GROQ_MAX_COMPLETION_TOKENS = 4096

LEGAL_INFORMATION_DISCLAIMER = (
    "Informational guidance based on the indexed BIS documents. "
    "Verify requirements with BIS or a qualified professional."
)
INSUFFICIENT_EVIDENCE_ANSWER = (
    "The retrieved evidence is insufficient to answer this question reliably. "
    "Please verify the requirement with BIS or a qualified professional."
)


@dataclass(frozen=True)
class GenerationSettings:
    provider: str
    api_key: str | None
    model: str
    timeout_seconds: float
    max_completion_tokens: int
    base_url: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    structured_output_mode: str = "json_schema"


def get_generation_settings() -> GenerationSettings:
    provider = os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()
    if provider == "openai_compatible":
        model = os.getenv("LLM_MODEL", "").strip()
        api_key = os.getenv("LLM_API_KEY") or None
        raw_completion_tokens = os.getenv("LLM_MAX_COMPLETION_TOKENS", str(DEFAULT_GROQ_MAX_COMPLETION_TOKENS))
        # Preserve the configured spelling so the gateway can reject leading or
        # trailing whitespace instead of normalizing an ambiguous URL into one.
        base_url = os.getenv("LLM_BASE_URL", "") or None
        structured_output_mode = os.getenv("LLM_STRUCTURED_OUTPUT_MODE", "json_schema").strip().lower()
        allowed_hosts = _get_allowed_model_hosts(os.getenv("LLM_ALLOWED_HOSTS", ""))
    else:
        model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
        api_key = os.getenv("GROQ_API_KEY") or None
        raw_completion_tokens = os.getenv("GROQ_MAX_COMPLETION_TOKENS", str(DEFAULT_GROQ_MAX_COMPLETION_TOKENS))
        base_url = None
        structured_output_mode = "json_schema"
        allowed_hosts = ()
    timeout_seconds = float(
        os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS))
    )
    if timeout_seconds <= 0:
        raise ValueError("LLM timeout must be positive")
    try:
        max_completion_tokens = int(raw_completion_tokens)
    except ValueError:
        max_completion_tokens = DEFAULT_GROQ_MAX_COMPLETION_TOKENS
    if not MIN_GROQ_MAX_COMPLETION_TOKENS <= max_completion_tokens <= MAX_GROQ_MAX_COMPLETION_TOKENS:
        max_completion_tokens = DEFAULT_GROQ_MAX_COMPLETION_TOKENS
    return GenerationSettings(
        provider=provider,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_completion_tokens=max_completion_tokens,
        base_url=base_url,
        allowed_hosts=allowed_hosts,
        structured_output_mode=structured_output_mode,
    )


def _get_allowed_model_hosts(raw_hosts: str) -> tuple[str, ...]:
    hosts: list[str] = []
    for raw in raw_hosts.split(","):
        host = raw.strip().lower()
        # Spaces around comma-separated tokens are harmless normalization; all
        # other URL syntax is rejected here and revalidated by the gateway.
        if (
            not host
            or "*" in host
            or host.endswith(".")
            or not host.isascii()
            or any(unicodedata.category(char)[0] in {"C", "Z"} for char in host)
            or any(char in host for char in "/?#@[]")
            or "://" in host
            or not re.fullmatch(r"[a-z0-9][a-z0-9.:-]*", host)
        ):
            continue
        if host not in hosts:
            hosts.append(host)
    return tuple(hosts)
