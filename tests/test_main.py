from app.main import describe_rewrite_mode, normalize_platforms
from app.models import RewrittenArticle


def test_describe_rewrite_mode_for_llm_article() -> None:
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Hello",
        tags=["wappkit"],
        rewrite_source="llm",
        rewrite_strength="moderate",
    )

    assert describe_rewrite_mode(rewritten) == "llm/moderate"


def test_describe_rewrite_mode_for_fallback_article() -> None:
    rewritten = RewrittenArticle(
        title="Demo",
        description="Demo description",
        body_markdown="Hello",
        tags=["wappkit"],
        rewrite_source="fallback",
        rewrite_strength="minimal",
    )

    assert describe_rewrite_mode(rewritten) == "fallback/minimal"


def test_normalize_platforms_keeps_supported_unique_values() -> None:
    assert normalize_platforms(["devto", "blogger", "writeas", "devto", "mastodon"]) == [
        "devto",
        "blogger",
        "writeas",
        "mastodon",
    ]


def test_normalize_platforms_falls_back_to_devto() -> None:
    assert normalize_platforms(["unknown"]) == ["devto"]
