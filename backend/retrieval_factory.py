"""Central selection for retrieval providers."""

import logging
import re

from backend.retrieval_provider import LocalChromaRetriever, RetrieverProtocol
from backend.settings import RetrievalSettings, get_retrieval_settings


logger = logging.getLogger(__name__)
_SAFE_PROVIDER = re.compile(r"^[a-z0-9_]{1,40}$")


def create_retrieval_provider(settings: RetrievalSettings | None = None) -> RetrieverProtocol | None:
    try:
        settings = settings or get_retrieval_settings()
    except Exception:
        logger.warning("Invalid retrieval provider configuration")
        return None
    provider = settings.provider
    if not isinstance(provider, str):
        logger.warning("Invalid retrieval provider configuration")
        return None
    normalized = provider.strip().lower()
    if normalized == "disabled":
        return None
    if normalized != "chroma_local":
        name = normalized if _SAFE_PROVIDER.fullmatch(normalized) else "invalid"
        logger.warning("Unsupported retrieval provider configuration; provider=%s", name)
        return None
    try:
        return LocalChromaRetriever()
    except Exception:
        logger.warning("Retrieval provider construction failed")
        return None


def from_environment() -> RetrieverProtocol | None:
    return create_retrieval_provider()
