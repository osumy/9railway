#!/usr/bin/env python3
"""
9router.py — cross-platform CLI for managing 9Router services on Railway.

Works identically on Windows, Linux, and macOS (needs Python 3.8+).

Commands:
  up [N]              Deploy N new 9router services (default 1), auto-configure each
  sync                Re-configure existing services (no new deploy)
  list                Show saved services (URL + API key + combo)
  keys                Show only API keys
  status              Live Railway status
  down [name|all]     Delete one service or all services (+ detached volumes)
  nuke                Delete the ENTIRE project (fixes stuck volumes)
  clean               Delete detached volumes
  setpass <new>       Change default dashboard password
  config              Show current settings
  test <name>         Send a real request to a service (verifies it works)
  token               Show token status / refresh instructions
  reset               Clear state.json (services untouched)
  help                Show this help
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
DIR = Path(__file__).resolve().parent
SETTINGS_FILE = DIR / "settings.json"
STATE_FILE = DIR / "state.json"
TOKEN_FILE = DIR / ".railway-token"
RAILWAY_CONFIG = Path.home() / ".railway" / "config.json"

PROJECT_NAME = "9router"

DEFAULT_SETTINGS = {
    "default_password": "MyPassword123456",
    "combo_name": "claude-opus-5",
    "model_id": "oc/deepseek-v4-flash-free",
}

_RAILWAY = None  # cached resolved railway binary

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def eprint(*a):
    print(*a, file=sys.stderr)

def banner(title: str):
    print("\n" + "═" * 52)
    print(f"  {title}")
    print("═" * 52)

def ok(msg: str):
    print(f"  ✅ {msg}")

def warn(msg: str):
    print(f"  ⚠️  {msg}")

def fail(msg: str):
    print(f"  ❌ {msg}")

# ---------------------------------------------------------------------------
# Settings & state
# ---------------------------------------------------------------------------
def ensure_settings():
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")

def load_settings() -> dict:
    ensure_settings()
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_settings(s: dict):
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

def ensure_state():
    if not STATE_FILE.exists():
        STATE_FILE.write_text(json.dumps({"services": []}, indent=2), encoding="utf-8")

def load_state() -> dict:
    ensure_state()
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_state(s: dict):
    STATE_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

# ---------------------------------------------------------------------------
# Token handling — cross-platform
# ---------------------------------------------------------------------------
def get_token() -> str:
    """Return a usable Railway token: .railway-token file, or the accessToken
    stored by `railway login` in ~/.railway/config.json."""
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    if RAILWAY_CONFIG.exists():
        try:
            cfg = json.loads(RAILWAY_CONFIG.read_text(encoding="utf-8"))
            tok = (cfg.get("user") or {}).get("accessToken", "").strip()
            if tok:
                return tok
        except Exception:
            pass
    eprint("❌ No Railway token found.")
    eprint("   Run `railway login` once, or put your token in .railway-token")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Railway CLI wrapper
# ---------------------------------------------------------------------------
def find_railway() -> str:
    """Locate the railway CLI binary: .cmd on Windows (npm shim), plain on Unix."""
    for cand in (["railway.cmd", "railway"] if os.name == "nt" else ["railway"]):
        try:
            r = subprocess.run([cand, "--version"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return cand
        except Exception:
            continue
    for base in (Path(os.environ.get("APPDATA", "")) / "npm",
                 Path.home() / ".npm-global", Path.home() / ".local" / "bin"):
        for cand in (["railway.cmd", "railway"] if os.name == "nt" else ["railway"]):
            exe = base / cand
            if exe.exists():
                return str(exe)
    return "railway"

def rail(*args, check=True) -> subprocess.CompletedProcess:
    """Run the railway CLI. Returns completed process (stdout captured)."""
    global _RAILWAY
    if not _RAILWAY:
        _RAILWAY = find_railway()
    try:
        p = subprocess.run([_RAILWAY, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
    except FileNotFoundError:
        eprint("❌ railway CLI not found. Install: npm i -g @railway/cli")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        eprint("⏱️  railway CLI timed out.")
        sys.exit(1)
    if check and p.returncode != 0:
        eprint(f"⚠️  railway {' '.join(args)} failed:\n{p.stdout}\n{p.stderr}")
        return p
    return p

def rail_json(*args):
    p = rail(*args, check=False)
    out = p.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None

# ---------------------------------------------------------------------------
# HTTP helpers (for the 9router dashboard API)
# ---------------------------------------------------------------------------
def http_json(url: str, method: str = "GET", body: dict = None, cookie_jar: str = None, timeout: int = 40):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if cookie_jar:
        req.add_header("Cookie", cookie_jar)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)

def login_get_cookie(domain: str, password: str, retries: int = 3):
    """Login to the 9router dashboard, return the auth cookie string (or None).
    Retries a few times — the container may still be warming up."""
    import http.client
    for attempt in range(retries):
        try:
            conn = http.client.HTTPSConnection(domain, timeout=25)
            payload = json.dumps({"password": password})
            conn.request("POST", "/api/auth/login", body=payload,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", "replace")
            cookie = resp.getheader("Set-Cookie", "")
            conn.close()
            if resp.status == 200 and json.loads(body).get("success"):
                if cookie:
                    return cookie.split(";")[0]
        except Exception:
            pass
        time.sleep(8)
    return None

# ---------------------------------------------------------------------------
# Railway project / service helpers
# ---------------------------------------------------------------------------
def find_project(name: str = PROJECT_NAME):
    d = rail_json("project", "list", "--json")
    if not isinstance(d, list):
        return None
    for p in d:
        if p.get("name") == name and not p.get("deletedAt"):
            return p["id"]
    return None

def create_project(name: str = PROJECT_NAME):
    ws = None
    d = rail_json("project", "list", "--json")
    if isinstance(d, list) and d:
        ws = (d[0].get("workspace") or {}).get("id")
    if ws:
        rail("init", "--name", name, "--workspace", ws, "--json")
    else:
        rail("init", "--name", name)
    time.sleep(3)
    return find_project(name)

def list_services(project_id: str):
    d = rail_json("service", "list", "--project", project_id, "--environment", "production", "--json")
    if not isinstance(d, list):
        return []
    return [(s.get("id", "").strip(), s.get("name", "").strip()) for s in d]

def service_domain(project_id: str, service_name: str):
    d = rail_json("domain", "list", "--project", project_id, "--service", service_name,
                  "--environment", "production", "--json")
    if isinstance(d, dict) and d.get("domains"):
        return d["domains"][0].get("domain", "")
    p = rail("domain", "list", "--project", project_id, "--service", service_name,
             "--environment", "production", check=False)
    m = re.search(r"https?://([\w.-]+\.railway\.app)", p.stdout)
    return m.group(1) if m else ""

def latest_9router_service(project_id: str):
    names = [n for _, n in list_services(project_id) if "9router" in n.lower()]
    return names[-1] if names else ""

def list_detached_volumes():
    p = rail("volume", "list", check=False)
    vols, cur = [], None
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("Volume:"):
            cur = line.split(":", 1)[1].strip()
        elif "Attached to: N/A" in line and cur:
            vols.append(cur)
            cur = None
    return vols

def delete_volume(name: str):
    rail("volume", "delete", "-v", name, "-y", "--json", check=False)

# ---------------------------------------------------------------------------
# Core: configure one service (login → model → combo → key → save)
# ---------------------------------------------------------------------------
def configure_service(project_id: str, service_name: str, password: str) -> bool:
    settings = load_settings()
    combo = settings["combo_name"]
    model = settings["model_id"]
    alias, model_id = model.split("/", 1)

    domain = service_domain(project_id, service_name)
    if not domain:
        eprint(f"   ⚠️  no domain for {service_name}")
        return False

    print(f"   → configure {service_name} ({domain})")

    cookie = login_get_cookie(domain, password)
    if not cookie:
        eprint(f"   ⚠️  login failed for {service_name}")
        return False

    base = f"https://{domain}"

    # add model
    http_json(f"{base}/api/models/custom", "POST",
              {"providerAlias": alias, "id": model_id, "type": "llm"}, cookie)
    # combo
    http_json(f"{base}/api/combos", "POST", {"name": combo, "models": [model]}, cookie)
    # api key
    code, text = http_json(f"{base}/api/keys", "POST", {"name": f"9router-{service_name}"}, cookie)
    api_key = ""
    if code in (200, 201):
        try:
            api_key = json.loads(text).get("key", "")
        except Exception:
            pass

    # save to state
    state = load_state()
    entry = {
        "service": service_name,
        "url": f"https://{domain}",
        "api_key": api_key,
        "combo": combo,
        "model": model,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project_id": project_id,
    }
    state["services"] = [s for s in state["services"] if s.get("service") != service_name]
    state["services"].append(entry)
    save_state(state)

    print(f"   ✅ {service_name} ready: {api_key}")
    return True

def wait_online(domain: str, max_wait: int = 12) -> bool:
    for _ in range(max_wait):
        try:
            with urllib.request.urlopen(f"https://{domain}/api/health", timeout=10) as r:
                if b'"ok":true' in r.read():
                    return True
        except Exception:
            pass
        time.sleep(10)
    return False

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_up(n: int):
    settings = load_settings()
    password = settings["default_password"]

    project_id = find_project(PROJECT_NAME)
    if project_id:
        ok(f"project '{PROJECT_NAME}' exists: {project_id}")
    else:
        print(f"   project '{PROJECT_NAME}' not found → creating...")
        project_id = create_project(PROJECT_NAME)
        ok(f"project created: {project_id}")

    if not project_id:
        fail("could not create/find project")
        sys.exit(1)

    print(f"\n   deploying {n} service(s)...")
    for i in range(1, n + 1):
        print(f"\n── service {i}/{n} ──")
        out = rail("deploy", "--template", "9router",
                   "-v", f"INITIAL_PASSWORD={password}",
                   "-v", "DATA_DIR=/app/data", check=False)
        if "limit exceeded" in out.stdout or "3 volumes" in out.stdout:
            warn("volume limit → cleaning detached volumes, retrying...")
            cmd_clean()
            time.sleep(30)
            out = rail("deploy", "--template", "9router",
                       "-v", f"INITIAL_PASSWORD={password}",
                       "-v", "DATA_DIR=/app/data", check=False)

        # find the new service
        svc = ""
        for _ in range(9):
            time.sleep(10)
            svc = latest_9router_service(project_id)
            if svc:
                break
        if not svc:
            fail("could not find newly created service")
            continue
        print(f"   service: {svc}")

        # wait online + get domain
        domain = ""
        for _ in range(12):
            domain = service_domain(project_id, svc)
            if domain and wait_online(domain, 1):
                break
            time.sleep(10)
        if not domain:
            fail(f"no domain for {svc}")
            continue

        configure_service(project_id, svc, password)

    banner(f"✅ {n} service(s) processed. See:  python 9router.py list")

def cmd_sync():
    settings = load_settings()
    password = settings["default_password"]
    project_id = find_project(PROJECT_NAME)
    if not project_id:
        fail(f"project '{PROJECT_NAME}' not found. Run: python 9router.py up")
        return
    print(f"   configuring existing services in {project_id}...")
    for sid, name in list_services(project_id):
        configure_service(project_id, name, password)

def cmd_list():
    state = load_state()
    svcs = state.get("services", [])
    if not svcs:
        print("   (nothing in state yet — python 9router.py up)")
        return
    for i, s in enumerate(svcs, 1):
        print(f"  [{i}] {s.get('service')}")
        print(f"      URL    : {s.get('url')}/v1")
        print(f"      API key: {s.get('api_key')}")
        print(f"      Combo  : {s.get('combo')}  (model: {s.get('model')})")
        print(f"      Created: {s.get('created')}")
        print()

def cmd_keys():
    state = load_state()
    for s in state.get("services", []):
        print(f"  {s.get('service')}:  {s.get('api_key')}")

def cmd_status():
    p = rail("status", check=False)
    for line in p.stdout.splitlines():
        if re.search(r"Project:|Service:|url:|volume", line, re.I):
            print("  " + line.strip())

def cmd_clean():
    print("   cleaning detached volumes...")
    vols = list_detached_volumes()
    if not vols:
        print("   (none)")
        return
    for v in vols:
        print(f"   → deleting {v}")
        delete_volume(v)
    print("   ✅ detached volumes queued for deletion")

def cmd_down(target: str):
    project_id = find_project(PROJECT_NAME)
    state = load_state()

    if target == "all":
        print("   deleting all 9router services...")
        if project_id:
            for sid, name in list_services(project_id):
                rail("service", "delete", "--project", project_id, "--service", name,
                     "--environment", "production", "--yes", "--json", check=False)
                print(f"   ✅ deleted: {name}")
        state["services"] = []
        save_state(state)
        print("   ✅ state.json cleared")
        cmd_clean()
        return

    if not target:
        print("   usage: down <name|all>")
        cmd_list()
        return

    if project_id:
        rail("service", "delete", "--project", project_id, "--service", target,
             "--environment", "production", "--yes", "--json", check=False)
        print(f"   ✅ deleted: {target}")
    state["services"] = [s for s in state["services"] if s.get("service") != target]
    save_state(state)
    print("   ✅ removed from state.json")

def cmd_nuke():
    """Delete the ENTIRE project. Fixes stuck volumes / quota issues."""
    print("   ⚠️  NUKE: this deletes the whole '9router' project (all services, volumes, data)!")
    project_id = find_project(PROJECT_NAME)
    if not project_id:
        print("   (no '9router' project found — nothing to nuke)")
        return
    print(f"   deleting project {project_id}...")
    rail("project", "delete", "--project", project_id, "--yes", "--json", check=False)
    # clear state too
    save_state({"services": []})
    print("   ✅ project deleted, state cleared")
    print("   Next `up` will recreate everything fresh.")

def cmd_setpass(new: str):
    settings = load_settings()
    settings["default_password"] = new
    save_settings(settings)
    print(f"   ✅ default password changed to {new} (applies to new services)")

def cmd_config():
    settings = load_settings()
    print(json.dumps(settings, indent=2, ensure_ascii=False))
    print(f"\n  settings file: {SETTINGS_FILE}")

def cmd_test(name: str):
    """Send a real request to a saved service."""
    state = load_state()
    target = name
    if not target:
        # pick first
        svcs = state.get("services", [])
        if not svcs:
            fail("no services in state — run `up` first")
            return
        target = svcs[0]["service"]
        print(f"   (no name given, using first: {target})")

    entry = next((s for s in state.get("services", []) if s.get("service") == target), None)
    if not entry:
        fail(f"service '{target}' not in state. Use: python 9router.py list")
        return

    url = entry["url"].rstrip("/") + "/v1/chat/completions"
    key = entry.get("api_key", "")
    print(f"   testing {target} @ {url}")
    print(f"   sending: 'Say OK' (model: {entry.get('combo')})...")

    payload = json.dumps({
        "model": entry.get("combo", "claude-opus-5"),
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 50,
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8", "replace")
            data = json.loads(body.split("data: [DONE]")[0])
            msg = data["choices"][0]["message"]
            content = msg.get("content", "") or ""
            reasoning = msg.get("reasoning_content", "") or ""
            cost = data.get("cost", "?")
            print(f"   ✅ {target} works! model={data.get('model')} cost={cost}")
            if content:
                print(f"      reply: {content[:120]}")
            else:
                print(f"      (reasoning-only reply; max_tokens too low? reasoning: {reasoning[:80]}...)")
    except urllib.error.HTTPError as e:
        fail(f"{target} returned HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:
        fail(f"{target} error: {e}")

def cmd_token():
    tok = get_token()
    masked = tok[:8] + "..." + tok[-4:] if len(tok) > 12 else "***"
    print(f"  Railway token: {masked}")
    print(f"  source: {TOKEN_FILE if TOKEN_FILE.exists() else RAILWAY_CONFIG}")
    print("  To refresh: run `railway login`, then:")
    print("    python -c \"import json,pathlib; print(json.load(open(str(pathlib.Path.home()/'.railway'/'config.json')))['user']['accessToken'])\" > .railway-token")

def cmd_reset():
    save_state({"services": []})
    print("   ✅ state.json reset")

def cmd_help():
    print(__doc__)

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""

    # Commands that don't need Railway at all
    if cmd in ("help", "--help", "-h", "reset", "list", "keys", "config"):
        if cmd == "help" or cmd in ("--help", "-h"):
            cmd_help()
        elif cmd == "reset":
            cmd_reset()
        elif cmd == "list":
            cmd_list()
        elif cmd == "keys":
            cmd_keys()
        elif cmd == "config":
            cmd_config()
        return

    # make token available to railway subprocesses (cross-platform)
    os.environ["RAILWAY_API_TOKEN"] = get_token()

    if cmd == "up":
        n = int(arg) if arg.isdigit() else 1
        cmd_up(n)
    elif cmd == "sync":
        cmd_sync()
    elif cmd == "list":
        cmd_list()
    elif cmd == "keys":
        cmd_keys()
    elif cmd == "status":
        cmd_status()
    elif cmd == "down":
        cmd_down(arg)
    elif cmd == "nuke":
        cmd_nuke()
    elif cmd == "clean":
        cmd_clean()
    elif cmd == "setpass":
        cmd_setpass(arg)
    elif cmd == "config":
        cmd_config()
    elif cmd == "test":
        cmd_test(arg)
    elif cmd == "token":
        cmd_token()
    elif cmd == "reset":
        cmd_reset()
    else:
        cmd_help()

if __name__ == "__main__":
    main()
