from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from app.config import Config
from app.models import PublishResult, RewrittenArticle, SourceArticle


class TumblrPublisher:
    MAX_TEXT_CHARS = 3800

    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_root = "https://api.tumblr.com/v2"
        self.token_url = f"{self.api_root}/oauth2/token"
        self.token_state_path = self.config.data_dir / "tumblr-oauth.json"
        self._token_state = self._load_token_state()
        self._bootstrap_token_state()

    def build_payload(self, rewritten: RewrittenArticle, source: SourceArticle) -> dict:
        state = "published" if self._should_publish_publicly(rewritten) else "draft"
        payload = {
            "content": [
                {
                    "type": "text",
                    "text": self._build_text_body(rewritten, source),
                }
            ],
            "state": state,
        }
        if rewritten.tags:
            payload["tags"] = ",".join(rewritten.tags[:10])
        return payload

    def publish(self, rewritten: RewrittenArticle, source: SourceArticle) -> PublishResult:
        if not self.config.tumblr_blog_identifier:
            raise ValueError("TUMBLR_BLOG_IDENTIFIER is required for publishing.")
        if self.config.tumblr_require_llm_for_publication and rewritten.rewrite_source != "llm":
            raise ValueError("Tumblr publishing requires an llm rewrite when TUMBLR_REQUIRE_LLM_FOR_PUBLICATION=1.")

        payload = self.build_payload(rewritten, source)
        access_token = self._ensure_access_token()
        response = self._post_post_with_retries(payload, access_token)
        if response.status_code == 401 and self._can_refresh():
            access_token = self._refresh_access_token()
            response = self._post_post_with_retries(payload, access_token)

        self._raise_for_status_with_details(response)
        data = response.json()
        response_data = data.get("response") or {}
        state = str(response_data.get("state") or "").strip().lower()
        return PublishResult(
            external_id=str(response_data.get("id") or ""),
            url=self._build_post_url(response_data),
            raw_response=data,
            is_draft=state != "published",
        )

    def save_preview(self, rewritten: RewrittenArticle, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / f"{source.candidate.slug}-tumblr-preview.txt"
        payload_path = output_dir / f"{source.candidate.slug}-tumblr-payload.json"
        payload = self.build_payload(rewritten, source)
        preview_path.write_text(payload["content"][0]["text"], encoding="utf-8")
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return preview_path

    def _build_text_body(self, rewritten: RewrittenArticle, source: SourceArticle) -> str:
        title = (rewritten.title or "").strip()
        body = _markdown_to_tumblr_text(rewritten.body_markdown)
        if title and not body.lower().startswith(title.lower()):
            body = f"{title}\n\n{body}".strip()
        return self._fit_text_limit(body, source)

    def _fit_text_limit(self, body: str, source: SourceArticle) -> str:
        if len(body) <= self.MAX_TEXT_CHARS:
            return body

        canonical_url = source.canonical_url or source.candidate.url
        suffix = f"\n\nRead the full article on Wappkit: {canonical_url}"
        ellipsis = "..."
        budget = max(self.MAX_TEXT_CHARS - len(suffix) - len(ellipsis), 200)
        trimmed = body[:budget].rstrip()

        paragraph_cut = trimmed.rfind("\n\n")
        if paragraph_cut >= int(budget * 0.6):
            trimmed = trimmed[:paragraph_cut].rstrip()

        if not trimmed.endswith(("...", "…")):
            trimmed = trimmed.rstrip(". ") + ellipsis

        return f"{trimmed}{suffix}"

    def _build_post_url(self, response_data: dict) -> str | None:
        blog = self._normalized_blog_identifier()
        post_id = response_data.get("id")
        if not blog or not post_id:
            return None
        if blog.endswith(".tumblr.com"):
            return f"https://{blog}/post/{post_id}"
        return None

    def _should_publish_publicly(self, rewritten: RewrittenArticle) -> bool:
        if self.config.tumblr_publish_status != "published":
            return False
        if self.config.tumblr_require_llm_for_publication and rewritten.rewrite_source != "llm":
            return False
        return True

    def _post_post(self, payload: dict, access_token: str) -> requests.Response:
        return requests.post(
            f"{self.api_root}/blog/{self._normalized_blog_identifier()}/posts",
            headers=self._headers(access_token),
            json=payload,
            timeout=self.config.request_timeout_seconds,
        )

    def _post_post_with_retries(self, payload: dict, access_token: str) -> requests.Response:
        response = self._post_post(payload, access_token)
        if response.status_code != 400:
            return response

        detail = self._extract_error_detail(response).lower()
        if not _looks_like_transient_tumblr_error(detail):
            return response

        for delay_seconds in (1.0, 2.0):
            time.sleep(delay_seconds)
            retry_response = self._post_post(payload, access_token)
            if retry_response.status_code != 400:
                return retry_response
            retry_detail = self._extract_error_detail(retry_response).lower()
            if not _looks_like_transient_tumblr_error(retry_detail):
                return retry_response
            response = retry_response
        return response

    def _headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _ensure_access_token(self) -> str:
        access_token = self._token_state.get("access_token") or self.config.tumblr_access_token
        if access_token:
            return str(access_token)
        if self._can_refresh():
            return self._refresh_access_token()
        raise ValueError("TUMBLR_ACCESS_TOKEN or TUMBLR_REFRESH_TOKEN is required for publishing.")

    def _can_refresh(self) -> bool:
        return bool(self._refresh_token() and self.config.tumblr_client_id and self.config.tumblr_client_secret)

    def _refresh_token(self) -> str | None:
        return self._token_state.get("refresh_token") or self.config.tumblr_refresh_token or None

    def _refresh_access_token(self) -> str:
        refresh_token = self._refresh_token()
        if not refresh_token or not self.config.tumblr_client_id or not self.config.tumblr_client_secret:
            raise ValueError("Tumblr token refresh requires client id, client secret, and refresh token.")

        tried_tokens: list[str] = []
        candidate_tokens: list[str] = []
        if refresh_token:
            candidate_tokens.append(refresh_token)
        config_refresh = self.config.tumblr_refresh_token
        if config_refresh and config_refresh not in candidate_tokens:
            candidate_tokens.append(config_refresh)

        last_error: Exception | None = None
        data: dict | None = None
        for candidate in candidate_tokens:
            tried_tokens.append(candidate)
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": candidate,
                    "client_id": self.config.tumblr_client_id,
                    "client_secret": self.config.tumblr_client_secret,
                },
                timeout=self.config.request_timeout_seconds,
            )
            try:
                self._raise_for_status_with_details(response)
                data = response.json()
                self._token_state["refresh_token"] = candidate
                break
            except requests.HTTPError as exc:
                last_error = exc
                detail = str(exc)
                if "invalid_grant" not in detail:
                    raise
        if data is None:
            if last_error:
                raise last_error
            raise ValueError("Tumblr token refresh failed with no response data.")

        self._token_state["access_token"] = str(data.get("access_token") or "")
        if data.get("refresh_token"):
            self._token_state["refresh_token"] = str(data["refresh_token"])
        self._save_token_state()
        return self._token_state["access_token"]

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
        if not self._token_state.get("access_token") and self.config.tumblr_access_token:
            self._token_state["access_token"] = str(self.config.tumblr_access_token)
            seeded = True
        if not self._token_state.get("refresh_token") and self.config.tumblr_refresh_token:
            self._token_state["refresh_token"] = str(self.config.tumblr_refresh_token)
            seeded = True
        if seeded:
            self._save_token_state()

    def _save_token_state(self) -> None:
        self.token_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_state_path.write_text(json.dumps(self._token_state, ensure_ascii=False, indent=2), encoding="utf-8")

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
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                detail = first.get("detail") or first.get("title")
                if detail:
                    return str(detail)[:500]
        meta = data.get("meta")
        if isinstance(meta, dict):
            msg = meta.get("msg")
            if msg:
                return str(msg)[:500]
        return json.dumps(data, ensure_ascii=False)[:500]

    def _normalized_blog_identifier(self) -> str:
        blog = (self.config.tumblr_blog_identifier or "").strip()
        if not blog:
            return blog
        if "." not in blog:
            return f"{blog}.tumblr.com"
        return blog


def _markdown_to_tumblr_text(markdown: str) -> str:
    text = markdown.strip()
    text = re.sub(r"(?im)^>\s?", "", text)
    text = re.sub(r"(?im)^#{1,6}\s+", "", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 - \2", text)
    text = re.sub(r"(?im)^\s*[-*]\s+", "- ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _looks_like_transient_tumblr_error(detail: str) -> bool:
    markers = (
        "try again",
        "went thud",
        "hiccup",
        "snag",
        "flubbed",
        "goofed",
        "something broke",
        "unknown error",
        "measly little error",
    )
    return any(marker in detail for marker in markers)
