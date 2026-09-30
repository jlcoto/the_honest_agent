"""Serves a generated report locally, the same way `dbt docs serve` serves
`target/index.html` -- a thin wrapper around Python's stdlib static file
server, scoped to the report's directory so any relative paths in the report
resolve the same way they would on a real static host.
"""

from __future__ import annotations

import functools
import http.server
import webbrowser
from pathlib import Path


def serve(report_path: Path, port: int, open_browser: bool = True) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(report_path.parent))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/{report_path.name}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
