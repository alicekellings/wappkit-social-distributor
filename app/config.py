from __future__ import annotations

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
    devto_require_llm_for_publication: bool = True
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
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4"),
            devto_api_key=os.getenv("DEVTO_API_KEY") or None,
            devto_publish_status=publish_status,
            devto_default_tags=_split_csv(os.getenv("DEVTO_DEFAULT_TAGS", "wappkit,software,productivity,saas")),
            devto_require_llm_for_publication=_env_bool("DEVTO_REQUIRE_LLM_FOR_PUBLICATION", True),
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
