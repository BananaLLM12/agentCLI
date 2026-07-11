"""agentcli — a tiny multi-provider agentic LLM CLI."""
from .agent import Agent
from .registry import PRESETS, build_provider

__version__ = "1.0.0b1"          # BETA — early software, expect rough edges
__status__ = "beta"
__all__ = ["Agent", "build_provider", "PRESETS"]
