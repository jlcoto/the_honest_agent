import http.client
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner

from honest_agent.cli import main
from honest_agent.report import GENERATOR_TAG
from honest_agent.serve import make_server


@pytest.fixture
def report_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "honest_agent_report"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(f"<html><head>{GENERATOR_TAG}></head></html>")
    (folder / "assets" / "app.js").write_text("console.log(1)")
    (folder / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n")
    return folder


@pytest.fixture
def server(report_dir: Path):
    httpd = make_server(report_dir, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _get(port: int, path: str, host: str | None = None) -> int:
    con = http.client.HTTPConnection("127.0.0.1", port)
    con.request("GET", path, headers={"Host": host or f"127.0.0.1:{port}"})
    status = con.getresponse().status
    con.close()
    return status


def test_the_report_is_served(server: int):
    assert _get(server, "/") == 200
    assert _get(server, "/assets/app.js") == 200
    assert _get(server, "/?result=abc") == 200
    assert _get(server, "/", host=f"localhost:{server}") == 200


def test_another_host_name_is_refused(server: int):
    """DNS rebinding: a page on attacker.example made to resolve to 127.0.0.1."""
    assert _get(server, "/", host=f"attacker.example:{server}") == 403
    assert _get(server, "/", host="127.0.0.1:1") == 403


@pytest.mark.parametrize("path", ["/.env", "/%2eenv", "/assets/", "/assets/../.env"])
def test_no_dotfiles_and_no_folder_listings(server: int, path: str):
    assert _get(server, path) == 404


def test_serve_refuses_a_folder_report_did_not_write(tmp_path: Path):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n")

    result = CliRunner().invoke(main, ["serve", "--out", str(tmp_path), "--no-open-browser"])

    assert result.exit_code != 0
    assert "isn't an honest-agent report folder" in result.output
