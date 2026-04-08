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
