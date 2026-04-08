from app.config import Config
from app.models import ArticleCandidate, RewrittenArticle, SourceArticle
from app.platforms.wordpress_com import WordpressComPublisher
import requests


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


def test_wordpress_retries_with_minimal_payload_on_bad_request(tmp_path, monkeypatch) -> None:
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
        body_markdown="Hello",
        tags=["wappkit"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    calls = []

    class DummyResponse:
        def __init__(self, status_code: int, data: dict, text: str = "") -> None:
            self.status_code = status_code
            self._data = data
            self.text = text

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError("400 Client Error: Bad Request for url: test", response=self)

    def fake_post(url, data, headers, timeout):
        calls.append(data.copy())
        if len(calls) == 1:
            return DummyResponse(400, {"message": "Invalid categories"})
        return DummyResponse(200, {"ID": 123, "status": "draft", "URL": "https://example.wordpress.com/demo"})

    monkeypatch.setattr("app.platforms.wordpress_com.requests.post", fake_post)

    result = publisher.publish(rewritten, source)

    assert len(calls) == 2
    assert "categories" in calls[0]
    assert "tags" in calls[0]
    assert calls[1] == {
        "title": "Demo",
        "content": "<p>Hello</p>",
        "status": "draft",
    }
    assert result.is_draft is True
