from __future__ import annotations

import json
from pathlib import Path

import requests

from app.config import Config
from app.models import PublishResult, RewrittenArticle, SourceArticle


class MastodonPublisher:
    def __init__(self, config: Config) -> None:
        self.config = config

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        return {
            "status": rewritten.body_markdown,
            "visibility": self.config.mastodon_visibility,
            "language": self.config.mastodon_language,
        }

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if not self.config.mastodon_base_url:
            raise ValueError("MASTODON_BASE_URL is required for publishing.")
        if not self.config.mastodon_access_token:
            raise ValueError("MASTODON_ACCESS_TOKEN is required for publishing.")
        if self.config.mastodon_require_llm_for_publication and rewritten.rewrite_source != "llm":
            raise ValueError("Mastodon publishing requires an llm rewrite when MASTODON_REQUIRE_LLM_FOR_PUBLICATION=1.")

        payload = self.build_payload(rewritten, source)
        response = requests.post(
            f"{self.config.mastodon_base_url.rstrip('/')}/api/v1/statuses",
            data=payload,
            headers=self._headers(),
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return PublishResult(
            external_id=str(data.get("id") or ""),
            url=str(data.get("url") or "").strip() or None,
            raw_response=data,
            is_draft=False,
        )

    def save_preview(self, rewritten: RewrittenArticle, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / f"{source.candidate.slug}-mastodon-preview.txt"
        payload_path = output_dir / f"{source.candidate.slug}-mastodon-payload.json"
        payload = self.build_payload(rewritten, source)
        preview_path.write_text(rewritten.body_markdown, encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return preview_path

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.mastodon_access_token}",
            "Accept": "application/json",
        }
