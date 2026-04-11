from pathlib import Path

from app.config import Config
from app.models import ArticleCandidate, RewrittenArticle, SourceArticle
from app.platforms.writeas import WriteasPublisher
from app.rewrite import WriteasRewriter
from app.store import DeliveryStore


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
        writeas_base_url="https://write.as",
        writeas_font="serif",
        writeas_language="en",
        writeas_require_llm_for_publication=False,
    )


def build_source_article() -> SourceArticle:
    return SourceArticle(
        candidate=ArticleCandidate(slug="demo-post", url="https://www.wappkit.com/blog/demo-post"),
        title="Demo Post",
        description="Demo description",
        markdown="## Section\n\nA paragraph with [a link](https://example.com).",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        published_at="2026-04-11T08:00:00Z",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )


def test_writeas_fallback_rewrite_uses_writeas_angle(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    rewriter = WriteasRewriter(config)

    rewritten = rewriter.rewrite(build_source_article())

    assert "Write.as adaptation" in rewritten.body_markdown
    assert "## What stood out" in rewritten.body_markdown
    assert "This Write.as version links back to the source." in rewritten.body_markdown
    assert rewritten.rewrite_source == "fallback"


def test_writeas_build_payload_uses_anonymous_post_shape(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    publisher = WriteasPublisher(config)
    source = build_source_article()
    rewritten = RewrittenArticle(
        title="A better demo post",
        description="Fresh description",
        body_markdown="## What stood out\n\nA paragraph.",
        tags=["wappkit", "reddittoolbox"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    payload = publisher.build_payload(rewritten, source)

    assert payload == {
        "body": "## What stood out\n\nA paragraph.",
        "title": "A better demo post",
        "font": "serif",
        "lang": "en",
        "created": "2026-04-11T08:00:00Z",
    }


def test_writeas_publish_parses_id_url_and_token_state(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    publisher = WriteasPublisher(config)
    source = build_source_article()
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Body paragraph.",
        tags=["wappkit"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    class DummyResponse:
        status_code = 201
        text = ""

        def json(self):
            return {
                "code": 201,
                "data": {
                    "id": "rf3t35fkax0aw",
                    "token": "secret-modify-token",
                    "appearance": "norm",
                    "language": "en",
                    "slug": None,
                },
            }

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url == "https://write.as/api/posts"
        assert json["title"] == "Demo"
        return DummyResponse()

    monkeypatch.setattr("app.platforms.writeas.requests.post", fake_post)

    result = publisher.publish(rewritten, source)
    state = publisher.extract_state(result)

    assert result.external_id == "rf3t35fkax0aw"
    assert result.url == "https://write.as/rf3t35fkax0aw"
    assert state["token"] == "secret-modify-token"
    assert state["url"] == "https://write.as/rf3t35fkax0aw"


def test_store_mark_success_persists_platform_state(tmp_path: Path) -> None:
    store = DeliveryStore(tmp_path / "data" / "delivery-state.sqlite3")
    store.mark_attempt(
        platform="writeas",
        source_slug="demo-post",
        source_url="https://www.wappkit.com/blog/demo-post",
        title="Demo Post",
        source_updated_at=None,
    )

    store.mark_success(
        "writeas",
        "demo-post",
        "rf3t35fkax0aw",
        "https://write.as/rf3t35fkax0aw",
        platform_state={"token": "secret-modify-token"},
    )

    with store._connect() as conn:
        row = conn.execute(
            "SELECT platform_state FROM deliveries WHERE platform = ? AND source_slug = ?",
            ("writeas", "demo-post"),
        ).fetchone()

    assert row is not None
    assert row["platform_state"] == '{"token": "secret-modify-token"}'


def test_writeas_publish_can_require_llm_rewrite(tmp_path: Path) -> None:
    config = build_config(tmp_path)
    config.writeas_require_llm_for_publication = True
    publisher = WriteasPublisher(config)

    try:
        publisher.publish(
            RewrittenArticle(
                title="Demo",
                description="Demo description",
                body_markdown="Body paragraph.",
                tags=["wappkit"],
                rewrite_source="fallback",
                rewrite_strength="minimal",
            ),
            build_source_article(),
        )
    except ValueError as exc:
        assert "WRITEAS_REQUIRE_LLM_FOR_PUBLICATION=1" in str(exc)
    else:
        raise AssertionError("Expected Write.as publish to reject fallback rewrite when llm is required.")
