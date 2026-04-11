from pathlib import Path

import requests

from app.config import Config
from app.models import ArticleCandidate, RewrittenArticle, SourceArticle
from app.platforms.tumblr import TumblrPublisher
from app.rewrite import TumblrRewriter


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
        devto_api_key=None,
        devto_publish_status="draft",
        devto_default_tags=["wappkit", "software", "saas"],
        devto_require_llm_for_publication=True,
        tumblr_client_id="client-id",
        tumblr_client_secret="client-secret",
        tumblr_access_token="access-token",
        tumblr_refresh_token="refresh-token",
        tumblr_blog_identifier="myawesomeblogs",
        tumblr_publish_status="draft",
        tumblr_default_tags=["wappkit", "blog", "software"],
        tumblr_require_llm_for_publication=True,
    )


def build_source_article() -> SourceArticle:
    return SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="## Section\n\nA paragraph with [a link](https://example.com).",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )


def test_tumblr_fallback_rewrite_uses_tumblr_angle(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = TumblrRewriter(config)

    rewritten = rewriter.rewrite(build_source_article())

    assert "Tumblr-friendly adaptation" in rewritten.body_markdown
    assert "## Why this matters" in rewritten.body_markdown
    assert "This Tumblr version links back to the source." in rewritten.body_markdown
    assert rewritten.rewrite_source == "fallback"


def test_tumblr_build_payload_uses_npf_content(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    publisher = TumblrPublisher(config)
    source = build_source_article()
    rewritten = RewrittenArticle(
        title="A better demo post",
        description="Fresh description",
        body_markdown="## Why this matters\n\nA paragraph with [a link](https://example.com).",
        tags=["wappkit", "reddittoolbox"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    payload = publisher.build_payload(rewritten, source)

    assert payload["state"] == "draft"
    assert payload["tags"] == "wappkit,reddittoolbox"
    assert payload["content"][0]["type"] == "text"
    assert "Why this matters" in payload["content"][0]["text"]
    assert "https://example.com" in payload["content"][0]["text"]


def test_tumblr_build_payload_preserves_clean_bullets(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    publisher = TumblrPublisher(config)
    source = build_source_article()
    rewritten = RewrittenArticle(
        title="Bullet demo",
        description="Bullet description",
        body_markdown="## Why this matters\n\n- First point\n- Second point",
        tags=["wappkit"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    payload = publisher.build_payload(rewritten, source)

    assert "- First point" in payload["content"][0]["text"]
    assert "鈥?" not in payload["content"][0]["text"]


def test_tumblr_refreshes_token_after_unauthorized(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    publisher = TumblrPublisher(config)
    source = build_source_article()
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Body paragraph.",
        tags=["wappkit"],
        rewrite_source="llm",
        rewrite_strength="moderate",
    )

    calls = []

    class DummyResponse:
        def __init__(self, status_code: int, data: dict) -> None:
            self.status_code = status_code
            self._data = data
            self.text = str(data)

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} error", response=self)

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "data": data})
        if url.endswith("/v2/blog/myawesomeblogs.tumblr.com/posts") and len(calls) == 1:
            return DummyResponse(401, {"errors": [{"detail": "Unauthorized"}]})
        if url.endswith("/v2/oauth2/token"):
            return DummyResponse(
                200,
                {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "token_type": "bearer",
                    "expires_in": 2520,
                },
            )
        return DummyResponse(
            201,
            {"response": {"id": "123", "state": "draft"}, "meta": {"status": 201, "msg": "Created"}},
        )

    monkeypatch.setattr("app.platforms.tumblr.requests.post", fake_post)

    result = publisher.publish(rewritten, source)

    assert result.external_id == "123"
    assert result.is_draft is True
    assert any(call["url"].endswith("/v2/oauth2/token") for call in calls)
    assert calls[-1]["headers"]["Authorization"] == "Bearer new-access-token"


def test_tumblr_prefers_cached_state_over_bootstrap_tokens(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "tumblr-oauth.json").write_text(
        '{"access_token":"stale-access","refresh_token":"stale-refresh"}',
        encoding="utf-8",
    )

    publisher = TumblrPublisher(config)

    assert publisher._ensure_access_token() == "stale-access"
    assert publisher._refresh_token() == "stale-refresh"


def test_tumblr_bootstraps_token_state_from_config_when_cache_missing(tmp_path: Path) -> None:
    config = build_config(tmp_path)

    publisher = TumblrPublisher(config)

    assert publisher._ensure_access_token() == "access-token"
    assert publisher._refresh_token() == "refresh-token"
    state_file = config.data_dir / "tumblr-oauth.json"
    assert state_file.exists()
    assert '"access_token": "access-token"' in state_file.read_text(encoding="utf-8")


def test_tumblr_refresh_falls_back_to_config_refresh_token_when_cached_one_is_invalid(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "tumblr-oauth.json").write_text(
        '{"access_token":"cached-access","refresh_token":"stale-refresh"}',
        encoding="utf-8",
    )
    publisher = TumblrPublisher(config)

    class DummyResponse:
        def __init__(self, status_code: int, data: dict) -> None:
            self.status_code = status_code
            self._data = data
            self.text = str(data)

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} error", response=self)

    refresh_calls = []

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        if url.endswith("/v2/oauth2/token"):
            refresh_calls.append(data["refresh_token"])
            if data["refresh_token"] == "stale-refresh":
                return DummyResponse(400, {"error": "invalid_grant", "error_description": "Invalid refresh token"})
            return DummyResponse(
                200,
                {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "token_type": "bearer",
                    "expires_in": 2520,
                },
            )
        return DummyResponse(201, {"response": {"id": "123", "state": "draft"}, "meta": {"status": 201, "msg": "Created"}})

    monkeypatch.setattr("app.platforms.tumblr.requests.post", fake_post)

    token = publisher._refresh_access_token()

    assert token == "new-access-token"
    assert refresh_calls == ["stale-refresh", "refresh-token"]
    assert publisher._token_state["refresh_token"] == "new-refresh-token"
