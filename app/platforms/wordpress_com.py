from __future__ import annotations

import json
from pathlib import Path

import markdown
import requests

from app.config import Config
from app.models import PublishResult, RewrittenArticle, SourceArticle


class WordpressComPublisher:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_root = "https://public-api.wordpress.com/rest/v1.1"

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        status = "publish" if self._should_publish_publicly(rewritten) else "draft"
        payload = {
            "title": rewritten.title,
            "content": self._markdown_to_html(rewritten.body_markdown),
            "status": status,
        }
        excerpt = (rewritten.description or "").strip()
        if excerpt:
            payload["excerpt"] = excerpt[:200]
        if rewritten.tags:
            payload["tags"] = ",".join(rewritten.tags[:10])
        categories = self.config.wordpress_default_categories or []
        if categories:
            payload["categories"] = ",".join(categories[:10])
        return payload

    def build_minimal_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        payload = self.build_payload(rewritten, source)
        return {
            "title": payload["title"],
            "content": payload["content"],
            "status": payload["status"],
        }

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if not self.config.wordpress_access_token:
            raise ValueError("WORDPRESS_ACCESS_TOKEN is required for publishing.")
        if not self.config.wordpress_site:
            raise ValueError("WORDPRESS_SITE is required for publishing.")

        payload = self.build_payload(rewritten, source)
        response = self._post_payload(payload)
        if response.status_code >= 400:
            minimal_payload = self.build_minimal_payload(rewritten, source)
            if minimal_payload != payload:
                response = self._post_payload(minimal_payload)
        self._raise_for_status_with_details(response)
        data = response.json()

        status = str(data.get("status") or "").strip().lower()
        return PublishResult(
            external_id=str(data.get("ID") or data.get("id") or ""),
            url=str(data.get("URL") or data.get("url") or "").strip() or None,
            raw_response=data,
            is_draft=status != "publish",
        )

    def save_preview(self, rewritten: RewrittenArticle, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / f"{source.candidate.slug}-wordpress-preview.html"
        payload_path = output_dir / f"{source.candidate.slug}-wordpress-payload.json"
        payload = self.build_payload(rewritten, source)
        preview_path.write_text(payload["content"], encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return preview_path

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.wordpress_access_token}",
            "Accept": "application/json",
        }

    def _post_payload(self, payload: dict) -> requests.Response:
        return requests.post(
            f"{self.api_root}/sites/{self.config.wordpress_site}/posts/new",
            data=payload,
            headers=self._headers(),
            timeout=self.config.request_timeout_seconds,
        )

    def _raise_for_status_with_details(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = self._extract_error_detail(response)
            if detail:
                raise requests.HTTPError(f"{exc} | response={detail}", response=response) from exc
            raise

    def _extract_error_detail(self, response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return (response.text or "").strip()[:500]
        if isinstance(data, dict):
            for key in ("message", "error", "error_description"):
                value = data.get(key)
                if value:
                    return str(value)[:500]
            return json.dumps(data, ensure_ascii=False)[:500]
        return str(data)[:500]

    def _should_publish_publicly(self, rewritten: RewrittenArticle) -> bool:
        if self.config.wordpress_publish_status != "published":
            return False
        if self.config.wordpress_require_llm_for_publication and rewritten.rewrite_source != "llm":
            return False
        return True

    def _markdown_to_html(self, body_markdown: str) -> str:
        return markdown.markdown(body_markdown, extensions=["extra", "sane_lists", "nl2br"])
