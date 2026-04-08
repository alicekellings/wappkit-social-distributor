from __future__ import annotations

import re

from app.config import Config
from app.llm_router import LLMRouter
from app.models import RewrittenArticle, SourceArticle


class DevtoRewriter:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.router = LLMRouter(config)
        self.last_provider_label: str | None = None

    def rewrite(self, article: SourceArticle) -> RewrittenArticle:
        self.last_provider_label = self.router.active_label
        if not self.router.enabled:
            return self._fallback_rewrite(article)

        try:
            rewritten = self._llm_rewrite(article)
            self.last_provider_label = self.router.active_label
            return rewritten
        except Exception:
            return self._fallback_rewrite(article)

    def _llm_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        prompt = f"""
You are adapting a Wappkit blog post for DEV.to.

Rules:
- Make this clearly feel like a DEV.to-native version, not a copy-paste mirror.
- Keep the article human and practical.
- Preserve the real topic and useful details.
- Rewrite the title so it feels natural on DEV.to while staying faithful to the topic.
- Rewrite the opening section with a fresh angle and community-style tone.
- Keep the structure recognizable, but lightly rewrite headings and paragraphs so the wording is not identical.
- Remove obvious site-only CTA wording if it sounds too salesy.
- Keep a short note near the top that this version was originally published on Wappkit.
- Keep a source link back to Wappkit near the end.
- Keep markdown formatting.
- Do not invent facts.
- Aim for a light rewrite, not a total rewrite.
- Output valid JSON only.

JSON schema:
{{
  "title": "string",
  "description": "string under 200 chars",
  "body_markdown": "string",
  "tags": ["string", "string"]
}}

Canonical URL: {article.canonical_url}
Original title: {article.title}
Original description: {article.description}
Original markdown:
{article.markdown}
""".strip()

        payload = self.router.complete_json(
            system_prompt="You rewrite articles for publication on DEV.to and return JSON only.",
            user_prompt=prompt,
            temperature=0.45,
        )

        return RewrittenArticle(
            title=str(payload.get("title") or article.title).strip(),
            description=str(payload.get("description") or article.description).strip()[:200],
            body_markdown=_ensure_origin_note(
                str(payload.get("body_markdown") or article.markdown).strip(),
                article.canonical_url,
            ),
            tags=_sanitize_tags([str(tag) for tag in payload.get("tags", [])], article, self.config),
        )

    def _fallback_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        body = _strip_duplicate_h1(article.markdown, article.title)
        body = _strip_marketing_lines(body)
        body = _build_devto_style_intro(article) + "\n\n" + body.strip()
        body = _ensure_origin_note(body, article.canonical_url)
        body = body.strip()
        body += (
            "\n\n---\n\n"
            f"Originally published on [Wappkit]({article.canonical_url}). "
            "If you want the original version with product context, read it there."
        )

        return RewrittenArticle(
            title=article.title.strip(),
            description=(article.description or article.title).strip()[:200],
            body_markdown=body,
            tags=_sanitize_tags(article.tags + article.categories, article, self.config),
        )


def _ensure_origin_note(markdown: str, canonical_url: str) -> str:
    note = f"> Originally published on [Wappkit]({canonical_url}). This DEV.to version links back to the source.\n\n"
    if "Originally published on [Wappkit]" in markdown:
        return markdown
    return note + markdown.strip()


def _strip_duplicate_h1(markdown: str, title: str) -> str:
    escaped = re.escape(title.strip())
    return re.sub(rf"(?im)\A#\s+{escaped}\s*\n+", "", markdown.strip(), count=1)


def _strip_marketing_lines(markdown: str) -> str:
    lines = markdown.splitlines()
    blocked_patterns = [
        r"download free version",
        r"view product",
        r"visit wappkit",
        r"built for github and vercel",
    ]
    kept: list[str] = []
    for line in lines:
        lowered = line.strip().lower()
        if any(re.search(pattern, lowered) for pattern in blocked_patterns):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _build_devto_style_intro(article: SourceArticle) -> str:
    title_hint = article.title.replace("How to ", "").replace("Guide", "").strip()
    description = article.description.strip().rstrip(".")
    parts = [
        f"If you're exploring `{title_hint}` from a builder or operator angle, here's a DEV.to-friendly version of what I originally wrote on Wappkit.",
    ]
    if description:
        parts.append(description + ".")
    parts.append("I kept the useful parts, trimmed the site-specific wording, and left the original source linked back at the end.")
    return "\n\n".join(parts)


def _sanitize_tags(seed_tags: list[str], article: SourceArticle, config: Config) -> list[str]:
    combined = [*seed_tags, *article.tags, *article.categories, *config.devto_default_tags]
    seen: set[str] = set()
    cleaned: list[str] = []

    for tag in combined:
        token = re.sub(r"[^a-zA-Z0-9_]", "", tag.lower().replace("-", ""))
        if not token or len(token) > 20:
            continue
        if token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
        if len(cleaned) >= 4:
            break

    if not cleaned:
        cleaned = ["wappkit", "software", "saas"]
    return cleaned[:4]
