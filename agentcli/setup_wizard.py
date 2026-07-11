"""First-run onboarding. Greets the user, lets them pick a provider (including
a fully custom endpoint), takes the key (hidden), fetches the provider's LIVE
model list so they can pick a current one, records that model's real token cap,
saves everything to ~/.agentcli/config.json, and pings to confirm it works.
"""
from __future__ import annotations

import getpass
import sys

from . import config
from .models import rank_latest, resolve_max_output
from .registry import PRESETS, build_provider
from .types import Message

DIM, CYAN, GRN, YEL, RST = "\033[2m", "\033[36m", "\033[32m", "\033[33m", "\033[0m"

_CLOUD = ["openrouter", "groq", "openai", "anthropic", "google",
          "deepseek", "mistral", "together", "xai", "fireworks", "perplexity"]
_LOCAL = ["ollama", "llamacpp", "lmstudio", "vllm"]

_HINTS = {
    "openrouter": "one key → hundreds of models. openrouter.ai/keys",
    "groq":       "very fast, generous free tier. console.groq.com/keys",
    "openai":     "platform.openai.com/api-keys",
    "anthropic":  "console.anthropic.com/settings/keys",
    "google":     "aistudio.google.com/apikey",
}


def _prompt_choice() -> str:
    print(f"\n{CYAN}which provider do you want to set up?{RST}")
    for i, pid in enumerate(_CLOUD, 1):
        hint = _HINTS.get(pid, "")
        print(f"  {i:>2}. {pid:11}{DIM}{('  — ' + hint) if hint else ''}{RST}")
    print(f"  {len(_CLOUD)+1:>2}. local model  {DIM}(ollama / lm-studio / etc — no key){RST}")
    print(f"  {len(_CLOUD)+2:>2}. custom       {DIM}(any OpenAI-compatible endpoint){RST}")

    while True:
        raw = input(f"{CYAN}pick a number (or type a name) › {RST}").strip()
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(_CLOUD):
                return _CLOUD[n - 1]
            if n == len(_CLOUD) + 1:
                return _pick_local()
            if n == len(_CLOUD) + 2:
                return "__custom__"
        elif raw in PRESETS:
            return raw
        elif raw == "custom":
            return "__custom__"
        print(f"{YEL}  enter 1-{len(_CLOUD)+2} or a provider name.{RST}")


def _pick_local() -> str:
    print(f"{DIM}  local runtimes: {', '.join(_LOCAL)}{RST}")
    while True:
        raw = input(f"{CYAN}  which one? › {RST}").strip() or "ollama"
        if raw in _LOCAL:
            return raw
        print(f"{YEL}  pick one of: {', '.join(_LOCAL)}{RST}")


def _choose_model(provider_id: str, key: str, preset_default: str) -> tuple[str, int]:
    """Fetch the live model list, let the user pick, return (model, max_tokens)."""
    print(f"{DIM}fetching {provider_id}'s current models…{RST}")
    discovered: list[dict] = []
    try:
        prov = build_provider(provider_id, preset_default, api_key=key)
        discovered = prov.list_models()
    except Exception as e:
        print(f"{YEL}  couldn't fetch the model list ({e}). "
              f"you can still type one.{RST}")

    ranked = rank_latest(discovered, limit=8)
    by_id = {m["id"]: m for m in discovered}

    if ranked:
        print(f"{CYAN}pick a model — latest available:{RST}")
        for i, m in enumerate(ranked, 1):
            cap = resolve_max_output(m["id"], m)
            ctx = f", {m['context']//1000}k ctx" if m.get("context") else ""
            print(f"  {i:>2}. {m['id']:42}{DIM}(out≈{cap}{ctx}){RST}")
        print(f"{DIM}  …or type any model id.{RST}")
        raw = input(f"{CYAN}number or model id "
                    f"{DIM}[enter for {ranked[0]['id']}]{RST}{CYAN} › {RST}").strip()
        if not raw:
            model = ranked[0]["id"]
        elif raw.isdigit() and 1 <= int(raw) <= len(ranked):
            model = ranked[int(raw) - 1]["id"]
        else:
            model = raw
    else:
        model = input(f"{CYAN}model? {RST}{DIM}[enter for {preset_default}] › {RST}"
                      ).strip() or preset_default

    max_tokens = resolve_max_output(model, by_id.get(model))
    print(f"{DIM}→ {model}  (defaulting max output to {max_tokens} tokens){RST}")
    return model, max_tokens


def _custom_flow() -> str:
    print(f"\n{CYAN}custom OpenAI-compatible endpoint{RST}")
    name = ""
    while not name:
        name = input(f"{CYAN}a short name for it (e.g. 'work', 'myproxy') › {RST}").strip()
    base_url = ""
    while not base_url:
        base_url = input(f"{CYAN}base URL (…/v1) › {RST}").strip()
    key = getpass.getpass(f"{CYAN}API key (blank if none) › {RST}").strip() or "not-needed"
    model = input(f"{CYAN}default model id › {RST}").strip() or "unknown"

    config.add_custom_provider(name, base_url, key, model)
    m, mx = _choose_model(name, key, model) if key != "not-needed" else (model, resolve_max_output(model))
    config.set_default(name, m, mx)
    _ping(name, m)
    print(f"\n{GRN}custom provider '{name}' saved.{RST}\n")
    return name


def _ping(provider_id: str, model: str | None) -> None:
    print(f"{DIM}testing the connection…{RST}")
    try:
        prov = build_provider(provider_id, model)
        c = prov.chat([Message("user", "reply with the single word: ok")],
                      tools=[], max_tokens=8)
        print(f"{GRN}✓ working — {provider_id}:{prov.model} said: "
              f"{c.text.strip()[:40]}{RST}")
    except Exception as e:
        print(f"{YEL}⚠ couldn't reach it: {e}{RST}")
        print(f"{DIM}  saved anyway — double-check the key or your network later.{RST}")


def run_setup(force: bool = False) -> str:
    print(f"{GRN}welcome to agentcli 👋{RST}")
    print(f"{DIM}let's get you a provider so you can start chatting.{RST}")

    provider_id = _prompt_choice()
    if provider_id == "__custom__":
        return _custom_flow()

    preset = PRESETS[provider_id]
    is_local = provider_id in _LOCAL
    key = "not-needed"

    if not is_local:
        print(f"\n{DIM}paste your {provider_id} key "
              f"(hidden as you type, saved to ~/.agentcli/config.json):{RST}")
        while True:
            key = getpass.getpass(f"{CYAN}{preset.env_key} › {RST}").strip()
            if key:
                break
            print(f"{YEL}  can't be empty — paste the key.{RST}")
        config.set_key(provider_id, key)

    model, max_tokens = _choose_model(provider_id, key, preset.default_model)
    config.set_default(provider_id, model, max_tokens)

    if not is_local:
        _ping(provider_id, model)
    print(f"\n{GRN}all set.{RST} {DIM}rerun anytime with `agentcli setup`.{RST}\n")
    return provider_id
