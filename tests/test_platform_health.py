from pathlib import Path

import requests

from app.config import Config
from app.platform_health import verify_platforms


def build_config(tmp_path: Path) -> Config:
    return Config(
        root_dir=tmp_path,
        site_url="https://www.wappkit.com",
        sitemap_url="https://www.wappkit.com/sitemap.xml",
        rss_url="https://www.wappkit.com/rss.xml",
        content_raw_base_url="https://raw.githubusercontent.com/example/repo/main/content/blog",
        data_dir=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        request_timeout_seconds=10,
        check_interval_minutes=30,
        max_articles_per_run=1,
        openai_api_key=None,
        openai_base_url=None,
        openai_model="gpt-5.4",
        delivery_platforms=["devto", "blogger", "wordpress", "mastodon", "tumblr"],
        devto_api_key="devto-token",
        devto_publish_status="draft",
        devto_default_tags=["wappkit", "software", "saas"],
        devto_require_llm_for_publication=True,
        blogger_access_token="blogger-stale",
        blogger_client_id="blogger-client-id",
        blogger_client_secret="blogger-client-secret",
        blogger_refresh_token="blogger-refresh-token",
        blogger_blog_id=None,
        blogger_blog_url="https://wappkit.blogspot.com",
        blogger_publish_status="draft",
        blogger_default_labels=["wappkit", "blog", "software"],
        blogger_require_llm_for_publication=True,
        wordpress_access_token="wordpress-token",
        wordpress_site="blogxblog2.wordpress.com",
        wordpress_publish_status="draft",
        wordpress_default_tags=["wappkit", "blog", "software"],
        wordpress_default_categories=["Wappkit"],
        wordpress_require_llm_for_publication=True,
        mastodon_base_url="https://mastodon.social",
        mastodon_access_token="mastodon-token",
        mastodon_visibility="unlisted",
        mastodon_language="en",
        mastodon_require_llm_for_publication=True,
        tumblr_client_id="tumblr-client-id",
        tumblr_client_secret="tumblr-client-secret",
        tumblr_access_token="tumblr-stale",
        tumblr_refresh_token="tumblr-refresh-token",
        tumblr_blog_identifier="myawesomeblogs",
        tumblr_publish_status="draft",
        tumblr_default_tags=["wappkit", "blog", "software"],
        tumblr_require_llm_for_publication=True,
    )


class DummyResponse:
    def __init__(self, status_code: int, data: dict | list) -> None:
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


def test_verify_platforms_succeeds_and_refreshes_when_needed(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == "https://dev.to/api/articles/me/all":
            return DummyResponse(200, [{"id": 1}])
        if url == "https://public-api.wordpress.com/rest/v1.1/me":
            return DummyResponse(200, {"username": "linghonsly"})
        if url == "https://public-api.wordpress.com/rest/v1.1/sites/blogxblog2.wordpress.com":
            return DummyResponse(200, {"ID": 251172452})
        if url == "https://mastodon.social/api/v1/accounts/verify_credentials":
            return DummyResponse(200, {"acct": "xmhero"})
        if url == "https://api.tumblr.com/v2/blog/myawesomeblogs/info":
            return DummyResponse(200, {"response": {"blog": {"name": "myawesomeblogs"}}})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_verify_blogger(token, timeout=30):
        if token == "blogger-stale":
            raise requests.HTTPError("400 error")
        return {"scope": "https://www.googleapis.com/auth/blogger"}

    def fake_verify_tumblr(token, timeout=30):
        if token == "tumblr-stale":
            raise requests.HTTPError("401 error")
        return {"response": {"user": {"name": "myawesomeblogs"}}}

    monkeypatch.setattr("app.platform_health.requests.get", fake_get)
    monkeypatch.setattr("app.platform_health.verify_blogger_access_token", fake_verify_blogger)
    monkeypatch.setattr("app.platform_health.verify_tumblr_access_token", fake_verify_tumblr)
    monkeypatch.setattr("app.platform_health.BloggerPublisher._ensure_access_token", lambda self: "blogger-stale")
    monkeypatch.setattr("app.platform_health.BloggerPublisher._can_refresh", lambda self: True)
    monkeypatch.setattr("app.platform_health.BloggerPublisher._refresh_access_token", lambda self: "blogger-fresh")
    monkeypatch.setattr("app.platform_health.BloggerPublisher._resolve_blog_id", lambda self: "5177827481672815905")
    monkeypatch.setattr("app.platform_health.TumblrPublisher._ensure_access_token", lambda self: "tumblr-stale")
    monkeypatch.setattr("app.platform_health.TumblrPublisher._can_refresh", lambda self: True)
    monkeypatch.setattr("app.platform_health.TumblrPublisher._refresh_access_token", lambda self: "tumblr-fresh")

    results = verify_platforms(config)

    by_platform = {result.platform: result for result in results}
    assert all(result.ok for result in results)
    assert by_platform["blogger"].used_refresh is True
    assert by_platform["tumblr"].used_refresh is True
    assert "sample_count=1" in by_platform["devto"].detail
    assert "site_id=251172452" in by_platform["wordpress"].detail
    assert "acct=xmhero" in by_platform["mastodon"].detail


def test_verify_platforms_reports_missing_config(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    config.devto_api_key = None

    result = verify_platforms(config, platforms=["devto"])[0]

    assert result.ok is False
    assert result.detail == "DEVTO_API_KEY is missing."
