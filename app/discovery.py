from __future__ import annotations

from xml.etree import ElementTree

import feedparser
import requests

from app.config import Config
from app.models import ArticleCandidate


def discover_articles(config: Config, limit: int = 10) -> list[ArticleCandidate]:
    rss_candidates = _discover_from_rss(config)
    if rss_candidates:
        return rss_candidates[:limit]
    return _discover_from_sitemap(config)[:limit]


def get_candidate_by_slug(config: Config, slug: str) -> ArticleCandidate:
    for candidate in _discover_from_sitemap(config):
        if candidate.slug == slug:
            return candidate
    return ArticleCandidate(
        slug=slug,
        url=f"{config.site_url}/blog/{slug}",
        last_modified=None,
    )


def _discover_from_rss(config: Config) -> list[ArticleCandidate]:
    try:
        response = requests.get(config.rss_url, timeout=config.request_timeout_seconds)
        response.raise_for_status()
        parsed = feedparser.parse(response.text)
    except Exception:
        return []

    if not getattr(parsed, "entries", None):
        return []

    candidates: list[ArticleCandidate] = []
    for entry in parsed.entries:
        link = getattr(entry, "link", "") or ""
        if "/blog/" not in link:
            continue
        slug = link.rstrip("/").split("/")[-1]
        candidates.append(
            ArticleCandidate(
                slug=slug,
                url=link,
                last_modified=getattr(entry, "published", None) or getattr(entry, "updated", None),
                title=getattr(entry, "title", None),
                description=getattr(entry, "summary", None),
            )
        )
    return candidates


def _discover_from_sitemap(config: Config) -> list[ArticleCandidate]:
    response = requests.get(config.sitemap_url, timeout=config.request_timeout_seconds)
    response.raise_for_status()

    root = ElementTree.fromstring(response.text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    candidates: list[ArticleCandidate] = []

    for url_node in root.findall("sm:url", namespace):
        loc_node = url_node.find("sm:loc", namespace)
        if loc_node is None or not loc_node.text:
            continue
        loc = loc_node.text.strip()
        if "/blog/" not in loc or "/blog/category/" in loc:
            continue

        lastmod_node = url_node.find("sm:lastmod", namespace)
        slug = loc.rstrip("/").split("/")[-1]
        candidates.append(
            ArticleCandidate(
                slug=slug,
                url=loc,
                last_modified=lastmod_node.text.strip() if lastmod_node is not None and lastmod_node.text else None,
            )
        )

    candidates.sort(key=lambda item: item.last_modified or "", reverse=True)
    return candidates
