from __future__ import annotations

import json
from pathlib import Path

import requests

from app.config import Config
from app.models import PublishResult, RewrittenArticle, SourceArticle


class DevtoPublisher:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_url = "https://dev.to/api/articles"

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        should_publish = self._should_publish_publicly(rewritten)
        payload = {
            "article": {
                "title": rewritten.title,
                "body_markdown": rewritten.body_markdown,
                "published": should_publish,
                "tags": rewritten.tags[:4],
                "description": rewritten.description[:200],
                "canonical_url": source.canonical_url,
            }
        }
        if source.image_url:
            payload["article"]["main_image"] = source.image_url
        return payload

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if not self.config.devto_api_key:
            raise ValueError("DEVTO_API_KEY is required for publishing.")

        payload = self.build_payload(rewritten, source)
        response = requests.post(
            self.api_url,
            json=payload,
            headers={
                "api-key": self.config.devto_api_key,
                "Accept": "application/vnd.forem.api-v1+json",
                "Content-Type": "application/json",
            },
            timeout=self.config.request_timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = self._extract_error_detail(response)
            canonical_url = (source.canonical_url or "").strip()
            if canonical_url and self._looks_like_duplicate_canonical_error(detail):
                existing = self._find_existing_article_by_canonical_url(canonical_url)
                if existing:
                    published = bool(existing.get("published"))
                    existing_url = str(existing.get("url") or "").strip() or None
                    if not published and existing_url and "temp-slug" in existing_url:
                        existing_url = None
                    return PublishResult(
                        external_id=str(existing.get("id") or ""),
                        url=existing_url,
                        is_draft=not published,
                        raw_response={"existing_article": existing, "reused_due_to": detail},
                    )
            if detail:
                raise requests.HTTPError(f"{exc} | response={detail}", response=response) from exc
            raise
        data = response.json()
        published = bool(data.get("published"))
        api_url = str(data.get("url") or "").strip() or None

        # DEV.to draft articles often return a temporary URL such as "...temp-slug-123".
        # That URL is not a stable public permalink, so we avoid treating it as a final link.
        if not published and api_url and "temp-slug" in api_url:
            api_url = None

        return PublishResult(
            external_id=str(data.get("id") or ""),
            url=api_url,
            is_draft=not published,
            raw_response=data,
        )

    def save_preview(self, rewritten: RewrittenArticle, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / f"{source.candidate.slug}-devto-preview.md"
        payload_path = output_dir / f"{source.candidate.slug}-devto-payload.json"

        payload = self.build_payload(rewritten, source)
        preview_path.write_text(rewritten.body_markdown, encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return preview_path

    def _should_publish_publicly(self, rewritten: RewrittenArticle) -> bool:
        if self.config.devto_publish_status != "published":
            return False
        if self.config.devto_require_llm_for_publication and rewritten.rewrite_source != "llm":
            return False
        return True

    def _headers(self) -> dict[str, str]:
        return {
            "api-key": self.config.devto_api_key or "",
            "Accept": "application/vnd.forem.api-v1+json",
            "Content-Type": "application/json",
        }

    def _find_existing_article_by_canonical_url(self, canonical_url: str) -> dict | None:
        page = 1
        while True:
            response = requests.get(
                "https://dev.to/api/articles/me/all",
                params={"per_page": 100, "page": page},
                headers=self._headers(),
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or not data:
                return None
            for article in data:
                if str((article or {}).get("canonical_url") or "").strip() == canonical_url:
                    return article
            if len(data) < 100:
                return None
            page += 1

    def _extract_error_detail(self, response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return (response.text or "").strip()[:500]
        if isinstance(data, dict):
            for key in ("error", "message", "detail"):
                value = data.get(key)
                if value:
                    return str(value)[:500]
            return json.dumps(data, ensure_ascii=False)[:500]
        return str(data)[:500]

    def _looks_like_duplicate_canonical_error(self, detail: str) -> bool:
        normalized = detail.lower()
        return "canonical url" in normalized and "already been taken" in normalized
