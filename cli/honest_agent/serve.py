"""Serves a generated report folder locally, the same way `dbt docs serve`
serves `target/` -- a thin wrapper around Python's stdlib static file server.
Needed because browsers won't load the report's data from a `file://` page.
"""

from __future__ import annotations

import functools
import http.server
import webbrowser
from pathlib import Path


class _RevalidatingHandler(http.server.SimpleHTTPRequestHandler):
    # Without this, browsers can keep showing the previous report after
    # `honest-agent report` regenerates it into the same folder.
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def serve(report_dir: Path, port: int, open_browser: bool = True) -> None:
    handler = functools.partial(_RevalidatingHandler, directory=str(report_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
