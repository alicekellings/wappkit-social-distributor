from pathlib import Path

from app.config import Config
from app.models import ArticleCandidate, SourceArticle
from app.rewrite import DevtoRewriter


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
