from __future__ import annotations

import re

import requests
import yaml
from bs4 import BeautifulSoup

from app.config import Config
from app.models import ArticleCandidate, SourceArticle


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
RAW_EXTENSIONS = ("mdx", "md")
REQUEST_HEADERS = {
    "User-Agent": "wappkit-social-distributor/1.0 (+https://www.wappkit.com)",
    "Accept": "text/plain, text/markdown, text/x-markdown, application/xhtml+xml, text/html;q=0.9, */*;q=0.8",
}


def load_source_article(config: Config, candidate: ArticleCandidate) -> SourceArticle:
    try:
        return _load_from_github_raw(config, candidate)
    except Exception:
        return _load_from_webpage(config, candidate)


def _load_from_github_raw(config: Config, candidate: ArticleCandidate) -> SourceArticle:
    last_error: Exception | None = None
    response = None
    for extension in RAW_EXTENSIONS:
        raw_url = f"{config.content_raw_base_url}/{candidate.slug}.{extension}"
        try:
            response = _get(raw_url, config.request_timeout_seconds)
            response.raise_for_status()
            break
        except Exception as exc:
            last_error = exc
            response = None

    if response is None:
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Unable to load raw article for slug: {candidate.slug}")

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
    response = _get(candidate.url, config.request_timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find("main")
    title = _clean_title(_get_meta_title(soup) or candidate.title or candidate.slug.replace("-", " ").title())
    description = _get_meta_description(soup) or candidate.description or ""

    content_lines: list[str] = []
    if main is not None:
        for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            rendered = _render_webpage_block(tag.name, text)
            if rendered:
                content_lines.append(rendered)

    markdown = _normalize_markdown(
        _clean_webpage_markdown(content_lines, candidate.title or title),
        config,
    )

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


def _get(url: str, timeout_seconds: int) -> requests.Response:
    last_error: Exception | None = None
    for _ in range(2):
        try:
            return requests.get(url, timeout=timeout_seconds, headers=REQUEST_HEADERS)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Request failed: {url}")


def _render_webpage_block(tag_name: str, text: str) -> str | None:
    if tag_name == "h1":
        return f"# {text}"
    if tag_name == "h2":
        return f"## {text}"
    if tag_name == "h3":
        return f"### {text}"
    if tag_name == "li":
        return f"- {text}"
    if tag_name == "p":
        return text
    return None


def _clean_webpage_markdown(blocks: list[str], title: str) -> str:
    if not blocks:
        return ""

    normalized_title = title.strip().lower()
    start_index = 0
    title_hits = [index for index, block in enumerate(blocks) if block.strip().lower() == f"# {normalized_title}"]
    if len(title_hits) >= 2:
        start_index = title_hits[1]
    elif title_hits:
        start_index = title_hits[0]

    stop_markers = {
        "from wappkit",
        "support",
        "products",
        "platform",
    }
    blocked_exact = {
        "wappkit blog",
        "back to blog",
        "more articles",
        "article context",
        "authors",
        "wappkit team",
        "@ wappkit",
        "@",
        "view product",
        "download free version",
        "live tool",
        "desktop",
        "why it fits this blog",
        "guides",
        "long-form guide",
    }
    blocked_substrings = (
        "practical content, product pages, activation docs",
        "start with the reddit collector for free",
        "license retrieval, and in-app activation connected",
        "read the guide inside the same wappkit surface",
    )

    cleaned: list[str] = []
    seen_tail: list[str] = []

    for block in blocks[start_index:]:
        plain = re.sub(r"^#{1,3}\s+", "", block).strip()
        normalized = plain.lower()

        if normalized in stop_markers:
            break
        if not plain:
            continue
        if normalized in blocked_exact:
            continue
        if normalized.startswith("more in "):
            continue
        if any(token in normalized for token in blocked_substrings):
            continue

        if seen_tail and seen_tail[-1] == block:
            continue

        cleaned.append(block)
        seen_tail.append(block)

    return "\n\n".join(cleaned).strip()


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


def _clean_title(title: str) -> str:
    cleaned = re.sub(r"\s*\|\s*Wappkit Blog\s*$", "", title, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*\|\s*Wappkit\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _get_meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if tag is None:
        return None
    return tag.get("content")
