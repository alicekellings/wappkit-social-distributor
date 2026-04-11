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
        self.token_url = "https://oauth2.googleapis.com/token"
        self.token_state_path = self.config.data_dir / "blogger-oauth.json"
        self._token_state = self._load_token_state()
        self._bootstrap_token_state()

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        return {
            "kind": "blogger#post",
            "title": rewritten.title,
            "content": self._markdown_to_html(rewritten.body_markdown),
            "labels": (rewritten.tags or [])[:6],
        }

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if not self._ensure_access_token():
            raise ValueError("BLOGGER_ACCESS_TOKEN is required for publishing.")

        blog_id = self._resolve_blog_id()
        payload = self.build_payload(rewritten, source)
        is_draft = not self._should_publish_publicly(rewritten)

        response = self._authorized_request(
            "post",
            f"{self.api_root}/blogs/{blog_id}/posts",
            params={"isDraft": str(is_draft).lower()},
            json=payload,
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
        response = self._authorized_request(
            "get",
            f"{self.api_root}/blogs/byurl",
            params={"url": normalized_url},
        )
        response.raise_for_status()
        data = response.json()
        blog_id = str(data.get("id") or "").strip()
        if not blog_id:
            raise ValueError(f"Unable to resolve Blogger blog id from {normalized_url}")
        return blog_id

    def _headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _authorized_request(self, method: str, url: str, **kwargs) -> requests.Response:
        access_token = self._ensure_access_token()
        if not access_token:
            raise ValueError("BLOGGER_ACCESS_TOKEN is required for publishing.")
        response = requests.request(
            method,
            url,
            headers=self._headers(access_token),
            timeout=self.config.request_timeout_seconds,
            **kwargs,
        )
        if response.status_code == 401 and self._can_refresh():
            access_token = self._refresh_access_token()
            response = requests.request(
                method,
                url,
                headers=self._headers(access_token),
                timeout=self.config.request_timeout_seconds,
                **kwargs,
            )
        return response

    def _ensure_access_token(self) -> str | None:
        return self._token_state.get("access_token") or self.config.blogger_access_token or (
            self._refresh_access_token() if self._can_refresh() else None
        )

    def _can_refresh(self) -> bool:
        return bool(self._refresh_token() and self.config.blogger_client_id and self.config.blogger_client_secret)

    def _refresh_token(self) -> str | None:
        return self._token_state.get("refresh_token") or self.config.blogger_refresh_token or None

    def _refresh_access_token(self) -> str:
        refresh_token = self._refresh_token()
        if not refresh_token or not self.config.blogger_client_id or not self.config.blogger_client_secret:
            raise ValueError("Blogger token refresh requires client id, client secret, and refresh token.")

        response = requests.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config.blogger_client_id,
                "client_secret": self.config.blogger_client_secret,
            },
            timeout=self.config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Google token refresh returned no access_token.")
        self._token_state["access_token"] = access_token
        if data.get("refresh_token"):
            self._token_state["refresh_token"] = str(data["refresh_token"]).strip()
        self._save_token_state()
        return access_token

    def _load_token_state(self) -> dict[str, str]:
        if not self.token_state_path.exists():
            return {}
        try:
            data = json.loads(self.token_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        cleaned: dict[str, str] = {}
        for key in ("access_token", "refresh_token"):
            value = data.get(key)
            if value:
                cleaned[key] = str(value)
        return cleaned

    def _bootstrap_token_state(self) -> None:
        seeded = False
        if not self._token_state.get("access_token") and self.config.blogger_access_token:
            self._token_state["access_token"] = str(self.config.blogger_access_token)
            seeded = True
        if not self._token_state.get("refresh_token") and self.config.blogger_refresh_token:
            self._token_state["refresh_token"] = str(self.config.blogger_refresh_token)
            seeded = True
        if seeded:
            self._save_token_state()

    def _save_token_state(self) -> None:
        self.token_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_state_path.write_text(json.dumps(self._token_state, ensure_ascii=False, indent=2), encoding="utf-8")

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
