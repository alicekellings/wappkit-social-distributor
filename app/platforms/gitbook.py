from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from app.config import Config
from app.models import PublishResult, SourceArticle


class GitbookPublisher:
    api_root = "https://api.gitbook.com/v1"
    import_poll_interval_seconds = 5
    import_poll_timeout_seconds = 300
    request_retry_attempts = 4

    def __init__(self, config: Config) -> None:
        self.config = config

    def get_user(self) -> dict[str, Any]:
        self._ensure_config()
        return self._request_json("get", f"{self.api_root}/user")

    def get_site(self) -> dict[str, Any]:
        self._ensure_config()
        return self._request_json(
            "get",
            f"{self.api_root}/orgs/{self.config.gitbook_org_id}/sites/{self.config.gitbook_site_id}",
        )

    def list_site_spaces(self) -> list[dict[str, Any]]:
        self._ensure_config()
        data = self._request_json(
            "get",
            f"{self.api_root}/orgs/{self.config.gitbook_org_id}/sites/{self.config.gitbook_site_id}/site-spaces",
        )
        return list(data.get("items") or [])

    def build_preview_manifest(self, source: SourceArticle) -> dict[str, Any]:
        return {
            "platform": "gitbook",
            "source_slug": source.candidate.slug,
            "source_url": self._source_url(source),
            "space_title": self._build_space_title(source),
            "site_space_path": self.build_site_space_path(source),
            "publish_status": self.config.gitbook_publish_status,
            "hidden": self.config.gitbook_hidden,
            "enhance_import": self.config.gitbook_import_enhance,
            "organization_id": self.config.gitbook_org_id,
            "site_id": self.config.gitbook_site_id,
        }

    def save_preview(self, source: SourceArticle, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / f"{source.candidate.slug}-gitbook-import.json"
        manifest = self.build_preview_manifest(source)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path

    def publish(self, source: SourceArticle) -> PublishResult:
        self._ensure_config()

        created_space: dict[str, Any] | None = None
        site_space: dict[str, Any] | None = None

        try:
            created_space = self.create_space(self._build_space_title(source))
            space_id = str(created_space.get("id") or "").strip()
            if not space_id:
                raise ValueError("GitBook create space response returned no id.")

            existing_pages = self._flatten_pages(self.list_pages(space_id))
            existing_page_ids = {
                str(page.get("id") or "").strip()
                for page in existing_pages
                if str(page.get("id") or "").strip()
            }

            import_job = self.start_website_import(space_id, self._source_url(source))

            site_space = self.add_site_space(space_id)
            site_space_id = str(site_space.get("id") or "").strip()
            if not site_space_id:
                raise ValueError("GitBook attach space response returned no site-space id.")

            published_site_space = self.update_site_space(
                site_space_id=site_space_id,
                path=self.build_site_space_path(source),
                hidden=self.config.gitbook_hidden,
                draft=self.config.gitbook_publish_status != "published",
            )
            imported_page = self.wait_for_imported_page(space_id, existing_page_ids)
            final_url = self._build_final_url(published_site_space, imported_page)

            raw_response = {
                "space": created_space,
                "import": import_job,
                "page": imported_page,
                "site_space": published_site_space,
                "final_url": final_url,
            }
            return PublishResult(
                external_id=site_space_id,
                url=final_url,
                raw_response=raw_response,
                is_draft=bool(published_site_space.get("draft")),
            )
        except Exception:
            if site_space:
                self.delete_site_space(str(site_space.get("id") or "").strip())
            if created_space:
                self.delete_space(str(created_space.get("id") or "").strip())
            raise

    def extract_state(self, result: PublishResult) -> dict[str, Any]:
        state: dict[str, Any] = {}
        raw = result.raw_response
        import_job = raw.get("import") or {}
        page = raw.get("page") or {}
        site_space = raw.get("site_space") or {}
        space = raw.get("space") or {}
        published_base_url = (
            ((site_space.get("urls") or {}).get("published"))
            or ((space.get("urls") or {}).get("published"))
            or ((space.get("urls") or {}).get("public"))
        )

        if import_job.get("id"):
            state["import_id"] = str(import_job["id"])
        if space.get("id"):
            state["space_id"] = str(space["id"])
        if site_space.get("id"):
            state["site_space_id"] = str(site_space["id"])
        if site_space.get("path"):
            state["site_space_path"] = str(site_space["path"])
        if page.get("id"):
            state["page_id"] = str(page["id"])
        if page.get("path"):
            state["page_path"] = str(page["path"])
        if published_base_url:
            state["published_base_url"] = str(published_base_url)
        if result.url:
            state["url"] = result.url
        state["draft"] = bool(site_space.get("draft"))
        state["hidden"] = bool(site_space.get("hidden"))
        return state

    def create_space(self, title: str) -> dict[str, Any]:
        return self._request_json(
            "post",
            f"{self.api_root}/orgs/{self.config.gitbook_org_id}/spaces",
            json={
                "title": title,
                "language": "en",
            },
        )

    def start_website_import(self, space_id: str, source_url: str) -> dict[str, Any]:
        return self._request_json(
            "post",
            f"{self.api_root}/org/{self.config.gitbook_org_id}/imports",
            json={
                "source": {
                    "type": "website",
                    "url": source_url,
                },
                "target": {
                    "space": space_id,
                },
                "enhance": self.config.gitbook_import_enhance,
            },
        )

    def list_pages(self, space_id: str) -> list[dict[str, Any]]:
        data = self._request_json(
            "get",
            f"{self.api_root}/spaces/{space_id}/content/pages",
        )
        return list(data.get("pages") or [])

    def wait_for_imported_page(self, space_id: str, existing_page_ids: set[str]) -> dict[str, Any]:
        deadline = time.monotonic() + self.import_poll_timeout_seconds
        while time.monotonic() < deadline:
            pages = self._flatten_pages(self.list_pages(space_id))
            imported_pages = [
                page
                for page in pages
                if str(page.get("id") or "").strip() not in existing_page_ids
            ]
            if imported_pages:
                preferred_pages = [
                    page
                    for page in imported_pages
                    if str(page.get("path") or "").strip().lower() != "page"
                ]
                return preferred_pages[0] if preferred_pages else imported_pages[0]
            time.sleep(self.import_poll_interval_seconds)
        raise TimeoutError(f"Timed out waiting for GitBook import to finish for space {space_id}.")

    def add_site_space(self, space_id: str) -> dict[str, Any]:
        return self._request_json(
            "post",
            f"{self.api_root}/orgs/{self.config.gitbook_org_id}/sites/{self.config.gitbook_site_id}/site-spaces",
            json={"spaceId": space_id},
        )

    def update_site_space(self, site_space_id: str, path: str, hidden: bool, draft: bool) -> dict[str, Any]:
        return self._request_json(
            "patch",
            f"{self.api_root}/orgs/{self.config.gitbook_org_id}/sites/{self.config.gitbook_site_id}/site-spaces/{site_space_id}",
            json={
                "path": path,
                "hidden": hidden,
                "draft": draft,
            },
        )

    def delete_site_space(self, site_space_id: str) -> None:
        if not site_space_id:
            return
        try:
            self._request(
                "delete",
                f"{self.api_root}/orgs/{self.config.gitbook_org_id}/sites/{self.config.gitbook_site_id}/site-spaces/{site_space_id}",
            )
        except Exception:
            return

    def delete_space(self, space_id: str) -> None:
        if not space_id:
            return
        try:
            self._request("delete", f"{self.api_root}/spaces/{space_id}")
        except Exception:
            return

    def build_site_space_path(self, source: SourceArticle) -> str:
        seed = source.candidate.slug or source.title or "wappkit-import"
        cleaned = re.sub(r"[^a-z0-9-]+", "-", seed.lower())
        cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
        return (cleaned[:96] or "wappkit-import").strip("-") or "wappkit-import"

    def _build_space_title(self, source: SourceArticle) -> str:
        title = (source.title or source.candidate.slug or "Wappkit Import").strip()
        if len(title) <= 50:
            return title
        return title[:47].rstrip() + "..."

    def _source_url(self, source: SourceArticle) -> str:
        url = (source.canonical_url or source.candidate.url or "").strip()
        if not url:
            raise ValueError("GitBook publishing requires a canonical source URL.")
        return url

    def _build_final_url(self, site_space: dict[str, Any], imported_page: dict[str, Any]) -> str | None:
        base_url = (
            ((site_space.get("urls") or {}).get("published"))
            or (((site_space.get("space") or {}).get("urls") or {}).get("published"))
            or (((site_space.get("space") or {}).get("urls") or {}).get("public"))
        )
        if not base_url:
            return None
        page_path = str(imported_page.get("path") or imported_page.get("slug") or "").strip("/")
        if not page_path:
            return str(base_url).rstrip("/") + "/"
        return f"{str(base_url).rstrip('/')}/{page_path}"

    def _ensure_config(self) -> None:
        missing: list[str] = []
        if not self.config.gitbook_token:
            missing.append("GITBOOK_TOKEN")
        if not self.config.gitbook_org_id:
            missing.append("GITBOOK_ORG_ID")
        if not self.config.gitbook_site_id:
            missing.append("GITBOOK_SITE_ID")
        if missing:
            raise ValueError(f"GitBook publishing requires: {', '.join(missing)}")

    def _request_json(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        response = self._request(method, url, **kwargs)
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected GitBook response shape from {url}: {type(data).__name__}")
        return data

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self.config.gitbook_token}",
            "Accept": "application/json",
        }
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        extra_headers = kwargs.pop("headers", None) or {}
        headers.update(extra_headers)

        last_error: Exception | None = None
        for attempt in range(1, self.request_retry_attempts + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.config.request_timeout_seconds,
                    **kwargs,
                )
                self._raise_for_status_with_details(response)
                return response
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt >= self.request_retry_attempts:
                    raise
                time.sleep(min(2 * attempt, 5))
        if last_error:
            raise last_error
        raise RuntimeError(f"GitBook request failed without a captured exception: {method.upper()} {url}")

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
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return str(message)[:500]
            for key in ("message", "error", "detail"):
                value = data.get(key)
                if value:
                    return str(value)[:500]
            return json.dumps(data, ensure_ascii=False)[:500]
        return str(data)[:500]

    def _flatten_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        for page in pages:
            flattened.append(page)
            flattened.extend(self._flatten_pages(list(page.get("pages") or [])))
        return flattened
