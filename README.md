# 9railway

**Auto-deploy and manage 9Router — the self-hosted AI gateway — on Railway, from your terminal or browser.**

Deploy a fleet of 9Router services, configure each one automatically (model → combo → API key), keep their credentials in one place, and tear them down when you're done. One tool, three interfaces.

---

## Why this exists

Manually deploying 9Router on Railway means clicking through the same flow every time:
create project → deploy template → set password → open dashboard → add model → build combo → create API key.

This tool automates the whole loop and **persists everything** — service URLs, API keys, combos — in a single `state.json`.

---

## Features

- 🚀 **One-command deploy** — `up N` creates the project if needed, deploys N services in parallel, and auto-configures each one
- 🔑 **Auto API keys** — every service gets a ready-to-use `sk-...` key, saved to `state.json`
- 🧩 **Combos included** — the model (e.g. `oc/deepseek-v4-flash-free`) is wired into a combo (e.g. `claude-opus-5`) automatically
- 💾 **Volume persistence** — the SQLite database lives on a Railway volume, so data survives redeploys
- 🧹 **Full lifecycle** — list, test, delete one/all, clean stuck volumes, or nuke the whole project
- 🖥️ **Three interfaces** — CLI, interactive terminal menu (TUI), and a local web dashboard
- 🐍 **Cross-platform** — pure Python 3.8+ (no bash, no external deps), works on Windows / Linux / macOS

---

## Prerequisites

- **Python 3.10+** (developed and tested on 3.14) — the tool uses **only the standard library**, so `pip install` is not needed. See [`requirements.txt`](requirements.txt) for the explicit marker.
- **Railway CLI** — `npm i -g @railway/cli`, then `railway login` once.

```bash
python --version   # >= 3.10
railway --version  # works
```

## Quick start

```bash
# 1. One-time setup
railway login                         # Railway account
python 9router.py help                # see all commands

# 2. Deploy 2 services (auto-configured)
python 9router.py up 2

# 3. See what you got
python 9router.py list
python 9router.py keys

# 4. Use the endpoint anywhere (OpenAI-compatible)
#    Base URL : https://<service>.up.railway.app/v1
#    API key  : sk-...
#    Model    : claude-opus-5
```

---

## Interfaces

### 1. CLI — `python 9router.py <command>`

| Command | What it does |
|---|---|
| `up [N]` | Deploy N new services (default 1), auto-configure each, save to state |
| `sync` | Re-configure existing services in the project (no new deploy) |
| `list` | Show saved services (URL + API key + combo + model) |
| `keys` | Show only API keys |
| `status` | Live Railway status (services, volumes) |
| `test [name]` | Send a real request to a service and verify it replies |
| `down [name\|all]` | Delete one service or all of them (+ detached volumes) |
| `nuke` | Delete the **entire** project — fixes stuck volumes / quota issues |
| `clean` | Delete detached volumes |
| `setpass <new>` | Change the default dashboard password |
| `config` | Show current settings |
| `token` | Show token status + refresh instructions |
| `reset` | Clear `state.json` (services are NOT touched) |
| `help` | Show help |

### 2. TUI — `python 9router-tui.py`

Interactive numbered menu (0–13). Same commands, guided flow, confirmation prompts for destructive actions. No extra dependencies.

### 3. Web — `python 9router-web.py`

Local dashboard at **http://localhost:8989** — dark theme, service cards with copy-able keys, one-click deploy/test/delete/nuke, live output console. Pure stdlib (`http.server`), no deps.

---

## Configuration

**`settings.json`** — created automatically on first run:

```json
{
  "default_password": "MyPassword123456",
  "combo_name": "claude-opus-5",
  "model_id": "oc/deepseek-v4-flash-free"
}
```

- `default_password` — dashboard login password for new services (change with `setpass`)
- `combo_name` — the combo created on each service
- `model_id` — the model wired into that combo (`<provider-alias>/<model-id>`)

**`state.json`** — the source of truth (NOT committed to git):

```json
{
  "services": [
    {
      "service": "9router-abc1",
      "url": "https://9router-abc1-production.up.railway.app",
      "api_key": "sk-...",
      "combo": "claude-opus-5",
      "model": "oc/deepseek-v4-flash-free",
      "created": "2026-08-04T18:01:53Z",
      "project_id": "..."
    }
  ]
}
```

---

## How the auto-configuration works

For each deployed service the tool:

1. Deploys the Railway template `9router` with `INITIAL_PASSWORD` + `DATA_DIR=/app/data`
2. Waits for the service to come online (health check)
3. Logs in to the dashboard → captures the session cookie
4. Adds the custom model (`POST /api/models/custom`)
5. Creates the combo (`POST /api/combos`)
6. Creates an API key (`POST /api/keys`)
7. Saves URL + key + combo to `state.json`

All verified end-to-end against live services (`cost: 0` replies).

---

## Notes & troubleshooting

### Token
- Auth uses the Railway access token from `.railway-token`, or falls back to `~/.railway/config.json` (written by `railway login`).
- When the token expires (`Unauthorized` errors), refresh it:
  ```bash
  railway login
  python -c "import json,pathlib; print(json.load(open(str(pathlib.Path.home()/'.railway'/'config.json')))['user']['accessToken'])" > .railway-token
  ```

### Volume limits (free plan)
- Railway free plan allows **3 volumes per project**. After repeated deploy/delete cycles, detached volumes can linger and block new deploys.
- Fix: `python 9router.py clean` (deletes detached volumes) or `python 9router.py nuke` (deletes the whole project — everything is recreated on next `up`).

### Reasoning models
- `oc/deepseek-v4-flash-free` is a reasoning model — it "thinks" before answering. Use `max_tokens` ≥ 300 in your requests or the reply may be truncated.

### Security
- `.railway-token` and `state.json` (contains API keys) are git-ignored. Don't commit them.
- The dashboard password in `settings.json` is local-only; change it with `setpass` or by editing the file.

---

## Project layout

```
9railway/
├── 9router.py        # core CLI (all commands, cross-platform)
├── 9router-tui.py    # interactive terminal menu
├── 9router-web.py    # local web dashboard server
├── web/
│   └── index.html    # dashboard frontend (external file)
├── requirements.txt  # explicit Python marker (stdlib-only — nothing to install)
├── settings.json     # config (auto-created, committed template)
├── state.json        # runtime state — service URLs/keys (git-ignored)
├── .railway-token    # your Railway token (git-ignored)
└── README.md
```

---

## References

- [9Router](https://github.com/decolua/9router) — the self-hosted AI gateway this tool deploys
- [Railway](https://railway.com) — deployment platform
- [Railway CLI](https://docs.railway.com/reference/cli) — the CLI this tool wraps
- [Railway Public API](https://docs.railway.com/reference/public-api) — GraphQL API docs
