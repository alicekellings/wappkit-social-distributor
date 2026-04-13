from app.config import Config
from app.models import ArticleCandidate, RewrittenArticle, SourceArticle
from app.platforms.devto import DevtoPublisher
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
        devto_api_key="test-key",
        devto_publish_status="draft",
        devto_default_tags=["wappkit", "software", "saas"],
        devto_require_llm_for_publication=True,
    )


def test_build_payload_marks_draft_mode(tmp_path) -> None:
    config = build_config(tmp_path)
    publisher = DevtoPublisher(config)
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

    payload = publisher.build_payload(rewritten, source)

    assert payload["article"]["published"] is False
    assert payload["article"]["canonical_url"] == "https://www.wappkit.com/blog/demo"


def test_build_payload_allows_publication_for_llm_rewrite(tmp_path) -> None:
    config = build_config(tmp_path)
    config.devto_publish_status = "published"
    publisher = DevtoPublisher(config)
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

    assert payload["article"]["published"] is True


def test_build_payload_forces_draft_when_fallback_rewrite(tmp_path) -> None:
    config = build_config(tmp_path)
    config.devto_publish_status = "published"
    publisher = DevtoPublisher(config)
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

    payload = publisher.build_payload(rewritten, source)

    assert payload["article"]["published"] is False


def test_publish_reuses_existing_article_when_canonical_url_exists(tmp_path, monkeypatch) -> None:
    config = build_config(tmp_path)
    publisher = DevtoPublisher(config)
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

    class DummyResponse:
        def __init__(self, status_code: int, data):
            self.status_code = status_code
            self._data = data
            self.text = str(data)

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} error", response=self)

    def fake_post(url, json=None, headers=None, timeout=None):
        return DummyResponse(
            422,
            {"error": "Canonical url has already been taken. Email support@dev.to for further details."},
        )

    def fake_get(url, params=None, headers=None, timeout=None):
        assert params == {"per_page": 100, "page": 1}
        return DummyResponse(
            200,
            [
                {
                    "id": 123,
                    "canonical_url": "https://www.wappkit.com/blog/demo",
                    "url": "https://dev.to/example/demo-123",
                    "published": False,
                }
            ],
        )

    monkeypatch.setattr("app.platforms.devto.requests.post", fake_post)
    monkeypatch.setattr("app.platforms.devto.requests.get", fake_get)

    result = publisher.publish(rewritten, source)

    assert result.external_id == "123"
    assert result.url == "https://dev.to/example/demo-123"
    assert result.is_draft is True
