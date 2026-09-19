from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.bedrock_provider import BedrockProvider
from app.llm.groq_provider import GroqProvider
from app.llm.mistral_provider import MistralProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    match settings.llm_provider:
        case "groq":
            return GroqProvider(api_key=settings.groq_api_key)
        case "mistral":
            return MistralProvider(api_key=settings.mistral_api_key)
        case "anthropic":
            return AnthropicProvider(api_key=settings.anthropic_api_key)
        case "bedrock":
            return BedrockProvider()
        case _:
            raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
