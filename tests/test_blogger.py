from app.config import Config
from app.models import ArticleCandidate, RewrittenArticle, SourceArticle
from app.platforms.blogger import BloggerPublisher, _normalize_blog_url


def build_config(tmp_path):
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
        blogger_access_token="test-token",
        blogger_client_id="client-id",
        blogger_client_secret="client-secret",
        blogger_refresh_token="refresh-token",
        blogger_blog_id="123456",
        blogger_blog_url="https://wappkit.blogspot.com/",
        blogger_publish_status="draft",
        blogger_default_labels=["wappkit", "blog", "software"],
        blogger_require_llm_for_publication=True,
    )


def test_build_payload_renders_html(tmp_path) -> None:
    config = build_config(tmp_path)
    publisher = BloggerPublisher(config)
    source = SourceArticle(
        candidate=ArticleCandidate(slug="demo", url="https://www.wappkit.com/blog/demo"),
        title="Demo",
        description="Demo description",
        markdown="## Title",
        canonical_url="https://www.wappkit.com/blog/demo",
    )
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="## Section\n\nA paragraph with a [link](https://example.com).",
        tags=["wappkit"],
        rewrite_source="llm",
        rewrite_strength="moderate",
    )

    payload = publisher.build_payload(rewritten, source)

    assert payload["title"] == "Demo"
    assert "<h2>Section</h2>" in payload["content"]
    assert 'href="https://example.com"' in payload["content"]


def test_fallback_rewrite_forces_blogger_draft(tmp_path) -> None:
    config = build_config(tmp_path)
    config.blogger_publish_status = "published"
    publisher = BloggerPublisher(config)
    source = SourceArticle(
        candidate=ArticleCandidate(slug="demo", url="https://www.wappkit.com/blog/demo"),
        title="Demo",
        description="Demo description",
        markdown="Hello",
        canonical_url="https://www.wappkit.com/blog/demo",
    )
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Hello",
        tags=["wappkit"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    assert publisher._should_publish_publicly(rewritten) is False


def test_llm_rewrite_allows_blogger_publication(tmp_path) -> None:
    config = build_config(tmp_path)
    config.blogger_publish_status = "published"
    publisher = BloggerPublisher(config)
    source = SourceArticle(
        candidate=ArticleCandidate(slug="demo", url="https://www.wappkit.com/blog/demo"),
        title="Demo",
        description="Demo description",
        markdown="Hello",
        canonical_url="https://www.wappkit.com/blog/demo",
    )
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Hello",
        tags=["wappkit"],
        rewrite_source="llm",
        rewrite_strength="moderate",
    )

    assert publisher._should_publish_publicly(rewritten) is True


def test_normalize_blog_url_supports_domain_only() -> None:
    assert _normalize_blog_url("wappkit.blogspot.com") == "https://wappkit.blogspot.com/"


def test_blogger_refreshes_token_after_unauthorized(tmp_path, monkeypatch) -> None:
    config = build_config(tmp_path)
    publisher = BloggerPublisher(config)
    source = SourceArticle(
        candidate=ArticleCandidate(slug="demo", url="https://www.wappkit.com/blog/demo"),
        title="Demo",
        description="Demo description",
        markdown="Hello",
        canonical_url="https://www.wappkit.com/blog/demo",
    )
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Hello",
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
                raise Exception(f"{self.status_code} error")

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        calls.append({"method": method, "url": url, "headers": headers, "kwargs": kwargs})
        if url.endswith("/blogs/123456/posts") and len([c for c in calls if c["url"].endswith("/blogs/123456/posts")]) == 1:
            return DummyResponse(401, {"error": {"message": "Invalid Credentials"}})
        return DummyResponse(200, {"id": "123", "url": "https://wappkit.blogspot.com/2026/04/demo.html"})

    def fake_post(url, data=None, timeout=None, **kwargs):
        calls.append({"method": "post", "url": url, "data": data})
        return DummyResponse(200, {"access_token": "new-access-token", "expires_in": 3600, "token_type": "Bearer"})

    monkeypatch.setattr("app.platforms.blogger.requests.request", fake_request)
    monkeypatch.setattr("app.platforms.blogger.requests.post", fake_post)

    result = publisher.publish(rewritten, source)

    assert result.external_id == "123"
    assert any(call["url"] == "https://oauth2.googleapis.com/token" for call in calls)
    post_calls = [call for call in calls if call["url"].endswith("/blogs/123456/posts")]
    assert post_calls[-1]["headers"]["Authorization"] == "Bearer new-access-token"


def test_blogger_prefers_cached_state_over_bootstrap_tokens(tmp_path) -> None:
    config = build_config(tmp_path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "blogger-oauth.json").write_text(
        '{"access_token":"cached-access","refresh_token":"cached-refresh"}',
        encoding="utf-8",
    )

    publisher = BloggerPublisher(config)

    assert publisher._ensure_access_token() == "cached-access"
    assert publisher._refresh_token() == "cached-refresh"


def test_blogger_bootstraps_token_state_from_config_when_cache_missing(tmp_path) -> None:
    config = build_config(tmp_path)

    publisher = BloggerPublisher(config)

    assert publisher._ensure_access_token() == "test-token"
    assert publisher._refresh_token() == "refresh-token"
    state_file = config.data_dir / "blogger-oauth.json"
    assert state_file.exists()
    assert '"access_token": "test-token"' in state_file.read_text(encoding="utf-8")
