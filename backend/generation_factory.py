"""Central provider selection; unsupported configuration is non-fatal to retrieval."""
import logging
import re
from backend.generation import GenerationProvider, GroqGenerator, ProviderUnavailableError
from backend.openai_compatible_generator import OpenAICompatibleGenerator
from backend.settings import GenerationSettings, get_generation_settings

logger = logging.getLogger(__name__)

def create_generation_provider(settings: GenerationSettings | None = None) -> GenerationProvider | None:
    try:
        settings = settings or get_generation_settings()
    except Exception:
        logger.warning("Invalid generation provider configuration")
        return None
    if settings.provider == "disabled":
        return None
    if (
        not isinstance(settings.model, str)
        or not settings.model
        or len(settings.model) > 200
        or any(ord(character) < 32 for character in settings.model)
    ):
        logger.warning("Invalid generation provider model configuration")
        return None
    try:
        if settings.provider == "groq":
            return GroqGenerator(settings)
        if settings.provider == "openai_compatible":
            return OpenAICompatibleGenerator(settings)
    except Exception:
        logger.warning("Generation provider construction failed")
        return None
    name = settings.provider if isinstance(settings.provider, str) and re.fullmatch(r"[a-z0-9_-]{1,40}", settings.provider) else "invalid"
    logger.warning("Unsupported generation provider configuration; provider=%s", name)
    return None

def from_environment() -> GenerationProvider:
    provider = create_generation_provider()
    if provider is None:
        raise ProviderUnavailableError("Chat generation is unavailable")
    return provider
