from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ArticleCandidate:
    slug: str
    url: str
    last_modified: str | None = None
    title: str | None = None
    description: str | None = None


@dataclass(slots=True)
class SourceArticle:
    candidate: ArticleCandidate
    title: str
    description: str
    markdown: str
    canonical_url: str
    published_at: str | None = None
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    image_url: str | None = None


@dataclass(slots=True)
class RewrittenArticle:
    title: str
    description: str
    body_markdown: str
    tags: list[str]


@dataclass(slots=True)
class PublishResult:
    external_id: str
    url: str
    raw_response: dict
