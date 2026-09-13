"""Configuration for the retrieval and grounded-chat API."""

from dataclasses import dataclass
import os
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


def get_generation_settings() -> GenerationSettings:
    provider = os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()
    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    timeout_seconds = float(
        os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS))
    )
    raw_completion_tokens = os.getenv(
        "GROQ_MAX_COMPLETION_TOKENS", str(DEFAULT_GROQ_MAX_COMPLETION_TOKENS)
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
        api_key=os.getenv("GROQ_API_KEY") or None,
        model=model,
        timeout_seconds=timeout_seconds,
        max_completion_tokens=max_completion_tokens,
    )
