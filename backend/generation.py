"""Generation-provider protocol and Groq implementation."""

from collections.abc import Mapping, Sequence
import logging
import re
from typing import Any, Protocol

from backend.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.settings import GenerationSettings, get_generation_settings


logger = logging.getLogger(__name__)

# This intentionally does not use Pydantic's JSON schema. Groq strict structured
# output accepts a deliberately small, closed schema; Python validates all richer
# constraints after receiving the response.
GROQ_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "insufficient_evidence": {"type": "boolean"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "citation_id": {"type": "string"},
                    "supporting_quote": {"type": "string"},
                },
                "required": ["citation_id", "supporting_quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "insufficient_evidence", "citations"],
    "additionalProperties": False,
}


class GenerationError(Exception):
    """Base class for safely mapped provider failures."""


class ProviderUnavailableError(GenerationError):
    pass


class ProviderTimeoutError(GenerationError):
    pass


class ProviderRateLimitError(GenerationError):
    def __init__(self, retry_after: str | None = None):
        super().__init__("Generation provider rate limit reached")
        self.retry_after = retry_after


class ProviderResponseError(GenerationError):
    pass


class ProviderCompletionExhaustedError(ProviderResponseError):
    """A single concise retry may be attempted by ChatService."""


class MalformedGenerationError(GenerationError):
    pass


class GenerationProvider(Protocol):
    @property
    def model(self) -> str: ...

    def generate(
        self,
        question: str,
        evidence: Sequence[Mapping[str, object]],
        *,
        repair: bool = False,
        concise: bool = False,
        repair_feedback: str | None = None,
    ) -> str: ...


class GroqGenerator:
    def __init__(self, settings: GenerationSettings, client: Any | None = None):
        if settings.provider != "groq":
            raise ProviderUnavailableError("Configured LLM provider is unavailable")
        if not settings.api_key:
            raise ProviderUnavailableError("Groq API key is not configured")

        if client is None:
            from groq import Groq

            client = Groq(api_key=settings.api_key, timeout=settings.timeout_seconds)
        self._client = client
        self._settings = settings

    @classmethod
    def from_environment(cls) -> "GroqGenerator":
        return cls(get_generation_settings())

    @property
    def model(self) -> str:
        return self._settings.model

    def generate(
        self,
        question: str,
        evidence: Sequence[Mapping[str, object]],
        *,
        repair: bool = False,
        concise: bool = False,
        repair_feedback: str | None = None,
    ) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            question,
                            evidence,
                            repair=repair,
                            concise=concise,
                            repair_feedback=repair_feedback,
                        ),
                    },
                ],
                temperature=0,
                max_completion_tokens=self._settings.max_completion_tokens,
                reasoning_effort="low",
                include_reasoning=False,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "grounded_bis_answer",
                        "strict": True,
                        "schema": GROQ_RESPONSE_SCHEMA,
                    },
                },
                tool_choice="none",
            )
        except Exception as exc:
            self._raise_safe_error(exc)

        if not completion.choices:
            raise ProviderResponseError("Generation provider returned no choices")
        return completion.choices[0].message.content or ""

    @staticmethod
    def _sanitized_provider_message(exc: Exception) -> str:
        """Keep diagnosis useful without persisting credentials or provider bodies."""
        # SDK messages occasionally append request context after a semicolon. Keep
        # only the diagnostic lead-in so a malformed upstream echo cannot leak a
        # prompt or retrieved passage to logs.
        message = " ".join(str(exc).split()).split(";", 1)[0]
        message = re.split(r"(?i)\bfailed_generation\b", message, maxsplit=1)[0].rstrip(" :")
        message = re.sub(r"(?i)(authorization\s*[:=]\s*)(\S+)", r"\1[REDACTED]", message)
        message = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", message)
        message = re.sub(r"gsk_[A-Za-z0-9_-]+", "[REDACTED]", message)
        return message[:300]

    @classmethod
    def _log_provider_diagnostic(cls, exc: Exception) -> None:
        response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        body = getattr(exc, "body", None)
        error = body.get("error", {}) if isinstance(body, dict) else {}
        error_type = error.get("type") if isinstance(error, dict) else None
        error_code = error.get("code") if isinstance(error, dict) else None
        headers = getattr(response, "headers", {}) if response is not None else {}
        request_id = headers.get("x-request-id") or headers.get("request-id")
        logger.warning(
            "Groq provider failure; exception_class=%s status_code=%s error_type=%s "
            "error_code=%s request_id=%s message=%s",
            type(exc).__name__, status, error_type, error_code, request_id,
            cls._sanitized_provider_message(exc),
        )

    @classmethod
    def _raise_safe_error(cls, exc: Exception) -> None:
        from groq import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            InternalServerError,
            PermissionDeniedError,
            RateLimitError,
        )

        cls._log_provider_diagnostic(exc)
        if isinstance(exc, APITimeoutError):
            raise ProviderTimeoutError("Generation provider timed out") from None
        if isinstance(exc, RateLimitError):
            retry_after = exc.response.headers.get("Retry-After")
            raise ProviderRateLimitError(retry_after) from None
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            raise ProviderUnavailableError("Generation provider authentication failed") from None
        if isinstance(exc, (APIConnectionError, InternalServerError)):
            raise ProviderUnavailableError("Generation provider is unavailable") from None
        if isinstance(exc, BadRequestError):
            if cls._is_completion_exhaustion(exc):
                raise ProviderCompletionExhaustedError(
                    "Generation provider exhausted completion tokens"
                ) from None
            raise ProviderResponseError("Generation provider rejected the request") from None
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            if isinstance(status, int) and status >= 500:
                raise ProviderUnavailableError("Generation provider is unavailable") from None
            raise ProviderResponseError("Generation provider request failed") from None
        raise ProviderResponseError("Unexpected generation provider failure") from None

    @staticmethod
    def _is_completion_exhaustion(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        body = getattr(exc, "body", None)
        error = body.get("error", {}) if isinstance(body, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        message = str(exc).lower()
        return (
            status == 400
            and code == "json_validate_failed"
            and "max completion tokens" in message
            and "valid document" in message
        )
