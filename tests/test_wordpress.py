from app.config import Config
from app.models import ArticleCandidate, RewrittenArticle, SourceArticle
from app.platforms.wordpress_com import WordpressComPublisher


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
        blogger_access_token=None,
        blogger_blog_id=None,
        blogger_blog_url=None,
        blogger_publish_status="draft",
        blogger_default_labels=["wappkit", "blog", "software"],
        blogger_require_llm_for_publication=True,
        wordpress_access_token="test-token",
        wordpress_site="blogxblog2.wordpress.com",
        wordpress_publish_status="draft",
        wordpress_default_tags=["wappkit", "blog", "software"],
        wordpress_default_categories=["Wappkit"],
        wordpress_require_llm_for_publication=True,
    )


def test_wordpress_build_payload_uses_draft_status(tmp_path) -> None:
    config = build_config(tmp_path)
    publisher = WordpressComPublisher(config)
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
        body_markdown="## Section\n\nHello",
        tags=["wappkit"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    payload = publisher.build_payload(rewritten, source)

    assert payload["status"] == "draft"
    assert "<h2>Section</h2>" in payload["content"]


def test_wordpress_llm_rewrite_allows_publish(tmp_path) -> None:
    config = build_config(tmp_path)
    config.wordpress_publish_status = "published"
    publisher = WordpressComPublisher(config)
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

    payload = publisher.build_payload(rewritten, source)

    assert payload["status"] == "publish"
