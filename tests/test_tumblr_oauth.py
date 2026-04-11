from pathlib import Path

from app.secret_codec import decode_secret
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


def test_save_tumblr_tokens_to_config_writes_obf_values(tmp_path: Path) -> None:
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
    data = __import__("json").loads(text)
    assert decode_secret(data["TUMBLR_ACCESS_TOKEN_OBF"], "TUMBLR_ACCESS_TOKEN_OBF") == "access-123"
    assert decode_secret(data["TUMBLR_REFRESH_TOKEN_OBF"], "TUMBLR_REFRESH_TOKEN_OBF") == "refresh-456"
    assert decode_secret(data["TUMBLR_CLIENT_ID_OBF"], "TUMBLR_CLIENT_ID_OBF") == "client-id"
    assert decode_secret(data["TUMBLR_CLIENT_SECRET_OBF"], "TUMBLR_CLIENT_SECRET_OBF") == "client-secret"
    assert '"TUMBLR_BLOG_IDENTIFIER": "myawesomeblogs"' in text
