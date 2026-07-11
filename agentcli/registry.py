"""Maps a short provider id to a concrete adapter + connection details.

Adding a new OpenAI-compatible service is a one-line entry here.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .providers.anthropic import AnthropicProvider
from .providers.base import Provider
from .providers.google import GoogleProvider
from .providers.openai_compat import OpenAICompatProvider


@dataclass
class Preset:
    adapter: type[Provider]
    base_url: str | None
    env_key: str          # env var to read the API key from
    default_model: str


# Everything that speaks chat-completions rides OpenAICompatProvider and only
# differs by base_url. Official SDKs (Anthropic, Google) get their own adapter.
PRESETS: dict[str, Preset] = {
    # --- official ---
    "openai":     Preset(OpenAICompatProvider, None, "OPENAI_API_KEY", "gpt-4o-mini"),
    "anthropic":  Preset(AnthropicProvider, None, "ANTHROPIC_API_KEY", "claude-3-5-sonnet-latest"),
    "google":     Preset(GoogleProvider, None, "GEMINI_API_KEY", "gemini-1.5-flash"),

    # --- third-party, OpenAI-compatible ---
    "openrouter": Preset(OpenAICompatProvider, "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai/gpt-4o-mini"),
    "groq":       Preset(OpenAICompatProvider, "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "together":   Preset(OpenAICompatProvider, "https://api.together.xyz/v1", "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "deepseek":   Preset(OpenAICompatProvider, "https://api.deepseek.com", "DEEPSEEK_API_KEY", "deepseek-chat"),
    "mistral":    Preset(OpenAICompatProvider, "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest"),
    "xai":        Preset(OpenAICompatProvider, "https://api.x.ai/v1", "XAI_API_KEY", "grok-2-latest"),
    "fireworks":  Preset(OpenAICompatProvider, "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
    "perplexity": Preset(OpenAICompatProvider, "https://api.perplexity.ai", "PERPLEXITY_API_KEY", "sonar"),

    # --- local, no key needed ---
    "ollama":     Preset(OpenAICompatProvider, "http://localhost:11434/v1", "OLLAMA_API_KEY", "llama3.1"),
    "llamacpp":   Preset(OpenAICompatProvider, "http://localhost:8080/v1", "LLAMACPP_API_KEY", "local-model"),
    "lmstudio":   Preset(OpenAICompatProvider, "http://localhost:1234/v1", "LMSTUDIO_API_KEY", "local-model"),
    "vllm":       Preset(OpenAICompatProvider, "http://localhost:8000/v1", "VLLM_API_KEY", "local-model"),
}


def build_provider(provider_id: str, model: str | None = None,
                   base_url: str | None = None, api_key: str | None = None) -> Provider:
    """Instantiate a provider. Explicit args always win over the preset.

    A completely unknown id is treated as a raw OpenAI-compatible endpoint,
    so you can point at anything without editing this file — just pass
    --base-url and --api-key.
    """
    preset = PRESETS.get(provider_id)
    if preset is None:
        # a user-defined custom provider saved during setup?
        custom = config.custom_providers().get(provider_id)
        if custom and not base_url:
            key = api_key or config.get_key(provider_id, "") or ""
            return OpenAICompatProvider(model=model or custom.get("model", "unknown"),
                                        api_key=key, base_url=custom["base_url"])
        if not base_url:
            raise ValueError(
                f"unknown provider '{provider_id}'. either add a preset or "
                f"pass --base-url for a raw OpenAI-compatible endpoint.")
        return OpenAICompatProvider(model=model or "unknown",
                                    api_key=api_key or "", base_url=base_url)

    # precedence: explicit arg > env var > saved config file
    key = api_key or config.get_key(provider_id, preset.env_key)
    # local runtimes usually accept any/empty key
    if not key and preset.base_url and "localhost" in preset.base_url:
        key = "not-needed"
    if not key:
        raise ValueError(f"no API key. set ${preset.env_key} or pass --api-key.")

    extra: dict[str, str] = {}
    if provider_id == "openrouter":
        # optional but nice: shows up on your openrouter dashboard
        extra = {"HTTP-Referer": "https://localhost/agentcli", "X-Title": "agentcli"}

    return preset.adapter(
        model=model or preset.default_model,
        api_key=key,
        base_url=base_url or preset.base_url,
        extra_headers=extra,
    )
