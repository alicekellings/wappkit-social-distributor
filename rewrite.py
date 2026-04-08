from __future__ import annotations

import re

from app.config import Config
from app.llm_router import LLMRouter
from app.models import RewrittenArticle, SourceArticle


class _BasePlatformRewriter:
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
        raise NotImplementedError

    def _fallback_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        raise NotImplementedError


class DevtoRewriter(_BasePlatformRewriter):
    def _llm_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        prompt = f"""
You are adapting a Wappkit blog post for DEV.to.

Rules:
- Make this clearly feel like a DEV.to-native version, not a copy-paste mirror.
- Keep the article human, practical, and written for builders, operators, or developers.
- Preserve the real topic and useful details.
- Rewrite the title so it feels natural on DEV.to while staying faithful to the topic. Do not reuse the source title verbatim.
- Rewrite the opening 2-4 paragraphs with a fresh angle and community-style tone.
- Frame the article around practical execution, mistakes, workflow choices, or lessons learned.
- Rewrite at least 3 section headings when the article is long enough to support that.
- Keep the structure recognizable, but rewrite paragraphs so the wording is not too close to the source.
- Do not keep the exact same framing from the source. Shift the emphasis toward implementation, tradeoffs, or operator lessons.
- Remove obvious site-only CTA wording if it sounds too salesy.
- Cut or soften product-led wording unless it is necessary for context.
- Keep a short note near the top that this version was originally published on Wappkit.
- Keep a source link back to Wappkit near the end.
- Add one short DEV.to-native section near the end, such as "Practical takeaway", "What I would do", "Workflow notes", or "Key lesson".
- Keep markdown formatting.
- Do not invent facts.
- Avoid copying long verbatim passages from the source unless they are necessary quotes or exact labels.
- Aim for a strong platform adaptation, not a superficial synonym swap.
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
            body_markdown=_ensure_platform_body(
                str(payload.get("body_markdown") or article.markdown).strip(),
                article,
                platform_name="DEV.to",
            ),
            tags=_sanitize_tags(
                [str(tag) for tag in payload.get("tags", [])],
                article,
                self.config.devto_default_tags,
            ),
            rewrite_source="llm",
            rewrite_strength="moderate",
        )

    def _fallback_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        body = _strip_duplicate_h1(article.markdown, article.title)
        body = _strip_marketing_lines(body)
        body = _build_devto_style_intro(article) + "\n\n" + body.strip()
        body = _ensure_platform_specific_section(body, article, platform_name="DEV.to")
        body = _ensure_origin_note(body, article.canonical_url, platform_name="DEV.to")
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
            tags=_sanitize_tags(article.tags + article.categories, article, self.config.devto_default_tags),
            rewrite_source="fallback",
            rewrite_strength="minimal",
        )


class BloggerRewriter(_BasePlatformRewriter):
    def _llm_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        prompt = f"""
You are adapting a Wappkit blog post for a Blogger / Blogspot audience.

Rules:
- Make this clearly feel like a standalone blog edition, not a copy-paste mirror.
- Keep the article human, practical, and readable in a classic blog format.
- Preserve the real topic and useful details.
- Rewrite the title so it feels natural on a standalone blog. Do not reuse the source title verbatim.
- Rewrite the opening 2-4 paragraphs with a fresh angle.
- Frame the article as a tutorial, a clear guide, or a step-by-step plan for someone who searched this topic.
- Rewrite at least 3 section headings when the article is long enough to support that.
- Keep the structure recognizable, but rewrite paragraphs so the wording is not too close to the source.
- Do not keep the exact same framing from the source. Shift the emphasis toward steps, checks, FAQs, or practical sequencing.
- Remove or soften obvious site-only CTA wording if it sounds too salesy.
- Keep a short note near the top that this version was originally published on Wappkit.
- Keep a source link back to Wappkit near the end.
- Add one short blog-native section near the end, such as "Quick steps", "Simple plan", "Checklist", or "FAQ".
- Keep markdown formatting.
- Do not mention DEV.to.
- Do not invent facts.
- Avoid copying long verbatim passages from the source unless they are necessary quotes or exact labels.
- Aim for a strong platform adaptation, not a superficial synonym swap.
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
            system_prompt="You rewrite articles for publication on Blogger and return JSON only.",
            user_prompt=prompt,
            temperature=0.45,
        )

        return RewrittenArticle(
            title=str(payload.get("title") or article.title).strip(),
            description=str(payload.get("description") or article.description).strip()[:200],
            body_markdown=_ensure_platform_body(
                str(payload.get("body_markdown") or article.markdown).strip(),
                article,
                platform_name="Blogger",
            ),
            tags=_sanitize_tags(
                [str(tag) for tag in payload.get("tags", [])],
                article,
                self.config.blogger_default_labels or ["wappkit", "blog", "software"],
            ),
            rewrite_source="llm",
            rewrite_strength="moderate",
        )

    def _fallback_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        body = _strip_duplicate_h1(article.markdown, article.title)
        body = _strip_marketing_lines(body)
        body = _build_blogger_style_intro(article) + "\n\n" + body.strip()
        body = _ensure_platform_specific_section(body, article, platform_name="Blogger")
        body = _ensure_origin_note(body, article.canonical_url, platform_name="Blogger")
        body = body.strip()
        body += (
            "\n\n---\n\n"
            f"Originally published on [Wappkit]({article.canonical_url}). "
            "Read the source there for the original version and current product context."
        )

        return RewrittenArticle(
            title=article.title.strip(),
            description=(article.description or article.title).strip()[:200],
            body_markdown=body,
            tags=_sanitize_tags(
                article.tags + article.categories,
                article,
                self.config.blogger_default_labels or ["wappkit", "blog", "software"],
            ),
            rewrite_source="fallback",
            rewrite_strength="minimal",
        )


class WordpressRewriter(_BasePlatformRewriter):
    def _llm_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        prompt = f"""
You are adapting a Wappkit blog post for a WordPress.com audience.

Rules:
- Make this clearly feel like a standalone WordPress blog edition, not a copy-paste mirror.
- Keep the article human, practical, and readable in a classic blog format.
- Preserve the real topic and useful details.
- Rewrite the title so it feels natural on WordPress. Do not reuse the source title verbatim.
- Rewrite the opening 2-4 paragraphs with a fresh angle.
- Frame the article as a case-based analysis, opinionated guide, or tradeoff discussion for a reader who wants context, not just steps.
- Rewrite at least 3 section headings when the article is long enough to support that.
- Keep the structure recognizable, but rewrite paragraphs so the wording is not too close to the source.
- Do not keep the exact same framing from the source. Shift the emphasis toward decisions, tradeoffs, mistakes, and when the approach actually fits.
- Remove or soften obvious site-only CTA wording if it sounds too salesy.
- Keep a short note near the top that this version was originally published on Wappkit.
- Keep a source link back to Wappkit near the end.
- Add one short WordPress-native section near the end, such as "When this approach fits", "Tradeoffs to keep in mind", or "Common mistakes to avoid".
- Keep markdown formatting.
- Do not mention DEV.to or Blogger.
- Do not invent facts.
- Avoid copying long verbatim passages from the source unless they are necessary quotes or exact labels.
- Aim for a strong platform adaptation, not a superficial synonym swap.
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
            system_prompt="You rewrite articles for publication on WordPress.com and return JSON only.",
            user_prompt=prompt,
            temperature=0.45,
        )

        return RewrittenArticle(
            title=str(payload.get("title") or article.title).strip(),
            description=str(payload.get("description") or article.description).strip()[:200],
            body_markdown=_ensure_platform_body(
                str(payload.get("body_markdown") or article.markdown).strip(),
                article,
                platform_name="WordPress.com",
            ),
            tags=_sanitize_tags(
                [str(tag) for tag in payload.get("tags", [])],
                article,
                self.config.wordpress_default_tags or ["wappkit", "blog", "software"],
            ),
            rewrite_source="llm",
            rewrite_strength="moderate",
        )

    def _fallback_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        body = _strip_duplicate_h1(article.markdown, article.title)
        body = _strip_marketing_lines(body)
        body = _build_wordpress_style_intro(article) + "\n\n" + body.strip()
        body = _ensure_platform_specific_section(body, article, platform_name="WordPress.com")
        body = _ensure_origin_note(body, article.canonical_url, platform_name="WordPress.com")
        body = body.strip()
        body += (
            "\n\n---\n\n"
            f"Originally published on [Wappkit]({article.canonical_url}). "
            "Read the source there for the original version and current product context."
        )

        return RewrittenArticle(
            title=article.title.strip(),
            description=(article.description or article.title).strip()[:200],
            body_markdown=body,
            tags=_sanitize_tags(
                article.tags + article.categories,
                article,
                self.config.wordpress_default_tags or ["wappkit", "blog", "software"],
            ),
            rewrite_source="fallback",
            rewrite_strength="minimal",
        )


class MastodonRewriter(_BasePlatformRewriter):
    def _llm_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        prompt = f"""
You are adapting a Wappkit blog post into a Mastodon post.

Rules:
- Output a short social post, not a full article.
- Keep it human and practical.
- Mention the main takeaway from the article.
- Include the source link exactly once near the end.
- Include 1-3 relevant hashtags.
- Keep the full post within 450 characters.
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

        payload = self.router.complete_json(
            system_prompt="You rewrite articles into short Mastodon posts and return JSON only.",
            user_prompt=prompt,
            temperature=0.45,
        )

        body = _truncate_mastodon_status(
            str(payload.get("body_markdown") or "").strip(),
            article.canonical_url,
            [str(tag) for tag in payload.get("tags", [])],
        )

        return RewrittenArticle(
            title=str(payload.get("title") or article.title).strip(),
            description=str(payload.get("description") or article.description).strip()[:200],
            body_markdown=body,
            tags=_sanitize_tags(
                [str(tag) for tag in payload.get("tags", [])],
                article,
                ["wappkit", "blog", "software"],
            ),
            rewrite_source="llm",
            rewrite_strength="moderate",
        )

    def _fallback_rewrite(self, article: SourceArticle) -> RewrittenArticle:
        body = _build_mastodon_status(article, article.tags + article.categories)
        return RewrittenArticle(
            title=article.title.strip(),
            description=(article.description or article.title).strip()[:200],
            body_markdown=body,
            tags=_sanitize_tags(article.tags + article.categories, article, ["wappkit", "blog", "software"]),
            rewrite_source="fallback",
            rewrite_strength="minimal",
        )


def _ensure_origin_note(markdown: str, canonical_url: str, platform_name: str) -> str:
    note = f"> Originally published on [Wappkit]({canonical_url}). This {platform_name} version links back to the source.\n\n"
    if "Originally published on [Wappkit]" in markdown:
        return markdown
    return note + markdown.strip()


def _ensure_platform_body(markdown: str, article: SourceArticle, platform_name: str) -> str:
    body = _ensure_platform_specific_section(markdown, article, platform_name)
    return _ensure_origin_note(body, article.canonical_url, platform_name=platform_name)


def _ensure_platform_specific_section(markdown: str, article: SourceArticle, platform_name: str) -> str:
    body = markdown.strip()
    heading = _platform_section_heading(platform_name)
    if re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", body):
        return body
    return body + "\n\n" + _build_platform_section(article, platform_name)


def _strip_duplicate_h1(markdown: str, title: str) -> str:
    escaped = re.escape(title.strip())
    cleaned = markdown.strip()
    while True:
        updated = re.sub(rf"(?im)\A#\s+{escaped}\s*\n+", "", cleaned, count=1)
        if updated == cleaned:
            return cleaned
        cleaned = updated.lstrip()


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
    parts.append("I kept the useful parts, shifted the framing toward execution and workflow, and left the original source linked back at the end.")
    return "\n\n".join(parts)


def _build_blogger_style_intro(article: SourceArticle) -> str:
    title_hint = article.title.replace("How to ", "").replace("Guide", "").strip()
    description = article.description.strip().rstrip(".")
    parts = [
        f"Here's a Blogger-friendly adaptation of my original Wappkit article about `{title_hint}`.",
    ]
    if description:
        parts.append(description + ".")
    parts.append("I kept the useful parts, reorganized them into a more tutorial-style flow, and linked back to the original source at the end.")
    return "\n\n".join(parts)


def _build_wordpress_style_intro(article: SourceArticle) -> str:
    title_hint = article.title.replace("How to ", "").replace("Guide", "").strip()
    description = article.description.strip().rstrip(".")
    parts = [
        f"Here is a WordPress-friendly adaptation of my original Wappkit article about `{title_hint}`.",
    ]
    if description:
        parts.append(description + ".")
    parts.append("I kept the useful parts, reframed them around context and tradeoffs, and linked back to the original source at the end.")
    return "\n\n".join(parts)


def _platform_section_heading(platform_name: str) -> str:
    if platform_name == "DEV.to":
        return "Practical takeaway"
    if platform_name == "Blogger":
        return "Quick steps"
    if platform_name == "WordPress.com":
        return "Tradeoffs to keep in mind"
    raise ValueError(f"Unsupported platform section heading for {platform_name}")


def _build_platform_section(article: SourceArticle, platform_name: str) -> str:
    topic = article.title.strip().rstrip(".")
    description = article.description.strip().rstrip(".")
    if platform_name == "DEV.to":
        lines = [
            "## Practical takeaway",
            "",
            f"If I were applying `{topic}` in a real workflow, I would start with the smallest repeatable step first and only scale it after the signal looks real.",
            f"The short version is this: {description.lower() if description else 'keep the useful signal, remove the extra noise, and validate with real usage'}.",
            "That angle matters more on DEV.to because readers usually want something they can test quickly, not just a broad summary.",
        ]
        return "\n".join(lines)
    if platform_name == "Blogger":
        lines = [
            "## Quick steps",
            "",
            f"1. Define the exact problem you are solving with `{topic}`.",
            "2. Start with the simplest working version before adding extra automation.",
            "3. Check the result against real usage instead of assuming the first draft is enough.",
            "4. Keep notes on what changed so the next iteration is faster.",
        ]
        return "\n".join(lines)
    if platform_name == "WordPress.com":
        lines = [
            "## Tradeoffs to keep in mind",
            "",
            f"`{topic}` can work well when the workflow is clear, but it is rarely just a matter of copying a tactic from one context into another.",
            "The upside is speed and clarity once the process is defined.",
            "The downside is that the wrong framing can make the result look generic, especially when the same topic is published across multiple platforms.",
            "That is why this version focuses more on decisions, fit, and tradeoffs than a simple how-to sequence.",
        ]
        return "\n".join(lines)
    raise ValueError(f"Unsupported platform section builder for {platform_name}")


def _build_mastodon_status(article: SourceArticle, tags: list[str]) -> str:
    base = f"{article.title}\n\n{article.description.strip()}\n\n{article.canonical_url}"
    return _truncate_mastodon_status(base, article.canonical_url, tags)


def _truncate_mastodon_status(text: str, canonical_url: str, tags: list[str]) -> str:
    hashtags = []
    for tag in tags:
        token = re.sub(r"[^a-zA-Z0-9_]", "", tag)
        if token:
            hashtags.append(f"#{token}")
        if len(hashtags) >= 3:
            break

    suffix_parts = [canonical_url]
    if hashtags:
        suffix_parts.append(" ".join(hashtags))
    suffix = "\n\n" + "\n".join(suffix_parts)

    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace(canonical_url, "").strip()
    max_prefix_len = max(40, 450 - len(suffix))
    prefix = cleaned[:max_prefix_len].rstrip()
    if len(cleaned) > max_prefix_len:
        prefix = prefix.rstrip(". ") + "..."
    return (prefix + suffix).strip()


def _sanitize_tags(seed_tags: list[str], article: SourceArticle, default_tags: list[str]) -> list[str]:
    combined = [*seed_tags, *article.tags, *article.categories, *default_tags]
    seen: set[str] = set()
    cleaned: list[str] = []

    for tag in combined:
        token = re.sub(r"[^a-zA-Z0-9_]", "", tag.lower().replace("-", ""))
        if not token or len(token) > 40:
            continue
        if token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
        if len(cleaned) >= 6:
            break

    if not cleaned:
        cleaned = ["wappkit", "software", "saas"]
    return cleaned[:6]
