#!/usr/bin/env python3
"""
9router-web.py — local web UI for the 9router manager.

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
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIR = Path(__file__).resolve().parent
CORE = DIR / "9router.py"
WEB_HTML = DIR / "web" / "index.html"
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
# HTTP server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            try:
                html = WEB_HTML.read_text(encoding="utf-8")
            except Exception:
                html = "<h1>web/index.html missing</h1>"
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
    print(f"  9Router Manager web UI →  http://localhost:{port}")
    print("  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
        server.server_close()


if __name__ == "__main__":
    main()
