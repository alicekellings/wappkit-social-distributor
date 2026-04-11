from __future__ import annotations

import json
from pathlib import Path

import requests

from app.config import Config
from app.models import PublishResult, RewrittenArticle, SourceArticle


class WriteasPublisher:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_root = f"{self.config.writeas_base_url.rstrip('/')}/api"

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        payload = {
            "body": rewritten.body_markdown.strip(),
            "title": rewritten.title.strip(),
            "font": self.config.writeas_font,
            "lang": self.config.writeas_language,
        }
        if source.published_at:
            payload["created"] = source.published_at
        return payload

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if self.config.writeas_require_llm_for_publication and rewritten.rewrite_source != "llm":
            raise ValueError("Write.as anonymous publishing requires an llm rewrite when WRITEAS_REQUIRE_LLM_FOR_PUBLICATION=1.")

        payload = self.build_payload(rewritten, source)
        response = requests.post(
            f"{self.api_root}/posts",
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self.config.request_timeout_seconds,
        )
        self._raise_for_status_with_details(response)
        data = response.json()
        post = data.get("data") or {}
        post_id = str(post.get("id") or "").strip()
        return PublishResult(
            external_id=post_id,
            url=self._build_post_url(post_id),
            raw_response=data,
            is_draft=False,
        )

    def save_preview(self, rewritten: RewrittenArticle, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / f"{source.candidate.slug}-writeas-preview.md"
        payload_path = output_dir / f"{source.candidate.slug}-writeas-payload.json"
        payload = self.build_payload(rewritten, source)
        preview_path.write_text(rewritten.body_markdown, encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return preview_path

    def extract_state(self, result: PublishResult) -> dict[str, str]:
        post = result.raw_response.get("data") or {}
        state: dict[str, str] = {}
        for key in ("id", "token", "slug", "appearance", "language"):
            value = post.get(key)
            if value is None:
                continue
            state[key] = str(value)
        if result.url:
            state["url"] = result.url
        return state

    def _build_post_url(self, post_id: str) -> str | None:
        if not post_id:
            return None
        return f"{self.config.writeas_base_url.rstrip('/')}/{post_id}"

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
            for key in ("error_msg", "error", "message"):
                value = data.get(key)
                if value:
                    return str(value)[:500]
            return json.dumps(data, ensure_ascii=False)[:500]
        return str(data)[:500]
