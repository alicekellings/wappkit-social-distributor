from __future__ import annotations

import json
import re

from openai import OpenAI

from app.config import Config
from app.models import RewrittenArticle, SourceArticle


class DevtoRewriter:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = None
        if config.openai_api_key:
            self.client = OpenAI(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url or None,
            )

    def rewrite(self, article: SourceArticle) -> RewrittenArticle:
        if self.client is None:
            return self._fallback_rewrite(article)

        try:
            return self._llm_rewrite(article)
        except Exception:
            return self._fallback_rewrite(article)

    def _llm_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        prompt = f"""
You are adapting a Wappkit blog post for DEV.to.

Rules:
- Keep the article human and practical.
- Preserve the real topic and useful details.
- Remove obvious site-only CTA wording if it sounds too salesy.
- Keep a short note near the top that this version was originally published on Wappkit.
- Keep markdown formatting.
- Do not invent facts.
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

        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            temperature=0.4,
            messages=[
                {
                    "role": "system",
                    "content": "You rewrite articles for publication on DEV.to and return JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = _extract_json(content)

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


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return json.loads(text[start : end + 1])


def _ensure_origin_note(markdown: str, canonical_url: str) -> str:
    note = f"> Originally published on [Wappkit]({canonical_url}). This DEV.to version links back to the source.\n\n"
    if "Originally published on [Wappkit]" in markdown:
        return markdown
    return note + markdown.strip()


def _strip_duplicate_h1(markdown: str, title: str) -> str:
    escaped = re.escape(title.strip())
    return re.sub(rf"(?im)\A#\s+{escaped}\s*\n+", "", markdown.strip(), count=1)


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
