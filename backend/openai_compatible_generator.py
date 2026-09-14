"""Controlled OpenAI-compatible HTTP generation adapter."""

import logging
import re
import ipaddress
import unicodedata
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.generation import (
    GROQ_RESPONSE_SCHEMA,
    ProviderCompletionExhaustedError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from backend.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.settings import GenerationSettings

logger = logging.getLogger(__name__)
_PROVIDER_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_RETRY_AFTER = re.compile(r"^[0-9]+$")
_MAX_RETRY_AFTER_SECONDS = 86_400
_HOSTNAME = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\Z", re.IGNORECASE)


def _has_unsafe_character(value: str) -> bool:
    """Reject controls and Unicode whitespace/separators before URL parsing."""
    return any(unicodedata.category(char)[0] in {"C", "Z"} for char in value)


def _canonical_host(host: str) -> str | None:
    """Return a conservative ASCII host spelling, without DNS resolution."""
    if not host or _has_unsafe_character(host) or not host.isascii() or host.endswith("."):
        return None
    value = host.lower()
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        # Numeric, hexadecimal, and shortened IPv4 spellings are ambiguous.
        if value.startswith("0x") or re.fullmatch(r"[0-9a-fx.]+", value):
            return None
        return value if _HOSTNAME.fullmatch(value) else None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return None
    return str(address)


def _allowed_hosts(entries: Sequence[str]) -> set[str] | None:
    """Validate the administrator allowlist as host tokens, not URL fragments."""
    if not entries:
        return None
    normalized: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str) or "*" in entry:
            return None
        host = _canonical_host(entry)
        if host is None:
            return None
        normalized.add(host)
    return normalized or None


def validated_chat_endpoint(settings: GenerationSettings) -> str:
    if not settings.base_url or not settings.allowed_hosts:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    if _has_unsafe_character(settings.base_url) or "\\" in settings.base_url:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    allowed_hosts = _allowed_hosts(settings.allowed_hosts)
    if allowed_hosts is None:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    try:
        parsed = urlsplit(settings.base_url)
        port = parsed.port
        parsed_host = parsed.hostname
    except ValueError:
        raise ProviderUnavailableError("Configured LLM provider is unavailable") from None
    scheme = parsed.scheme.lower()
    # Reject percent-encoded authority delimiters and all userinfo forms, including
    # an empty username before a password delimiter.
    if not parsed.netloc or "@" in parsed.netloc or "%" in parsed.netloc:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    host = _canonical_host(parsed_host or "")
    if (
        host is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or scheme not in {"https", "http"}
    ):
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    if host not in allowed_hosts:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    if scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    if port is not None and not 1 <= port <= 65535:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    path = parsed.path
    if "%" in path or "\\" in path:
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    path = path.rstrip("/")
    if not path or path == "/":
        path = ""
    if "//" in path or any(segment in {".", ".."} for segment in path.split("/")) or path.endswith("/chat/completions"):
        raise ProviderUnavailableError("Configured LLM provider is unavailable")
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority = f"{authority}:{port}"
    return urlunsplit((scheme, authority, f"{path}/chat/completions", "", ""))


class OpenAICompatibleGenerator:
    def __init__(self, settings: GenerationSettings, client: httpx.Client | None = None):
        if settings.provider != "openai_compatible" or not settings.model or len(settings.model) > 200 or any(ord(c) < 32 for c in settings.model):
            raise ProviderUnavailableError("Configured LLM provider is unavailable")
        if settings.structured_output_mode not in {"json_schema", "json_object"}:
            raise ProviderUnavailableError("Configured LLM provider is unavailable")
        self._settings = settings
        self._endpoint = validated_chat_endpoint(settings)
        self._client = client or httpx.Client(timeout=settings.timeout_seconds, follow_redirects=False)

    @property
    def model(self) -> str:
        return self._settings.model

    def generate(self, question: str, evidence: Sequence[Mapping[str, object]], *, repair: bool = False, concise: bool = False, repair_feedback: str | None = None) -> str:
        response_format: dict[str, object]
        if self._settings.structured_output_mode == "json_schema":
            response_format = {"type": "json_schema", "json_schema": {"name": "grounded_bis_answer", "strict": True, "schema": GROQ_RESPONSE_SCHEMA}}
        else:
            response_format = {"type": "json_object"}
        payload = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(question, evidence, repair=repair, concise=concise, repair_feedback=repair_feedback)}], "temperature": 0, "max_completion_tokens": self._settings.max_completion_tokens, "response_format": response_format, "stream": False}
        headers = {"Content-Type": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        try:
            response = self._client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException:
            self._log_provider_failure("timeout")
            raise ProviderTimeoutError("Generation provider timed out") from None
        except httpx.RequestError:
            self._log_provider_failure("request_error")
            raise ProviderUnavailableError("Generation provider is unavailable") from None
        except Exception:
            self._log_provider_failure("unexpected_client_exception")
            raise ProviderResponseError("Unexpected generation provider failure") from None
        self._raise_for_status(response)
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            choices = payload["choices"]
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise TypeError
            choice = choices[0]
            if choice.get("finish_reason") == "length":
                raise ProviderCompletionExhaustedError("Generation provider exhausted completion tokens")
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError
            content = message["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            self._log_provider_failure("malformed_response", response)
            raise ProviderResponseError("Generation provider returned invalid output") from None
        if (
            message.get("refusal") is not None
            or message.get("tool_calls") is not None
            or message.get("function_call") is not None
        ):
            self._log_provider_failure("invalid_response_shape", response)
            raise ProviderResponseError("Generation provider returned invalid output")
        if not isinstance(content, str) or not content.strip():
            self._log_provider_failure("invalid_response_shape", response)
            raise ProviderResponseError("Generation provider returned invalid output")
        return content

    @staticmethod
    def _provider_request_id(response: httpx.Response | None) -> str | None:
        """Return a single conservative diagnostic ID from approved headers."""
        if response is None:
            return None
        values: list[str] = []
        for name in ("x-request-id", "request-id"):
            header_values = response.headers.get_list(name)
            if len(header_values) > 1:
                return None
            if header_values:
                values.append(header_values[0])
        if not values or len(set(values)) != 1:
            return None
        value = values[0]
        return value if value.isascii() and _PROVIDER_REQUEST_ID.fullmatch(value) else None

    @classmethod
    def _log_provider_failure(cls, event: str, response: httpx.Response | None = None) -> None:
        """Log only fixed event names, numeric status, and a validated ID."""
        status = response.status_code if response is not None else None
        logger.warning(
            "OpenAI-compatible provider failure; event=%s status_code=%s request_id=%s",
            event,
            status,
            cls._provider_request_id(response),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if 300 <= response.status_code < 400:
            OpenAICompatibleGenerator._log_provider_failure("redirect", response)
            raise ProviderResponseError("Generation provider rejected the request")
        if response.status_code < 400:
            return
        OpenAICompatibleGenerator._log_provider_failure("http_status", response)
        if response.status_code in {401, 403} or response.status_code >= 500:
            raise ProviderUnavailableError("Generation provider is unavailable")
        if response.status_code == 429:
            raise ProviderRateLimitError(OpenAICompatibleGenerator._retry_after(response))
        if response.status_code == 400:
            try:
                payload = response.json()
                choices = payload.get("choices") if isinstance(payload, dict) else None
                choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
                if choice and choice.get("finish_reason") in {"length", "max_tokens"}:
                    raise ProviderCompletionExhaustedError("Generation provider exhausted completion tokens")
            except (ValueError, TypeError, IndexError):
                pass
        raise ProviderResponseError("Generation provider rejected the request")

    @staticmethod
    def _retry_after(response: httpx.Response) -> str | None:
        values = response.headers.get_list("Retry-After")
        if len(values) != 1 or not _RETRY_AFTER.fullmatch(values[0]):
            return None
        seconds = int(values[0])
        return values[0] if seconds <= _MAX_RETRY_AFTER_SECONDS else None
