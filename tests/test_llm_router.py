from app.config import Config
from app.llm_router import resolve_llm_candidates


def test_resolve_llm_candidates_uses_direct_openai_when_configured(tmp_path) -> None:
    config = Config(
        root_dir=tmp_path,
        site_url="https://www.wappkit.com",
        sitemap_url="https://www.wappkit.com/sitemap.xml",
        rss_url="https://www.wappkit.com/rss.xml",
        content_raw_base_url="https://raw.githubusercontent.com/example/repo/main/content/blog",
        data_dir=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        request_timeout_seconds=10,
        check_interval_minutes=30,
        max_articles_per_run=1,
        openai_api_key="test-key",
        openai_base_url="https://api.example.com/v1",
        openai_model="gpt-5.4",
        devto_api_key=None,
        devto_publish_status="draft",
        devto_default_tags=["wappkit"],
    )

    candidates = resolve_llm_candidates(config)

    assert len(candidates) == 1
    assert candidates[0].source == "env.openai"


def test_resolve_llm_candidates_parses_model_pool_json(tmp_path) -> None:
    config = Config(
        root_dir=tmp_path,
        site_url="https://www.wappkit.com",
        sitemap_url="https://www.wappkit.com/sitemap.xml",
        rss_url="https://www.wappkit.com/rss.xml",
        content_raw_base_url="https://raw.githubusercontent.com/example/repo/main/content/blog",
        data_dir=tmp_path / "data",
        outputs_dir=tmp_path / "outputs",
        request_timeout_seconds=10,
        check_interval_minutes=30,
        max_articles_per_run=1,
        openai_api_key=None,
        openai_base_url=None,
        openai_model="gpt-5.4",
        devto_api_key=None,
        devto_publish_status="draft",
        devto_default_tags=["wappkit"],
        model_pool_config_json="""
        {
          "fallback_pool": {
            "groq": {
              "api_key": "gsk-test",
              "models": ["openai/gpt-oss-20b"]
            }
          }
        }
        """,
    )

    candidates = resolve_llm_candidates(config)

    assert len(candidates) == 1
    assert candidates[0].source == "model_pool.groq"
    assert candidates[0].base_url == "https://api.groq.com/openai/v1"
