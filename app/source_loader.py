from __future__ import annotations

import re

import requests
import yaml
from bs4 import BeautifulSoup

from app.config import Config
from app.models import ArticleCandidate, SourceArticle


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def load_source_article(config: Config, candidate: ArticleCandidate) -> SourceArticle:
    try:
        return _load_from_github_raw(config, candidate)
    except Exception:
        return _load_from_webpage(config, candidate)


def _load_from_github_raw(config: Config, candidate: ArticleCandidate) -> SourceArticle:
    raw_url = f"{config.content_raw_base_url}/{candidate.slug}.mdx"
    response = requests.get(raw_url, timeout=config.request_timeout_seconds)
    response.raise_for_status()

    metadata, body = _parse_frontmatter(response.text)
    title = str(metadata.get("title") or candidate.title or candidate.slug.replace("-", " ").title()).strip()
    description = str(metadata.get("description") or candidate.description or "").strip()
    categories = [str(item).strip() for item in metadata.get("categories", []) if str(item).strip()]
    tags = [str(item).strip() for item in metadata.get("tags", []) if str(item).strip()]
    image = metadata.get("image")

    image_url = None
    if isinstance(image, str) and image.strip():
        image_url = _absolute_url(config, image.strip())

    markdown = _normalize_markdown(body, config)

    return SourceArticle(
        candidate=candidate,
        title=title,
        description=description,
        markdown=markdown,
        canonical_url=candidate.url,
        published_at=str(metadata.get("date") or candidate.last_modified or ""),
        categories=categories,
        tags=tags,
        image_url=image_url,
    )


def _load_from_webpage(config: Config, candidate: ArticleCandidate) -> SourceArticle:
    response = requests.get(candidate.url, timeout=config.request_timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find("main")
    title = _get_meta_title(soup) or candidate.title or candidate.slug.replace("-", " ").title()
    description = _get_meta_description(soup) or candidate.description or ""

    content_lines: list[str] = []
    if main is not None:
        for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            if text in {
                "Back to Blog",
                "More articles",
                "From Wappkit",
                "View Product",
                "Download Free Version",
            }:
                continue
            if text.startswith("More in "):
                continue
            content_lines.append(text)

    markdown = _normalize_markdown("\n\n".join(content_lines).strip(), config)

    return SourceArticle(
        candidate=candidate,
        title=title.strip(),
        description=description.strip(),
        markdown=markdown,
        canonical_url=candidate.url,
        published_at=candidate.last_modified,
        categories=[],
        tags=[],
        image_url=None,
    )


def _parse_frontmatter(raw_text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(raw_text)
    if not match:
        return {}, raw_text.strip()
    metadata_text, body = match.groups()
    metadata = yaml.safe_load(metadata_text) or {}
    return metadata, body.strip()


def _normalize_markdown(markdown: str, config: Config) -> str:
    markdown = markdown.replace("\r\n", "\n").strip()
    markdown = re.sub(r"(?m)^import .*$", "", markdown)
    markdown = re.sub(r"(?m)^export .*$", "", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(
        r"\]\((/[^)]+)\)",
        lambda match: f"]({_absolute_url(config, match.group(1))})",
        markdown,
    )
    return markdown.strip()


def _absolute_url(config: Config, path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return f"{config.site_url}{path_or_url if path_or_url.startswith('/') else '/' + path_or_url}"


def _get_meta_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"property": "og:title"}) or soup.find("title")
    if tag is None:
        return None
    if tag.name == "meta":
        return tag.get("content")
    return tag.get_text(strip=True)


def _get_meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if tag is None:
        return None
    return tag.get("content")
