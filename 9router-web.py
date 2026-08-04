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
# Tiny HTML template
# ---------------------------------------------------------------------------
PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>9Router Manager</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background:#0f1117; color:#e6e6e6; padding:24px; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  .sub { color:#888; font-size:13px; margin-bottom:20px; }
  .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap:16px; margin-bottom:24px; }
  .card { background:#171a23; border:1px solid #262b38; border-radius:12px; padding:16px; }
  .card h3 { font-size:15px; margin-bottom:8px; color:#9db4ff; }
  .kv { font-size:13px; line-height:1.7; }
  .kv b { color:#c9d1e8; }
  .key { font-family: monospace; color:#7ee787; font-size:12px; word-break: break-all; }
  .btnrow { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px; }
  button { background:#232a3b; color:#e6e6e6; border:1px solid #333d55; border-radius:8px; padding:8px 14px; font-size:13px; cursor:pointer; }
  button:hover { background:#2c3550; }
  button.danger { border-color:#7a2e33; color:#ff8f95; }
  button.danger:hover { background:#3a1f22; }
  pre { background:#0b0d13; border:1px solid #222736; border-radius:8px; padding:12px; font-size:12px; overflow:auto; max-height:400px; white-space:pre-wrap; }
  .ok { color:#7ee787; } .err { color:#ff8f95; }
  input { background:#0b0d13; border:1px solid #333d55; border-radius:6px; padding:6px 10px; color:#e6e6e6; font-size:13px; }
  label { font-size:12px; color:#888; display:block; margin-bottom:4px; }
  .row { display:flex; gap:8px; align-items:flex-end; }
</style>
</head>
<body>
  <h1>🚀 9Router Manager</h1>
  <div class="sub">Local dashboard — deploy, manage and test 9Router services on Railway</div>

  <div class="btnrow">
    <button onclick="cmd(['list'])">Refresh list</button>
    <button onclick="cmd(['status'])">Status</button>
    <button onclick="cmd(['keys'])">Keys</button>
    <button onclick="cmd(['sync'])">Sync all</button>
    <button onclick="cmd(['clean'])">Clean volumes</button>
    <button class="danger" onclick="nuke()">☢ NUKE project</button>
  </div>

  <div class="row" style="margin-bottom:16px">
    <div><label>Deploy N services</label>
      <div class="row"><input id="ncount" type="number" value="1" min="1" max="5" style="width:70px">
      <button onclick="cmd(['up', document.getElementById('ncount').value])">Deploy</button></div>
    </div>
  </div>

  <h2 style="font-size:16px; margin-bottom:10px">Services</h2>
  <div id="services" class="grid"></div>

  <h2 style="font-size:16px; margin:16px 0 8px">Output</h2>
  <pre id="output">(run a command to see output)</pre>

<script>
async function cmd(args) {
  const pre = document.getElementById('output');
  pre.textContent = 'Running: python 9router.py ' + args.join(' ') + ' ...';
  pre.className = '';
  try {
    const r = await fetch('/api/run?args=' + encodeURIComponent(JSON.stringify(args)));
    const d = await r.json();
    pre.textContent = d.output || '(no output)';
    pre.className = d.ok ? 'ok' : 'err';
  } catch(e) {
    pre.textContent = 'fetch error: ' + e;
    pre.className = 'err';
  }
  loadServices();
}
function nuke() {
  if (confirm('NUKE deletes the ENTIRE project (all services, volumes, data). Continue?')) {
    cmd(['nuke']);
  }
}
async function loadServices() {
  try {
    const r = await fetch('/api/state');
    const d = await r.json();
    const grid = document.getElementById('services');
    const svcs = d.services || [];
    if (!svcs.length) {
      grid.innerHTML = '<div class="card"><h3>No services yet</h3><div class="kv">Run <b>Deploy</b> above.</div></div>';
      return;
    }
    grid.innerHTML = svcs.map(s => `
      <div class="card">
        <h3>${s.service || '?'}</h3>
        <div class="kv">
          <div><b>URL</b><br><span class="key">${s.url || ''}/v1</span></div>
          <div style="margin-top:6px"><b>API key</b><br><span class="key">${s.api_key || ''}</span></div>
          <div style="margin-top:6px"><b>Combo</b> ${s.combo || ''} · <b>Model</b> ${s.model || ''}</div>
        </div>
        <div style="margin-top:10px; display:flex; gap:6px">
          <button onclick="cmd(['test', '${s.service}'])">Test</button>
          <button class="danger" onclick="if(confirm('Delete ${s.service}?')) cmd(['down', '${s.service}'])">Delete</button>
        </div>
      </div>`).join('');
  } catch(e) { console.error(e); }
}
loadServices();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            body = PAGE.encode()
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
