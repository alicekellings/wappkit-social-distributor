from pathlib import Path

import requests

from app.config import Config
from app.models import ArticleCandidate, SourceArticle
from app.platform_health import verify_platforms
from app.platforms.gitbook import GitbookPublisher


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
        gitbook_token="gb_api_test",
        gitbook_org_id="org_123",
        gitbook_site_id="site_456",
        gitbook_publish_status="published",
        gitbook_hidden=False,
        gitbook_import_enhance=False,
    )


def build_source_article() -> SourceArticle:
    return SourceArticle(
        candidate=ArticleCandidate(
            slug="demo-post",
            url="https://www.wappkit.com/blog/demo-post",
            last_modified="2026-04-12T08:00:00Z",
        ),
        title="Demo Post",
        description="Demo description",
        markdown="## Section\n\nA paragraph.",
        canonical_url="https://www.wappkit.com/blog/demo-post",
        published_at="2026-04-11T08:00:00Z",
        categories=["guides"],
        tags=["reddit-toolbox"],
    )


class DummyResponse:
    def __init__(self, status_code: int, data: dict | list | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("No JSON payload")
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


def test_gitbook_publish_creates_visible_published_site_space(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    publisher = GitbookPublisher(config)
    source = build_source_article()
    requests_seen: list[tuple[str, str, dict | None]] = []
    list_pages_calls = 0

    def fake_request(method, url, headers=None, timeout=None, json=None):
        nonlocal list_pages_calls
        requests_seen.append((method.lower(), url, json))
        if method.lower() == "post" and url.endswith("/orgs/org_123/spaces"):
            assert len(json["title"]) <= 50
            return DummyResponse(201, {"id": "space_1", "title": "Demo Post", "urls": {"app": "https://app.gitbook.com/s/space_1/"}})
        if method.lower() == "get" and url.endswith("/spaces/space_1/content/pages"):
            list_pages_calls += 1
            if list_pages_calls == 1:
                return DummyResponse(200, {"pages": [{"id": "default_page", "path": "page", "pages": []}]})
            return DummyResponse(
                200,
                {
                    "pages": [
                        {"id": "default_page", "path": "page", "pages": []},
                        {
                            "id": "imported_page",
                            "title": "Demo Post",
                            "path": "demo-post-or-wappkit-blog",
                            "slug": "demo-post-or-wappkit-blog",
                            "pages": [],
                        },
                    ]
                },
            )
        if method.lower() == "post" and url.endswith("/org/org_123/imports"):
            assert json == {
                "source": {"type": "website", "url": "https://www.wappkit.com/blog/demo-post"},
                "target": {"space": "space_1"},
                "enhance": False,
            }
            return DummyResponse(200, {"id": "import_1", "status": "pending"})
        if method.lower() == "post" and url.endswith("/orgs/org_123/sites/site_456/site-spaces"):
            assert json == {"spaceId": "space_1"}
            return DummyResponse(201, {"id": "sitesp_1", "path": "draft-space"})
        if method.lower() == "patch" and url.endswith("/orgs/org_123/sites/site_456/site-spaces/sitesp_1"):
            assert json == {
                "path": "demo-post",
                "hidden": False,
                "draft": False,
            }
            return DummyResponse(
                200,
                {
                    "id": "sitesp_1",
                    "path": "demo-post",
                    "draft": False,
                    "hidden": False,
                    "urls": {"published": "https://estar-1.gitbook.io/estar-docs/demo-post/"},
                },
            )
        raise AssertionError(f"Unexpected request {method} {url}")

    monkeypatch.setattr("app.platforms.gitbook.requests.request", fake_request)
    monkeypatch.setattr("app.platforms.gitbook.time.sleep", lambda _: None)

    result = publisher.publish(source)
    state = publisher.extract_state(result)

    assert result.external_id == "sitesp_1"
    assert result.url == "https://estar-1.gitbook.io/estar-docs/demo-post/demo-post-or-wappkit-blog"
    assert result.is_draft is False
    assert state["space_id"] == "space_1"
    assert state["site_space_path"] == "demo-post"
    assert state["page_path"] == "demo-post-or-wappkit-blog"
    assert any(url.endswith("/org/org_123/imports") for _, url, _ in requests_seen)


def test_gitbook_publish_cleans_up_created_resources_on_failure(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)
    publisher = GitbookPublisher(config)
    source = build_source_article()
    deleted: list[tuple[str, str]] = []
    list_pages_calls = 0

    def fake_request(method, url, headers=None, timeout=None, json=None):
        nonlocal list_pages_calls
        if method.lower() == "post" and url.endswith("/orgs/org_123/spaces"):
            return DummyResponse(201, {"id": "space_1"})
        if method.lower() == "get" and url.endswith("/spaces/space_1/content/pages"):
            list_pages_calls += 1
            if list_pages_calls == 1:
                return DummyResponse(200, {"pages": [{"id": "default_page", "path": "page", "pages": []}]})
            return DummyResponse(
                200,
                {"pages": [{"id": "imported_page", "path": "demo-post-or-wappkit-blog", "pages": []}]},
            )
        if method.lower() == "post" and url.endswith("/org/org_123/imports"):
            return DummyResponse(200, {"id": "import_1", "status": "pending"})
        if method.lower() == "post" and url.endswith("/orgs/org_123/sites/site_456/site-spaces"):
            return DummyResponse(201, {"id": "sitesp_1"})
        if method.lower() == "patch" and url.endswith("/orgs/org_123/sites/site_456/site-spaces/sitesp_1"):
            return DummyResponse(500, {"error": {"message": "patch failed"}})
        if method.lower() == "delete":
            deleted.append((method.lower(), url))
            return DummyResponse(205, None)
        raise AssertionError(f"Unexpected request {method} {url}")

    monkeypatch.setattr("app.platforms.gitbook.requests.request", fake_request)
    monkeypatch.setattr("app.platforms.gitbook.time.sleep", lambda _: None)

    try:
        publisher.publish(source)
    except requests.HTTPError as exc:
        assert "patch failed" in str(exc)
    else:
        raise AssertionError("Expected GitBook publish to fail when site-space patch fails.")

    assert ("delete", "https://api.gitbook.com/v1/orgs/org_123/sites/site_456/site-spaces/sitesp_1") in deleted
    assert ("delete", "https://api.gitbook.com/v1/spaces/space_1") in deleted


def test_verify_platforms_can_check_gitbook_credentials(tmp_path: Path, monkeypatch) -> None:
    config = build_config(tmp_path)

    monkeypatch.setattr(
        "app.platform_health.GitbookPublisher.get_user",
        lambda self: {"displayName": "Tester"},
    )
    monkeypatch.setattr(
        "app.platform_health.GitbookPublisher.get_site",
        lambda self: {"title": "Estar Docs"},
    )
    monkeypatch.setattr(
        "app.platform_health.GitbookPublisher.list_site_spaces",
        lambda self: [{"id": "sitesp_1"}, {"id": "sitesp_2"}],
    )

    result = verify_platforms(config, platforms=["gitbook"])[0]

    assert result.ok is True
    assert result.platform == "gitbook"
    assert "site=Estar Docs" in result.detail
    assert "site_spaces=2" in result.detail
