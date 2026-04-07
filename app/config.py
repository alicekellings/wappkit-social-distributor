from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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

    @property
    def database_path(self) -> Path:
        return self.data_dir / "delivery-state.sqlite3"

    @classmethod
    def load(cls) -> "Config":
        root_dir = Path(__file__).resolve().parents[1]
        load_dotenv(root_dir / ".env")

        data_dir_raw = os.getenv("DATA_DIR", "./data")
        outputs_dir_raw = os.getenv("OUTPUTS_DIR", "./outputs")

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
        )

    def ensure_runtime_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        (self.outputs_dir / "previews").mkdir(parents=True, exist_ok=True)
