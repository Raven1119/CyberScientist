"""The browser must wait for the real local backend to become healthy."""
import io
import webbrowser

from cyberscientist import cli


def test_browser_opens_after_health_check(monkeypatch):
    attempts = []
    opened = []

    class Response(io.BytesIO):
        status = 200

    def urlopen(url, *, timeout):
        attempts.append((url, timeout))
        if len(attempts) < 3:
            raise OSError("server starting")
        assert not opened
        return Response(b'{"ok":true}')

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    cli._open_browser_when_ready("http://127.0.0.1:8765")

    assert len(attempts) == 3
    assert all(url == "http://127.0.0.1:8765/api/v1/health"
               for url, _ in attempts)
    assert opened == ["http://127.0.0.1:8765"]
