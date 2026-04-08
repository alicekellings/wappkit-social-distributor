from pathlib import Path

from app.config import Config


def test_wordpress_access_token_b64_overrides_plain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WORDPRESS_ACCESS_TOKEN", "plain-token")
    monkeypatch.setenv("WORDPRESS_ACCESS_TOKEN_B64", "YjY0LXRva2Vu")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))

    config = Config.load()

    assert config.wordpress_access_token == "b64-token"
