"""Heimdall live server: regenere le dashboard depuis la DB du bot et le sert.

Read-only: lit data/bot.db (WAL) que le bot ecrit; n'ecrit jamais la DB.
Decouple de bot.main volontairement (restart libre sans toucher au bot).
Hot-reload: si dashboard/render.py change sur disque, le module est recharge
au cycle suivant -> tout patch render.py prend effet sans relancer serve.
Le cache prix (module-level) reste chaud entre cycles, sauf juste apres un patch.
Lancer depuis la racine du repo:  python3 -m dashboard.serve
"""

import functools
import http.server
import importlib
import os
import socketserver
import threading
import time
from pathlib import Path

import dashboard.render as render_mod

PORT = int(os.environ.get("HEIMDALL_PORT", "8000"))
INTERVAL = int(os.environ.get("HEIMDALL_REFRESH", "60"))

_RENDER_PY = Path(__file__).with_name("render.py")
try:
    _LAST_MTIME = _RENDER_PY.stat().st_mtime
except OSError:
    _LAST_MTIME = 0.0


def _fresh_render():
    """Recharge render.py s'il a change sur disque, puis rend."""
    global _LAST_MTIME
    try:
        m = _RENDER_PY.stat().st_mtime
    except OSError:
        m = _LAST_MTIME
    if m != _LAST_MTIME:
        importlib.reload(render_mod)
        _LAST_MTIME = m
        print("[serve] render.py change -> module recharge", flush=True)
    render_mod.render()


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


def _regen_loop():
    while True:
        time.sleep(INTERVAL)
        t0 = time.monotonic()
        try:
            _fresh_render()
            print(f"[serve] regen {time.monotonic() - t0:.1f}s", flush=True)
        except Exception as e:
            print(f"[serve] regen FAILED: {type(e).__name__}: {e}", flush=True)


def main():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        _fresh_render()
        print("[serve] initial render OK", flush=True)
    except Exception as e:
        print(f"[serve] initial render FAILED: {type(e).__name__}: {e}", flush=True)
    threading.Thread(target=_regen_loop, daemon=True).start()
    handler = functools.partial(NoCache, directory="dashboard")
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as srv:
        print(f"[serve] live -> http://127.0.0.1:{PORT}/dashboard.html  (regen {INTERVAL}s)", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
