"""agentcli — a tiny multi-provider agentic LLM CLI."""
from .agent import Agent
from .registry import PRESETS, build_provider

__version__ = "1.0.0"
__all__ = ["Agent", "build_provider", "PRESETS"]
