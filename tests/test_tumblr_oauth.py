from pathlib import Path

from app.tumblr_oauth import build_authorize_url, save_tumblr_tokens_to_config


def test_build_authorize_url_includes_offline_access() -> None:
    url = build_authorize_url(
        client_id="client-id",
        redirect_uri="https://www.wappkit.com/",
        state="state123",
    )

    assert "response_type=code" in url
    assert "client_id=client-id" in url
    assert "redirect_uri=https%3A%2F%2Fwww.wappkit.com%2F" in url
    assert "scope=basic+write+offline_access" in url
    assert "state=state123" in url


def test_save_tumblr_tokens_to_config_writes_b64_values(tmp_path: Path) -> None:
    target = tmp_path / "wappkit-secrets.json"

    path = save_tumblr_tokens_to_config(
        target,
        access_token="access-123",
        refresh_token="refresh-456",
        client_id="client-id",
        client_secret="client-secret",
        blog_identifier="myawesomeblogs",
    )

    text = path.read_text(encoding="utf-8")
    assert path == target
    assert "YWNjZXNzLTEyMw==" in text
    assert "cmVmcmVzaC00NTY=" in text
    assert '"TUMBLR_CLIENT_ID": "client-id"' in text
    assert '"TUMBLR_BLOG_IDENTIFIER": "myawesomeblogs"' in text
