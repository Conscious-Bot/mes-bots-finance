"""Presage live server: regenere le dashboard depuis la DB du bot et le sert.

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
import sys
import threading
import time
from pathlib import Path

import dashboard.render as render_mod

PORT = int(os.environ.get("PRESAGE_PORT", "8000"))
INTERVAL = int(os.environ.get("PRESAGE_REFRESH", "60"))

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Modules dont les changements doivent declencher un reload.
# render.py est le principal mais TOUT module use par render (shared.storage,
# intelligence.*) compte aussi — sinon les nouvelles fonctions ajoutees a
# storage.py ne sont jamais visibles par le render cycle (cache import).
_WATCHED_PATHS = [
    Path(__file__).with_name("render.py"),
    Path(__file__).with_name("chat.py"),
    _REPO_ROOT / "shared" / "storage.py",
    _REPO_ROOT / "intelligence" / "portfolio_grade.py",
    _REPO_ROOT / "intelligence" / "bot_conceptions.py",
    _REPO_ROOT / "intelligence" / "bot_preferences.py",
    _REPO_ROOT / "intelligence" / "factor_exposures.py",
    _REPO_ROOT / "intelligence" / "spof_and_sizing.py",
    _REPO_ROOT / "intelligence" / "wrapper_tax.py",
    _REPO_ROOT / "intelligence" / "benchmark.py",
    _REPO_ROOT / "intelligence" / "return_clustering.py",
    _REPO_ROOT / "intelligence" / "kill_criteria_monitor.py",
    _REPO_ROOT / "intelligence" / "portfolio_grade_llm.py",
]


def _mtimes() -> dict:
    out: dict = {}
    for p in _WATCHED_PATHS:
        try:
            out[str(p)] = p.stat().st_mtime
        except OSError:
            out[str(p)] = 0.0
    return out


_LAST_MTIMES = _mtimes()


def _reload_changed(prev: dict, curr: dict) -> list[str]:
    """Reload modules whose backing file changed. Returns list of modules reloaded."""
    reloaded = []
    for path_str, mtime in curr.items():
        if mtime == prev.get(path_str):
            continue
        # Path -> module name (dotted)
        p = Path(path_str)
        # find the module name relative to repo root
        try:
            rel = p.relative_to(_REPO_ROOT)
        except ValueError:
            continue
        mod_name = ".".join(rel.with_suffix("").parts)
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
                reloaded.append(mod_name)
            except Exception as e:
                print(f"[serve] reload {mod_name} FAILED: {type(e).__name__}: {e}", flush=True)
    return reloaded


def _fresh_render():
    """Recharge tout module surveille qui a change sur disque, puis rend."""
    global _LAST_MTIMES
    curr = _mtimes()
    reloaded = _reload_changed(_LAST_MTIMES, curr)
    if reloaded:
        # render.py doit etre rechargee EN DERNIER si elle change, pour binder
        # les nouvelles versions des dependances. Force reload du render au cas ou.
        importlib.reload(render_mod)
        print(f"[serve] reload : {', '.join(reloaded)}", flush=True)
    _LAST_MTIMES = curr
    render_mod.render()


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass

    def do_POST(self):
        """Sprint 7 — /chat endpoint : RAG sur DB + Opus."""
        if self.path != "/chat":
            self.send_error(404)
            return
        import json as _json

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = self.rfile.read(length).decode("utf-8") if length else ""
            payload = _json.loads(body) if body else {}
            message = (payload.get("message") or "").strip()
            history = payload.get("history") or []
            session_id = payload.get("session_id") or None
            if not isinstance(history, list):
                history = []
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_json.dumps({"error": f"bad_json: {e}"}).encode("utf-8"))
            return
        try:
            from dashboard.chat import chat as _chat

            result = _chat(message, history=history, session_id=session_id, surface="dashboard")
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_json.dumps({"error": f"{type(e).__name__}: {e}"}).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(_json.dumps(result, ensure_ascii=False).encode("utf-8"))


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
