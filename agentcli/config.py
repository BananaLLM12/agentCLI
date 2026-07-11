"""Persistent config at ~/.agentcli/config.json.

Stores saved API keys + your default provider/model so you set things up
once and never touch an env var again. Key resolution order everywhere:
    explicit CLI arg  >  environment variable  >  this config file
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("AGENTCLI_HOME", Path.home() / ".agentcli"))
CONFIG_PATH = CONFIG_DIR / "config.json"


def load() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), "utf-8")
    try:  # keys live here — keep it owner-only
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def _secure_on() -> bool:
    from . import secure_store
    return bool(load().get("secure_keys")) and secure_store.available()


def get_key(provider_id: str, env_var: str) -> str | None:
    """Resolution: env var > OS keychain (if enabled) > config file."""
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    if _secure_on():
        from . import secure_store
        k = secure_store.get_key(provider_id)
        if k:
            return k
    return load().get("keys", {}).get(provider_id)


def set_key(provider_id: str, key: str) -> None:
    if _secure_on():
        from . import secure_store
        if secure_store.set_key(provider_id, key):
            # keep a marker but NOT the secret in the plaintext file
            cfg = load()
            cfg.setdefault("keys", {})[provider_id] = "<in keychain>"
            save(cfg)
            return
    cfg = load()
    cfg.setdefault("keys", {})[provider_id] = key
    save(cfg)


def set_default(provider_id: str, model: str | None,
                max_tokens: int | None = None) -> None:
    cfg = load()
    cfg["default_provider"] = provider_id
    if model:
        cfg["default_model"] = model
    if max_tokens:
        cfg["default_max_tokens"] = max_tokens
    save(cfg)


def add_custom_provider(name: str, base_url: str, api_key: str,
                        model: str) -> None:
    """Persist a user-defined OpenAI-compatible endpoint."""
    cfg = load()
    cfg.setdefault("custom_providers", {})[name] = {
        "base_url": base_url, "model": model,
    }
    cfg.setdefault("keys", {})[name] = api_key
    save(cfg)


def custom_providers() -> dict[str, Any]:
    return load().get("custom_providers", {})


# -- generic settings --------------------------------------------------
_COERCE = {"true": True, "false": False, "none": None}


def set_value(key: str, raw: str) -> Any:
    """Set an arbitrary top-level config key, coercing obvious types."""
    val: Any = raw
    if raw.lower() in _COERCE:
        val = _COERCE[raw.lower()]
    elif raw.lstrip("-").isdigit():
        val = int(raw)
    cfg = load()
    cfg[key] = val
    save(cfg)
    return val


# -- personas ----------------------------------------------------------
def save_persona(name: str, text: str) -> None:
    cfg = load()
    cfg.setdefault("personas", {})[name] = text
    save(cfg)


def personas() -> dict[str, str]:
    return load().get("personas", {})


def delete_persona(name: str) -> bool:
    cfg = load()
    if name in cfg.get("personas", {}):
        del cfg["personas"][name]
        save(cfg)
        return True
    return False


def is_configured() -> bool:
    cfg = load()
    return bool(cfg.get("keys")) or bool(cfg.get("default_provider"))
