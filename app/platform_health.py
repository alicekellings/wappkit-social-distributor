from __future__ import annotations

from dataclasses import dataclass

import requests

from app.blogger_oauth import verify_access_token as verify_blogger_access_token
from app.config import Config
from app.platforms.blogger import BloggerPublisher
from app.platforms.tumblr import TumblrPublisher
from app.platforms.writeas import WriteasPublisher
from app.tumblr_oauth import verify_access_token as verify_tumblr_access_token


SUPPORTED_PLATFORMS = ("devto", "blogger", "wordpress", "mastodon", "tumblr", "writeas")


@dataclass(slots=True)
class PlatformVerificationResult:
    platform: str
    ok: bool
    detail: str
    used_refresh: bool = False


def normalize_platforms(platforms: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for platform in platforms or []:
        token = (platform or "").strip().lower()
        if token not in SUPPORTED_PLATFORMS or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized or ["devto"]


def verify_platforms(config: Config, platforms: list[str] | None = None) -> list[PlatformVerificationResult]:
    selected = normalize_platforms(platforms or config.delivery_platforms)
    checks = {
        "devto": _verify_devto,
        "blogger": _verify_blogger,
        "wordpress": _verify_wordpress,
        "mastodon": _verify_mastodon,
        "tumblr": _verify_tumblr,
        "writeas": _verify_writeas,
    }
    return [checks[platform](config) for platform in selected]


def _verify_devto(config: Config) -> PlatformVerificationResult:
    if not config.devto_api_key:
        return PlatformVerificationResult("devto", False, "DEVTO_API_KEY is missing.")
    try:
        response = requests.get(
            "https://dev.to/api/articles/me/all",
            params={"per_page": 1},
            headers={
                "api-key": config.devto_api_key,
                "Accept": "application/vnd.forem.api-v1+json",
            },
            timeout=config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        count = len(data) if isinstance(data, list) else 0
        return PlatformVerificationResult("devto", True, f"Authenticated; sample_count={count}.")
    except Exception as exc:
        return PlatformVerificationResult("devto", False, str(exc))


def _verify_blogger(config: Config) -> PlatformVerificationResult:
    if not config.blogger_blog_id and not config.blogger_blog_url:
        return PlatformVerificationResult("blogger", False, "BLOGGER_BLOG_ID or BLOGGER_BLOG_URL is required.")

    publisher = BloggerPublisher(config)
    try:
        access_token = publisher._ensure_access_token()
        if not access_token:
            raise ValueError("BLOGGER_ACCESS_TOKEN is required.")
        used_refresh = False
        try:
            verify_blogger_access_token(access_token, timeout=config.request_timeout_seconds)
        except requests.HTTPError:
            if not publisher._can_refresh():
                raise
            access_token = publisher._refresh_access_token()
            used_refresh = True
            verify_blogger_access_token(access_token, timeout=config.request_timeout_seconds)

        blog_id = publisher._resolve_blog_id()
        return PlatformVerificationResult(
            "blogger",
            True,
            f"Authenticated; blog_id={blog_id}.",
            used_refresh=used_refresh,
        )
    except Exception as exc:
        return PlatformVerificationResult("blogger", False, str(exc))


def _verify_wordpress(config: Config) -> PlatformVerificationResult:
    if not config.wordpress_access_token:
        return PlatformVerificationResult("wordpress", False, "WORDPRESS_ACCESS_TOKEN is missing.")
    if not config.wordpress_site:
        return PlatformVerificationResult("wordpress", False, "WORDPRESS_SITE is missing.")
    try:
        me_response = requests.get(
            "https://public-api.wordpress.com/rest/v1.1/me",
            headers={
                "Authorization": f"Bearer {config.wordpress_access_token}",
                "Accept": "application/json",
            },
            timeout=config.request_timeout_seconds,
        )
        me_response.raise_for_status()
        me = me_response.json()

        site_response = requests.get(
            f"https://public-api.wordpress.com/rest/v1.1/sites/{config.wordpress_site}",
            headers={
                "Authorization": f"Bearer {config.wordpress_access_token}",
                "Accept": "application/json",
            },
            timeout=config.request_timeout_seconds,
        )
        site_response.raise_for_status()
        site = site_response.json()
        return PlatformVerificationResult(
            "wordpress",
            True,
            f"Authenticated; username={me.get('username', 'unknown')} site_id={site.get('ID', 'unknown')}.",
        )
    except Exception as exc:
        return PlatformVerificationResult("wordpress", False, str(exc))


def _verify_mastodon(config: Config) -> PlatformVerificationResult:
    if not config.mastodon_base_url:
        return PlatformVerificationResult("mastodon", False, "MASTODON_BASE_URL is missing.")
    if not config.mastodon_access_token:
        return PlatformVerificationResult("mastodon", False, "MASTODON_ACCESS_TOKEN is missing.")
    try:
        response = requests.get(
            f"{config.mastodon_base_url.rstrip('/')}/api/v1/accounts/verify_credentials",
            headers={
                "Authorization": f"Bearer {config.mastodon_access_token}",
                "Accept": "application/json",
            },
            timeout=config.request_timeout_seconds,
        )
        response.raise_for_status()
        account = response.json()
        return PlatformVerificationResult(
            "mastodon",
            True,
            f"Authenticated; acct={account.get('acct', 'unknown')}.",
        )
    except Exception as exc:
        return PlatformVerificationResult("mastodon", False, str(exc))


def _verify_tumblr(config: Config) -> PlatformVerificationResult:
    if not config.tumblr_blog_identifier:
        return PlatformVerificationResult("tumblr", False, "TUMBLR_BLOG_IDENTIFIER is missing.")

    publisher = TumblrPublisher(config)
    try:
        access_token = publisher._ensure_access_token()
        used_refresh = False
        try:
            info = verify_tumblr_access_token(access_token, timeout=config.request_timeout_seconds)
        except requests.HTTPError:
            if not publisher._can_refresh():
                raise
            access_token = publisher._refresh_access_token()
            used_refresh = True
            info = verify_tumblr_access_token(access_token, timeout=config.request_timeout_seconds)

        blog_response = requests.get(
            f"https://api.tumblr.com/v2/blog/{config.tumblr_blog_identifier}/info",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=config.request_timeout_seconds,
        )
        blog_response.raise_for_status()
        blog = ((blog_response.json().get("response") or {}).get("blog") or {})
        user = (((info.get("response") or {}).get("user")) or {})
        return PlatformVerificationResult(
            "tumblr",
            True,
            f"Authenticated; user={user.get('name', 'unknown')} blog={blog.get('name', 'unknown')}.",
            used_refresh=used_refresh,
        )
    except Exception as exc:
        return PlatformVerificationResult("tumblr", False, str(exc))


def _verify_writeas(config: Config) -> PlatformVerificationResult:
    publisher = WriteasPublisher(config)
    try:
        response = requests.post(
            f"{publisher.api_root}/markdown",
            json={"raw_body": "Write.as API probe"},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=config.request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        body = (data.get("data") or {}).get("body") or ""
        return PlatformVerificationResult(
            "writeas",
            True,
            f"Anonymous publishing endpoint reachable; rendered_length={len(str(body))}.",
        )
    except Exception as exc:
        return PlatformVerificationResult("writeas", False, str(exc))
