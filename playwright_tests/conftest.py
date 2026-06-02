"""Playwright tests config (#23).

Setup minimal pour smoke tests visuels du dashboard. Pas lance dans la
pytest suite principale -- run separement via :
    pytest playwright_tests/ --browser=chromium

Pre-requis :
    pip install pytest-playwright
    playwright install chromium

Pattern : tests lancent un serveur HTTP local sur dashboard/dashboard.html
genere, puis chargent la page + verifient elements clefs.
"""
from __future__ import annotations

import http.server
import socketserver
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def dashboard_server():
    """HTTP server local servant dashboard/ pour les tests Playwright."""
    project_root = Path(__file__).resolve().parent.parent
    dashboard_dir = project_root / "dashboard"

    # Genere le HTML
    from dashboard.render import render as _render
    _render()

    handler = http.server.SimpleHTTPRequestHandler
    httpd = None
    port = 0

    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    def serve():
        nonlocal httpd, port
        import os
        os.chdir(dashboard_dir)
        with Server(("127.0.0.1", 0), handler) as srv:
            httpd = srv
            port = srv.server_address[1]
            srv.serve_forever()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(0.5)  # warmup

    while port == 0:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"

    if httpd:
        httpd.shutdown()
