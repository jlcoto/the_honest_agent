"""Serves a generated report folder locally, the same way `dbt docs serve`
serves `target/` -- a thin wrapper around Python's stdlib static file server.
Needed because browsers won't load the report's data from a `file://` page.

Only on 127.0.0.1, and only what a report needs:
- a folder `report` wrote (cli.py checks), so `serve --out .` can't publish a project's
  `.env` or anything else that happens to be there;
- requests addressed to this machine by name or address, so a web page can't reach the
  server through DNS rebinding (its own domain made to resolve to 127.0.0.1);
- no folder listings and no dotfiles.
"""

from __future__ import annotations

import functools
import http.server
import webbrowser
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


class _ReportHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self._allowed():
            super().do_GET()

    def do_HEAD(self) -> None:
        if self._allowed():
            super().do_HEAD()

    def _allowed(self) -> bool:
        port = self.server.server_address[1]
        host = (self.headers.get("Host") or "").lower()
        if host not in {f"{name}:{port}" for name in _LOCAL_HOSTS}:
            self.send_error(HTTPStatus.FORBIDDEN, "Only requests to 127.0.0.1 or localhost are served")
            return False
        # Decoded first, as the file lookup does: `%2eenv` is `.env`.
        path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])
        if any(part.startswith(".") for part in path.split("/")):
            self.send_error(HTTPStatus.NOT_FOUND)
            return False
        return True

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    # Without this, browsers can keep showing the previous report after
    # `honest-agent report` regenerates it into the same folder.
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def make_server(report_dir: Path, port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_ReportHandler, directory=str(report_dir))
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(report_dir: Path, port: int, open_browser: bool = True) -> None:
    httpd = make_server(report_dir, port)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
