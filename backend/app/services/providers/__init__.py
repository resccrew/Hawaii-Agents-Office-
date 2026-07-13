from app.services.providers.base import ConversationalProvider, GenerativeProvider
from app.services.providers.claude_provider import ClaudeProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.nanobanana_provider import NanoBananaProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.providers.openai_provider import OpenAIProvider

CONVERSATIONAL_PROVIDERS: dict[str, ConversationalProvider] = {
    "claude": ClaudeProvider(),
    "openai": OpenAIProvider(),
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
}

GENERATIVE_PROVIDERS: dict[str, GenerativeProvider] = {
    "nanobanana": NanoBananaProvider(),
}


def get_conversational_provider(name: str) -> ConversationalProvider | None:
    return CONVERSATIONAL_PROVIDERS.get(name)


def get_generative_provider(name: str) -> GenerativeProvider | None:
    return GENERATIVE_PROVIDERS.get(name)
