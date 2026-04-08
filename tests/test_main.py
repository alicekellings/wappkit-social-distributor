from app.main import describe_rewrite_mode
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
