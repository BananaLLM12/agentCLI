# agentcli

A multi-provider **agentic LLM CLI** that lives in your terminal — real tools, a
permission system, a layered security guard, and a proper TUI. **Zero third-party
dependencies** (pure Python standard library).

```
  ◈  a g e n t c l i
     ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔
     multi-provider terminal agent
```

## Install (one command)

```bash
pipx install git+https://github.com/USER/agentcli.git
```

or with pip:

```bash
pip install git+https://github.com/USER/agentcli.git
```

Then run:

```bash
agentcli          # first run walks you through picking a provider + key
```

> Requires Python 3.9+. No API key baked in — you supply your own at setup.

## What it does

- **Any provider** — OpenAI, Anthropic, Google, plus every OpenAI-compatible
  service (OpenRouter, Groq, Together, DeepSeek, Mistral, xAI, Fireworks,
  Perplexity) and local runtimes (Ollama, llama.cpp, LM Studio, vLLM). Point it
  at anything with `--base-url`.
- **29 built-in tools** — shell (foreground + background jobs), full filesystem
  (read/write/edit/search/move/delete), web (`http_get`, Tavily `web_search`),
  sub-agents, plans, notifications.
- **Permission modes** — `read-only` · `approve` (asks first) · `auto`, with
  path/network/shell restrictions.
- **Layered security** — an injection guard (scans untrusted input *and* tool
  output), an intent flagger (scans the model's own commands/code), a policy
  file, and a low-power refusal mode. Each catches a different attack surface.
- **A real TUI** — gradient logo, live status bar, command palette (`/`),
  interactive pickers, markdown rendering, mode-colored prompt.
- **Modes** — plan mode (draft steps → approve → execute), education mode
  (interactive tutoring + quizzes), personas, side threads, context compaction.

## Quick start

```bash
agentcli                                   # interactive, safe "approve" mode
agentcli --provider groq --stream          # streaming REPL on Groq
agentcli --mode auto -p "run the tests"    # one-shot, full-auto
agentcli --mode read-only                  # planning only, can't mutate
```

Type `/` in the REPL for the command palette. Key commands: `/status`, `/model`,
`/mode`, `/plan`, `/learn <subject>`, `/persona`, `/thread`, `/resume`,
`/policy`, `/integrity`.

## Security & the policy file

The operating policy lives at `~/.agentcli/policy.json` — a reviewable set of
rules injected into the model's prompt *and* enforced by the harness. Lock it
for distribution:

```
# in the REPL
/policy lock        # permanent for this install (undo by editing the file)
```

Once locked, runtime tweaks (`/mode`, `/set`, `/settings`, `/persona`) are
refused, and a **source-tampering** check runs at launch: if a security-critical
file has been modified, a locked build **refuses to run** (`/integrity` shows
status). See `agentcli/integrity.py` for the honest scope of this guarantee.

## Config

Everything lives under `~/.agentcli/`:

- `config.json` — provider defaults + keys (`0600`; or store keys in the OS
  keychain with `/securekeys on`)
- `policy.json` — the operating policy
- `threads/*.jsonl` — one file per conversation

## Development

```bash
git clone https://github.com/USER/agentcli.git
cd agentcli
python3 -m agentcli --help

# after changing source, regenerate the integrity manifest:
python3 scripts/build_manifest.py
```

## License

MIT — see [LICENSE](LICENSE).
