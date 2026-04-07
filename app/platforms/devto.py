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
        payload = {
            "article": {
                "title": rewritten.title,
                "body_markdown": rewritten.body_markdown,
                "published": self.config.devto_publish_status == "published",
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
                "Content-Type": "application/json",
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return PublishResult(
            external_id=str(data.get("id") or ""),
            url=str(data.get("url") or ""),
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
