<div align="center">

# 🚀 9railway

**Auto-deploy and manage [9Router](https://github.com/decolua/9router) AI gateway services on Railway — from your terminal or browser.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/osumy/9railway/actions/workflows/ci.yml/badge.svg)](https://github.com/osumy/9railway/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/osumy/9railway?style=social)](https://github.com/osumy/9railway)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macOS-9cf)]()

**Zero dependencies · Pure Python stdlib · MIT licensed**

</div>

---

## ✨ What it does

Deploy a fleet of 9Router services on Railway and get **ready-to-use API keys** — no dashboard clicking.

- 🚀 **One-command deploy** — `up N` creates the project, deploys N services in parallel, and auto-configures each one
- 🔑 **Auto API keys** — every service gets a working `sk-...` key, saved to `state.json`
- 🧩 **Combos wired in** — the model (e.g. `oc/deepseek-v4-flash-free`) is plugged into a combo (e.g. `claude-opus-5`) automatically
- 💾 **Volume persistence** — data survives redeploys
- 🧹 **Full lifecycle** — list, test, delete one/all, clean stuck volumes, nuke the whole project
- 🔐 **Token-based auth** — `login` / `logout` in both the CLI and the web dashboard

---

## 🛠️ Two interfaces

### 1. CLI — `python 9router.py <command>`

| Command | What it does |
|---|---|
| `login` | Store your Railway token (pasted, or auto-copied from `railway login`) |
| `logout` | Remove the stored token |
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
| `token` | Show token status |
| `reset` | Clear `state.json` (services are NOT touched) |

### 2. Web dashboard — `python 9router-web.py`

Local dashboard at **http://localhost:8989** — dark theme, service cards with copy-able keys, one-click deploy/test/delete/nuke, live output console.

- **No token?** → you get a clean login page with step-by-step instructions
- **Connected?** → full dashboard with a **Logout** button
- Pure stdlib (`http.server`), no deps.

---

## 🚀 Quick start

```bash
# 1. Prerequisites: Python 3.10+, Railway CLI
railway login                        # once, or use the web login page
python 9router.py login              # store your token in .railway-token

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

> The web dashboard has the same flow — start it, and if no token is stored you'll see the login page first.

---

## ⚙️ Configuration

**`settings.json`** — created automatically on first run:

```json
{
  "default_password": "MyPassword123456",
  "combo_name": "claude-opus-5",
  "model_id": "oc/deepseek-v4-flash-free"
}
```

- `default_password` — dashboard password for new services (change with `setpass`)
- `combo_name` — combo created on each service
- `model_id` — model wired into that combo (`<provider-alias>/<model-id>`)

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

## 🔄 How the auto-configuration works

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

## 🛠️ Troubleshooting

### Token
- `python 9router.py token` shows where your token lives
- Token expired? → `railway login`, then `python 9router.py login` (copies the fresh token)

### Volume limits (free plan)
- Railway free plan allows **3 volumes per project**. After repeated deploy/delete cycles, detached volumes can block new deploys.
- Fix: `python 9router.py clean` (delete detached volumes) or `python 9router.py nuke` (delete the whole project — recreated on next `up`).

### Reasoning models
- `oc/deepseek-v4-flash-free` is a reasoning model — it "thinks" before answering. Use `max_tokens` ≥ 300 or the reply may be truncated.

### Security
- `.railway-token` and `state.json` (contains API keys) are git-ignored. Don't commit them.

---

## 📁 Project layout

```
9railway/
├── 9router.py        # core CLI (all commands, cross-platform)
├── 9router-web.py    # local web dashboard server (auth-aware)
├── web/
│   ├── index.html    # dashboard frontend
│   └── login.html    # login page (shown when no token)
├── requirements.txt  # stdlib-only marker (nothing to install)
├── settings.json     # config (auto-created, committed template)
├── state.json        # runtime state — service URLs/keys (git-ignored)
├── .railway-token    # your Railway token (git-ignored)
├── LICENSE           # MIT
└── README.md
```

---

## 📚 References

- [9Router](https://github.com/decolua/9router) — the self-hosted AI gateway this tool deploys
- [Railway](https://railway.com) — deployment platform
- [Railway CLI](https://docs.railway.com/reference/cli) — the CLI this tool wraps
- [Railway Public API](https://docs.railway.com/reference/public-api) — GraphQL API docs
