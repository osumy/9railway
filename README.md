# 9Router CLI — Railway Auto-Deployer

A bash CLI that fully automates deploying and managing [9Router](https://github.com/decolua/9router) (self-hosted AI gateway) services on [Railway](https://railway.com) — from project creation to ready-to-use API keys.

## What it does

One tool that:
- Ensures a Railway project named `9router` exists (creates it if missing)
- Deploys **N services** in parallel into that project
- Auto-configures **each service** (login → add model → create combo → create API key)
- Saves everything (`URL`, `API key`, combo, model) into `state.json`
- Lets you manage them: list, show keys, delete one or all

## Quick start

```bash
# One-time setup
railway login
# put your token in .railway-token (git-ignored) or export RAILWAY_API_TOKEN

# Deploy 3 services, all auto-configured
bash 9router-cli.sh up 3

# See what you have (URLs + API keys)
bash 9router-cli.sh list

# Show only the API keys
bash 9router-cli.sh keys
```

## Commands

| Command | What it does |
|---|---|
| `up [N]` | Deploy N new services (default 1), auto-configure each, save to state |
| `sync` | Re-configure existing services in the project (no new deploy) |
| `list` | Show saved services (URL + API key + combo) |
| `keys` | Show only API keys |
| `status` | Live Railway status (services, volumes) |
| `down [name\|all]` | Delete one service (by name) or all of them |
| `setpass <new>` | Change the default dashboard password |
| `reset` | Clear `state.json` (services are NOT touched) |

## Config & state

**`settings.json`** — created automatically on first run:

```json
{
  "default_password": "MyPassword123456",
  "combo_name": "claude-opus-5",
  "model_id": "oc/deepseek-v4-flash-free"
}
```

Change the dashboard password with `setpass`, or edit the file directly.

**`state.json`** — the source of truth for your deployed services:

```json
{
  "services": [
    {
      "service": "9router-abc1",
      "url": "https://9router-abc1-production.up.railway.app",
      "api_key": "sk-...",
      "combo": "claude-opus-5",
      "model": "oc/deepseek-v4-flash-free",
      "created": "2026-08-04T17:37:28Z",
      "project_id": "..."
    }
  ]
}
```

## How the auto-configuration works

For each deployed service, the script:
1. Logs in to the dashboard with `default_password`
2. Adds the model via `POST /api/models/custom`
3. Creates the combo via `POST /api/combos`
4. Creates an API key via `POST /api/keys`
5. Saves everything to `state.json`

Verified working end-to-end (real requests returned `cost: 0`).

## Usage notes

- **Token refresh**: if `RAILWAY_API_TOKEN` expires, re-run `railway login` and copy the fresh access token from `~/.railway/config.json` into `.railway-token`.
- **Volume persistence**: the DB (providers, combos, keys) lives on a Railway volume — data survives redeploys.
- **Reasoning models**: `oc/deepseek-v4-flash-free` is a reasoning model — use `max_tokens` ≥ 300 so answers don't get truncated (it spends tokens "thinking" first).

## Example usage

```bash
# Deploy 3 services
bash 9router-cli.sh up 3

# List them
bash 9router-cli.sh list

# Test one with curl
curl -X POST "https://YOUR-SERVICE.up.railway.app/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-YOUR-KEY" \
  -d '{"model":"claude-opus-5","messages":[{"role":"user","content":"سلام"}],"max_tokens":300}'

# Delete everything
bash 9router-cli.sh down all
```
