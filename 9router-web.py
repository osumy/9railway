#!/usr/bin/env python3
"""
9router-web.py — local web UI for the 9Railway manager.

Serves a lightweight dashboard on http://localhost:8989 that talks to the
same modular core (9router.py). No external dependencies — stdlib http.server.

Usage:
  python 9router-web.py            # open http://localhost:8687
  python 9router-web.py --port 9000
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse as urlparse
import urllib.request as urlreq
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIR = Path(__file__).resolve().parent
CORE = DIR / "9router.py"
WEB_HTML = DIR / "web" / "index.html"
LOGIN_HTML = DIR / "web" / "login.html"
PORT = 8989

# ---------------------------------------------------------------------------
# Core bridge — run 9router.py commands and capture output
# ---------------------------------------------------------------------------
def run_cmd(args, timeout=300):
    """Run a core command in a subprocess, return (ok, output)."""
    try:
        p = subprocess.run(
            [sys.executable, str(CORE), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(DIR),
        )
        out = (p.stdout or "") + ("\n[stderr] " + p.stderr if p.stderr else "")
        return p.returncode == 0, out.strip()
    except subprocess.TimeoutExpired:
        return False, "⏱️  timeout — command took too long"
    except Exception as e:
        return False, f"error: {e}"


def read_state():
    state_file = DIR / "state.json"
    if not state_file.exists():
        return {"services": []}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {"services": []}


def read_settings():
    sfile = DIR / "settings.json"
    if not sfile.exists():
        return {}
    try:
        return json.loads(sfile.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Auth — token in .railway-token (same as the core CLI)
# ---------------------------------------------------------------------------
TOKEN_FILE = DIR / ".railway-token"

# Railway OAuth (device-less PKCE flow, same client as `railway login`)
OAUTH_CLIENT_ID = "rlwy_oaci_onEklvmksh1hRUiCo7E2zX12"
OAUTH_AUTH_URL = "https://backboard.railway.com/oauth/auth"
OAUTH_TOKEN_URL = "https://backboard.railway.com/oauth/token"
OAUTH_SCOPES = "openid email profile offline_access workspace:admin project:admin ssh_keys"

def has_token() -> bool:
    if TOKEN_FILE.exists() and TOKEN_FILE.read_text(encoding="utf-8").strip():
        return True
    return False

def save_token(tok: str) -> bool:
    tok = tok.strip()
    if not tok:
        return False
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    return True

def delete_token():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


# ---------------------------------------------------------------------------
# OAuth helpers (PKCE — same flow as `railway login`)
# ---------------------------------------------------------------------------
import base64
import hashlib
import secrets

# Per-session OAuth state. Each start_oauth() creates a fresh one so that
# multiple parallel flows (or stale tabs) don't trample each other.
_oauth_sessions = {}  # state -> {verifier, created}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start_oauth() -> dict:
    """Generate PKCE pair + state, return the auth URL the browser should open."""
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(16)
    _oauth_sessions[state] = {"verifier": verifier, "created": time.time()}
    # cap session stash to avoid unbounded growth
    if len(_oauth_sessions) > 20:
        oldest = min(_oauth_sessions, key=lambda k: _oauth_sessions[k]["created"])
        _oauth_sessions.pop(oldest, None)

    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": f"http://127.0.0.1:{PORT}/callback",
        "scope": OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        # Required by Railway's Ory Hydra: force the consent screen so the
        # interaction session matches the (existing) authentication session.
        "prompt": "consent",
        "cli_caller": "tty",
    }
    url = OAUTH_AUTH_URL + "?" + urlparse.urlencode(params)
    return {"url": url, "state": state}


def exchange_code(code: str, state: str) -> str:
    """Exchange the authorization code for an access token (PKCE)."""
    session = _oauth_sessions.get(state)
    if not session:
        raise ValueError("state unknown or expired — please retry")
    _oauth_sessions.pop(state, None)  # one-shot
    verifier = session["verifier"]
    form = urlparse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"http://127.0.0.1:{PORT}/callback",
        "client_id": OAUTH_CLIENT_ID,
        "code_verifier": verifier,
    }).encode()
    req = urlreq.Request(OAUTH_TOKEN_URL, data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    # Cloudflare blocks requests that look like bots (urllib's default
    # python-urllib/3.x signature → error 1010). Send a real browser's
    # User-Agent + Accept so the token exchange is accepted.
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/126.0 Safari/537.36")
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Origin", f"http://127.0.0.1:{PORT}")
    try:
        with urlreq.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        # Include the provider's error body (invalid_grant vs other) for debugging
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise ValueError(f"token exchange failed: HTTP {e.code} {detail}")
    token = data.get("access_token", "")
    if not token:
        raise ValueError("no access_token in response")
    return token


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Root: if no token → login page, else dashboard
        if parsed.path in ("/", "/index.html"):
            if has_token():
                try:
                    html = WEB_HTML.read_text(encoding="utf-8")
                except Exception:
                    html = "<h1>web/index.html missing</h1>"
            else:
                try:
                    html = LOGIN_HTML.read_text(encoding="utf-8")
                except Exception:
                    html = "<h1>web/login.html missing</h1>"
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Auth status
        if parsed.path == "/api/auth":
            self._json(200, {"authenticated": has_token()})
            return

        # Start OAuth flow — return the Railway authorization URL
        if parsed.path == "/api/oauth/start":
            self._json(200, start_oauth())
            return

        # OAuth callback — Railway redirects here after the user approves
        if parsed.path == "/callback":
            qs = urlparse.parse_qs(parsed.query)
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]
            if not code or not state:
                body = "<h3>OAuth failed: missing code/state</h3><p><a href='/'>go back</a></p>".encode()
            else:
                try:
                    token = exchange_code(code, state)
                    save_token(token)
                    body = ("<h3>✅ Connected to Railway!</h3><p>Returning to the dashboard…</p>"
                            "<script>setTimeout(()=>location.href='/',800)</script>").encode()
                except Exception as e:
                    body = f"<h3>❌ OAuth failed: {e}</h3><p><a href='/'>try again</a></p>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Protected endpoints require a token
        if parsed.path in ("/api/state", "/api/run") and not has_token():
            self._json(401, {"ok": False, "output": "not authenticated"})
            return

        if parsed.path == "/api/state":
            data = json.dumps(read_state(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/run":
            qs = urllib.parse.parse_qs(parsed.query)
            raw = qs.get("args", ["[]"])[0]
            try:
                args = json.loads(raw)
                if not isinstance(args, list):
                    raise ValueError
            except Exception:
                self._json(400, {"ok": False, "output": "bad args"})
                return
            ok, output = run_cmd(args)
            self._json(200, {"ok": ok, "output": output})
            return

        self._json(404, {"ok": False, "output": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/login":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
                tok = body.get("token", "")
            except Exception:
                self._json(400, {"ok": False, "error": "bad body"})
                return
            if save_token(tok):
                self._json(200, {"ok": True, "authenticated": True})
            else:
                self._json(400, {"ok": False, "error": "empty token"})
            return

        if parsed.path == "/api/logout":
            delete_token()
            self._json(200, {"ok": True, "authenticated": False})
            return

        self._json(404, {"ok": False, "output": "not found"})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[web] " + fmt % args + "\n")


def main():
    global PORT
    port = PORT
    if len(sys.argv) > 1 and sys.argv[1] == "--port" and len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"  9Railway web UI →  http://localhost:{port}")
    print("  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
        server.server_close()


if __name__ == "__main__":
    main()
