from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import markdown
import requests

from app.config import Config
from app.models import PublishResult, RewrittenArticle, SourceArticle


class BloggerPublisher:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_root = "https://www.googleapis.com/blogger/v3"

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        return {
            "kind": "blogger#post",
            "title": rewritten.title,
            "content": self._markdown_to_html(rewritten.body_markdown),
            "labels": (rewritten.tags or [])[:6],
        }

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if not self.config.blogger_access_token:
            raise ValueError("BLOGGER_ACCESS_TOKEN is required for publishing.")

        blog_id = self._resolve_blog_id()
        payload = self.build_payload(rewritten, source)
        is_draft = not self._should_publish_publicly(rewritten)

        response = requests.post(
            f"{self.api_root}/blogs/{blog_id}/posts",
            params={"isDraft": str(is_draft).lower()},
            json=payload,
            headers=self._headers(),
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        return PublishResult(
            external_id=str(data.get("id") or ""),
            url=str(data.get("url") or "").strip() or None,
            raw_response=data,
            is_draft=is_draft,
        )

    def save_preview(self, rewritten: RewrittenArticle, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / f"{source.candidate.slug}-blogger-preview.html"
        payload_path = output_dir / f"{source.candidate.slug}-blogger-payload.json"

        payload = self.build_payload(rewritten, source)
        preview_path.write_text(payload["content"], encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return preview_path

    def _resolve_blog_id(self) -> str:
        if self.config.blogger_blog_id:
            return self.config.blogger_blog_id.strip()
        if not self.config.blogger_blog_url:
            raise ValueError("Set BLOGGER_BLOG_ID or BLOGGER_BLOG_URL.")

        normalized_url = _normalize_blog_url(self.config.blogger_blog_url)
        response = requests.get(
            f"{self.api_root}/blogs/byurl",
            params={"url": normalized_url},
            headers=self._headers(),
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        blog_id = str(data.get("id") or "").strip()
        if not blog_id:
            raise ValueError(f"Unable to resolve Blogger blog id from {normalized_url}")
        return blog_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.blogger_access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _should_publish_publicly(self, rewritten: RewrittenArticle) -> bool:
        if self.config.blogger_publish_status != "published":
            return False
        if self.config.blogger_require_llm_for_publication and rewritten.rewrite_source != "llm":
            return False
        return True

    def _markdown_to_html(self, body_markdown: str) -> str:
        return markdown.markdown(body_markdown, extensions=["extra", "sane_lists", "nl2br"])


def _normalize_blog_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return raw
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    normalized = f"{scheme}://{netloc}{path}".rstrip("/")
    return normalized + "/"
