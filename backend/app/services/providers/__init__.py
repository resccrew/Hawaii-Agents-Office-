from app.services.providers.base import ConversationalProvider, GenerativeProvider
from app.services.providers.claude_provider import ClaudeProvider
from app.services.providers.nanobanana_provider import NanoBananaProvider

CONVERSATIONAL_PROVIDERS: dict[str, ConversationalProvider] = {
    "claude": ClaudeProvider(),
}

GENERATIVE_PROVIDERS: dict[str, GenerativeProvider] = {
    "nanobanana": NanoBananaProvider(),
}


def get_conversational_provider(name: str) -> ConversationalProvider | None:
    return CONVERSATIONAL_PROVIDERS.get(name)


def get_generative_provider(name: str) -> GenerativeProvider | None:
    return GENERATIVE_PROVIDERS.get(name)
