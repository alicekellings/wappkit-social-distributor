from pathlib import Path

from app.config import Config


def test_wordpress_access_token_b64_overrides_plain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WORDPRESS_ACCESS_TOKEN", "plain-token")
    monkeypatch.setenv("WORDPRESS_ACCESS_TOKEN_B64", "YjY0LXRva2Vu")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))

    config = Config.load()

    assert config.wordpress_access_token == "b64-token"


def test_mastodon_access_token_b64_overrides_plain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "plain-token")
    monkeypatch.setenv("MASTODON_ACCESS_TOKEN_B64", "bWFzdG9kb24tYjY0LXRva2Vu")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))

    config = Config.load()

    assert config.mastodon_access_token == "mastodon-b64-token"


def test_tumblr_tokens_b64_override_plain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TUMBLR_ACCESS_TOKEN", "plain-access")
    monkeypatch.setenv("TUMBLR_ACCESS_TOKEN_B64", "dHVtYmxyLWI2NC1hY2Nlc3M=")
    monkeypatch.setenv("TUMBLR_REFRESH_TOKEN", "plain-refresh")
    monkeypatch.setenv("TUMBLR_REFRESH_TOKEN_B64", "dHVtYmxyLWI2NC1yZWZyZXNo")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))

    config = Config.load()

    assert config.tumblr_access_token == "tumblr-b64-access"
    assert config.tumblr_refresh_token == "tumblr-b64-refresh"
