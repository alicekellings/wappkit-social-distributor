from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_secret_with_b64(plain_name: str, b64_name: str) -> str | None:
    encoded = os.getenv(b64_name)
    if encoded:
        try:
            return base64.b64decode(encoded.strip()).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            pass
    return os.getenv(plain_name) or None


@dataclass(slots=True)
class Config:
    root_dir: Path
    site_url: str
    sitemap_url: str
    rss_url: str
    content_raw_base_url: str
    data_dir: Path
    outputs_dir: Path
    request_timeout_seconds: int
    check_interval_minutes: int
    max_articles_per_run: int
    openai_api_key: str | None
    openai_base_url: str | None
    openai_model: str
    devto_api_key: str | None
    devto_publish_status: str
    devto_default_tags: list[str]
    delivery_platforms: list[str] | None = None
    devto_require_llm_for_publication: bool = True
    blogger_access_token: str | None = None
    blogger_blog_id: str | None = None
    blogger_blog_url: str | None = None
    blogger_publish_status: str = "draft"
    blogger_default_labels: list[str] | None = None
    blogger_require_llm_for_publication: bool = True
    wordpress_access_token: str | None = None
    wordpress_site: str | None = None
    wordpress_publish_status: str = "draft"
    wordpress_default_tags: list[str] | None = None
    wordpress_default_categories: list[str] | None = None
    wordpress_require_llm_for_publication: bool = True
    mastodon_base_url: str | None = None
    mastodon_access_token: str | None = None
    mastodon_visibility: str = "unlisted"
    mastodon_language: str = "en"
    mastodon_require_llm_for_publication: bool = True
    use_public_api_pool: bool = False
    public_api_list_file: Path | None = None
    public_api_list_url: str | None = None
    public_api_list_text: str | None = None
    public_api_probe_timeout: int = 15
    public_api_probe_workers: int = 6
    public_api_probe_prompt: str = "Reply in one short English sentence that confirms you can rewrite a blog post."
    public_api_cache_ttl_minutes: int = 30
    model_pool_config_file: Path | None = None
    model_pool_config_url: str | None = None
    model_pool_config_json: str | None = None
    fallback_groq_api_key: str | None = None
    fallback_groq_base_url: str = "https://api.groq.com/openai/v1"
    fallback_groq_models: list[str] | None = None
    fallback_nvidia_api_key: str | None = None
    fallback_nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    fallback_nvidia_models: list[str] | None = None
    fallback_cloudflare_api_key: str | None = None
    fallback_cloudflare_account_id: str | None = None
    fallback_cloudflare_models: list[str] | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "delivery-state.sqlite3"

    @classmethod
    def load(cls) -> "Config":
        root_dir = Path(__file__).resolve().parents[1]
        load_dotenv(root_dir / ".env")

        data_dir_raw = os.getenv("DATA_DIR", "./data")
        outputs_dir_raw = os.getenv("OUTPUTS_DIR", "./outputs")
        public_api_list_file_raw = os.getenv("PUBLIC_API_LIST_FILE")
        model_pool_config_file_raw = os.getenv("MODEL_POOL_CONFIG_FILE")

        data_dir = Path(data_dir_raw)
        if not data_dir.is_absolute():
            data_dir = root_dir / data_dir

        outputs_dir = Path(outputs_dir_raw)
        if not outputs_dir.is_absolute():
            outputs_dir = root_dir / outputs_dir

        publish_status = os.getenv("DEVTO_PUBLISH_STATUS", "draft").strip().lower()
        if publish_status not in {"draft", "published"}:
            publish_status = "draft"

        blogger_publish_status = os.getenv("BLOGGER_PUBLISH_STATUS", "draft").strip().lower()
        if blogger_publish_status not in {"draft", "published"}:
            blogger_publish_status = "draft"

        wordpress_publish_status = os.getenv("WORDPRESS_PUBLISH_STATUS", "draft").strip().lower()
        if wordpress_publish_status not in {"draft", "published"}:
            wordpress_publish_status = "draft"

        mastodon_visibility = os.getenv("MASTODON_VISIBILITY", "unlisted").strip().lower()
        if mastodon_visibility not in {"public", "unlisted", "private", "direct"}:
            mastodon_visibility = "unlisted"

        return cls(
            root_dir=root_dir,
            site_url=os.getenv("WAPPKIT_SITE_URL", "https://www.wappkit.com").rstrip("/"),
            sitemap_url=os.getenv("WAPPKIT_SITEMAP_URL", "https://www.wappkit.com/sitemap.xml"),
            rss_url=os.getenv("WAPPKIT_RSS_URL", "https://www.wappkit.com/rss.xml"),
            content_raw_base_url=os.getenv(
                "WAPPKIT_CONTENT_RAW_BASE_URL",
                "https://raw.githubusercontent.com/alicekellings/wappkit-web/main/content/blog",
            ).rstrip("/"),
            data_dir=data_dir,
            outputs_dir=outputs_dir,
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            check_interval_minutes=int(os.getenv("CHECK_INTERVAL_MINUTES", "30")),
            max_articles_per_run=int(os.getenv("MAX_ARTICLES_PER_RUN", "1")),
            delivery_platforms=_split_csv(os.getenv("DELIVERY_PLATFORMS", "devto")),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4"),
            devto_api_key=os.getenv("DEVTO_API_KEY") or None,
            devto_publish_status=publish_status,
            devto_default_tags=_split_csv(os.getenv("DEVTO_DEFAULT_TAGS", "wappkit,software,productivity,saas")),
            devto_require_llm_for_publication=_env_bool("DEVTO_REQUIRE_LLM_FOR_PUBLICATION", True),
            blogger_access_token=os.getenv("BLOGGER_ACCESS_TOKEN") or None,
            blogger_blog_id=os.getenv("BLOGGER_BLOG_ID") or None,
            blogger_blog_url=os.getenv("BLOGGER_BLOG_URL") or None,
            blogger_publish_status=blogger_publish_status,
            blogger_default_labels=_split_csv(os.getenv("BLOGGER_DEFAULT_LABELS", "wappkit,blog,software")),
            blogger_require_llm_for_publication=_env_bool("BLOGGER_REQUIRE_LLM_FOR_PUBLICATION", True),
            wordpress_access_token=_env_secret_with_b64("WORDPRESS_ACCESS_TOKEN", "WORDPRESS_ACCESS_TOKEN_B64"),
            wordpress_site=os.getenv("WORDPRESS_SITE") or None,
            wordpress_publish_status=wordpress_publish_status,
            wordpress_default_tags=_split_csv(os.getenv("WORDPRESS_DEFAULT_TAGS", "wappkit,blog,software")),
            wordpress_default_categories=_split_csv(os.getenv("WORDPRESS_DEFAULT_CATEGORIES", "Wappkit")),
            wordpress_require_llm_for_publication=_env_bool("WORDPRESS_REQUIRE_LLM_FOR_PUBLICATION", True),
            mastodon_base_url=os.getenv("MASTODON_BASE_URL") or None,
            mastodon_access_token=_env_secret_with_b64("MASTODON_ACCESS_TOKEN", "MASTODON_ACCESS_TOKEN_B64"),
            mastodon_visibility=mastodon_visibility,
            mastodon_language=os.getenv("MASTODON_LANGUAGE", "en"),
            mastodon_require_llm_for_publication=_env_bool("MASTODON_REQUIRE_LLM_FOR_PUBLICATION", True),
            use_public_api_pool=_env_bool("USE_PUBLIC_API_POOL", False),
            public_api_list_file=(root_dir / public_api_list_file_raw).resolve() if public_api_list_file_raw else None,
            public_api_list_url=os.getenv("PUBLIC_API_LIST_URL") or None,
            public_api_list_text=os.getenv("PUBLIC_API_LIST_TEXT") or None,
            public_api_probe_timeout=int(os.getenv("PUBLIC_API_PROBE_TIMEOUT", "15")),
            public_api_probe_workers=int(os.getenv("PUBLIC_API_PROBE_WORKERS", "6")),
            public_api_probe_prompt=os.getenv(
                "PUBLIC_API_PROBE_PROMPT",
                "Reply in one short English sentence that confirms you can rewrite a blog post.",
            ),
            public_api_cache_ttl_minutes=int(os.getenv("PUBLIC_API_CACHE_TTL_MINUTES", "30")),
            model_pool_config_file=(root_dir / model_pool_config_file_raw).resolve() if model_pool_config_file_raw else None,
            model_pool_config_url=os.getenv("MODEL_POOL_CONFIG_URL") or None,
            model_pool_config_json=os.getenv("MODEL_POOL_CONFIG_JSON") or None,
            fallback_groq_api_key=os.getenv("FALLBACK_GROQ_API_KEY") or None,
            fallback_groq_base_url=os.getenv("FALLBACK_GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            fallback_groq_models=_split_csv(os.getenv("FALLBACK_GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b")),
            fallback_nvidia_api_key=os.getenv("FALLBACK_NVIDIA_API_KEY") or None,
            fallback_nvidia_base_url=os.getenv("FALLBACK_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            fallback_nvidia_models=_split_csv(
                os.getenv(
                    "FALLBACK_NVIDIA_MODELS",
                    "mistralai/mistral-small-3.1-24b-instruct,google/gemma-3-27b-it",
                )
            ),
            fallback_cloudflare_api_key=os.getenv("FALLBACK_CLOUDFLARE_API_KEY") or None,
            fallback_cloudflare_account_id=os.getenv("FALLBACK_CLOUDFLARE_ACCOUNT_ID") or None,
            fallback_cloudflare_models=_split_csv(
                os.getenv(
                    "FALLBACK_CLOUDFLARE_MODELS",
                    "@cf/openai/gpt-oss-120b,@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                )
            ),
        )

    def ensure_runtime_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        (self.outputs_dir / "previews").mkdir(parents=True, exist_ok=True)
