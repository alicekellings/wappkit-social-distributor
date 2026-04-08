from pathlib import Path

from app.config import Config
from app.models import ArticleCandidate, SourceArticle
from app.rewrite import BloggerRewriter, DevtoRewriter, WordpressRewriter


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
    )


def test_fallback_rewrite_adds_origin_note_and_strips_duplicate_h1(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = DevtoRewriter(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="# Demo Post\n\nRead more in [Download](https://www.wappkit.com/download).",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    rewritten = rewriter.rewrite(article)

    assert "Originally published on [Wappkit]" in rewritten.body_markdown
    assert "https://www.wappkit.com/blog/demo-post" in rewritten.body_markdown
    assert "# Demo Post" not in rewritten.body_markdown
    assert "DEV.to-friendly version" in rewritten.body_markdown
    assert "## Practical takeaway" in rewritten.body_markdown
    assert rewritten.tags
    assert rewritten.rewrite_source == "fallback"
    assert rewritten.rewrite_strength == "minimal"


def test_fallback_rewrite_strips_multiple_leading_h1_blocks(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = DevtoRewriter(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="# Demo Post\n\n# Demo Post\n\nBody paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    rewritten = rewriter.rewrite(article)

    assert rewritten.body_markdown.count("# Demo Post") == 0
    assert "Body paragraph." in rewritten.body_markdown
    assert rewritten.rewrite_source == "fallback"


def test_blogger_fallback_rewrite_uses_blogger_intro(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = BloggerRewriter(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="# Demo Post\n\nBody paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    rewritten = rewriter.rewrite(article)

    assert "Blogger-friendly adaptation" in rewritten.body_markdown
    assert "This Blogger version links back to the source." in rewritten.body_markdown
    assert "## Quick steps" in rewritten.body_markdown
    assert rewritten.rewrite_source == "fallback"


def test_wordpress_fallback_rewrite_uses_wordpress_angle(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = WordpressRewriter(config)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="# Demo Post\n\nBody paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    rewritten = rewriter.rewrite(article)

    assert "WordPress-friendly adaptation" in rewritten.body_markdown
    assert "This WordPress.com version links back to the source." in rewritten.body_markdown
    assert "## Tradeoffs to keep in mind" in rewritten.body_markdown
    assert rewritten.rewrite_source == "fallback"


def test_platform_fallbacks_use_distinct_angles(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="# Demo Post\n\nBody paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    devto = DevtoRewriter(config).rewrite(article)
    blogger = BloggerRewriter(config).rewrite(article)
    wordpress = WordpressRewriter(config).rewrite(article)

    assert "## Practical takeaway" in devto.body_markdown
    assert "## Quick steps" in blogger.body_markdown
    assert "## Tradeoffs to keep in mind" in wordpress.body_markdown
    assert devto.body_markdown != blogger.body_markdown
    assert blogger.body_markdown != wordpress.body_markdown
    assert devto.body_markdown != wordpress.body_markdown


def test_llm_rewrite_appends_platform_specific_section_when_missing(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = DevtoRewriter(config)
    rewriter.router.candidates = [object()]
    rewriter.router.client = object()
    article = SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="# Demo Post\n\nBody paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )

    rewriter.router.complete_json = lambda **kwargs: {
        "title": "A Better Demo Post",
        "description": "Fresh description",
        "body_markdown": "## New framing\n\nFresh text only.",
        "tags": ["demo"],
    }

    rewritten = rewriter.rewrite(article)

    assert rewritten.rewrite_source == "llm"
    assert "## Practical takeaway" in rewritten.body_markdown
    assert "This DEV.to version links back to the source." in rewritten.body_markdown
