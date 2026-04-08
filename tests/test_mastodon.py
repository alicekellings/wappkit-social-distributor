from pathlib import Path

from app.config import Config
from app.models import ArticleCandidate, SourceArticle
from app.platforms.mastodon import MastodonPublisher
from app.rewrite import MastodonRewriter


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
        mastodon_base_url="https://mastodon.social",
        mastodon_access_token="test-token",
        mastodon_visibility="unlisted",
        mastodon_language="en",
        mastodon_require_llm_for_publication=True,
    )


def test_mastodon_fallback_rewrite_is_short(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = MastodonRewriter(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description for a longer article that should still fit a short social summary.",
        markdown="Body paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    rewritten = rewriter.rewrite(article)

    assert len(rewritten.body_markdown) <= 450
    assert "https://www.wappkit.com/blog/demo-post" in rewritten.body_markdown
    assert "Demo Post" not in rewritten.body_markdown.split("\n\n", 1)[0]
    assert "The practical takeaway:" in rewritten.body_markdown
    assert rewritten.rewrite_source == "fallback"


def test_mastodon_fallback_rewrite_feels_like_social_summary(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = MastodonRewriter(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="How to Validate a Reddit Tool Idea",
        description="A step-by-step look at checking demand before you build too much.",
        markdown="Body paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox", "saas"],
    )

    rewritten = rewriter.rewrite(article)

    prefix = rewritten.body_markdown.split("\n\n", 1)[0]
    assert prefix.endswith(".")
    assert "Here is" not in rewritten.body_markdown
    assert "Originally published" not in rewritten.body_markdown
    assert "#reddittoolbox" in rewritten.body_markdown.lower() or "#saas" in rewritten.body_markdown.lower()


def test_mastodon_publisher_builds_payload(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    publisher = MastodonPublisher(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="Body paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
    )
    rewritten = MastodonRewriter(config).rewrite(article)

    payload = publisher.build_payload(rewritten, article)

    assert payload["visibility"] == "unlisted"
    assert payload["language"] == "en"
    assert payload["status"]
