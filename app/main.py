from __future__ import annotations

import time

import click

from app.config import Config
from app.discovery import discover_articles, get_candidate_by_slug
from app.platforms.blogger import BloggerPublisher
from app.platforms.devto import DevtoPublisher
from app.platforms.mastodon import MastodonPublisher
from app.platforms.wordpress_com import WordpressComPublisher
from app.rewrite import BloggerRewriter, DevtoRewriter, MastodonRewriter, WordpressRewriter
from app.source_loader import load_source_article
from app.store import DeliveryStore


SUPPORTED_PLATFORMS = ("devto", "blogger", "wordpress", "mastodon")


def describe_rewrite_mode(rewritten) -> str:
    return f"{rewritten.rewrite_source}/{rewritten.rewrite_strength}"


def normalize_platforms(platforms: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for platform in platforms:
        token = (platform or "").strip().lower()
        if token not in SUPPORTED_PLATFORMS:
            continue
        if token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized or ["devto"]


def log_runtime_config_summary(config: Config) -> None:
    click.echo(
        "Runtime config: "
        f"platforms={','.join(normalize_platforms(config.delivery_platforms))} "
        f"devto_api_key={'yes' if bool(config.devto_api_key) else 'no'} "
        f"blogger_access_token={'yes' if bool(config.blogger_access_token) else 'no'} "
        f"blogger_blog_url={'yes' if bool(config.blogger_blog_url) else 'no'} "
        f"wordpress_access_token={'yes' if bool(config.wordpress_access_token) else 'no'} "
        f"wordpress_site={config.wordpress_site or 'missing'} "
        f"mastodon_access_token={'yes' if bool(config.mastodon_access_token) else 'no'}"
    )


def run_selected_platforms_once(
    config: Config,
    slug: str | None,
    dry_run: bool,
    platforms: list[str] | None = None,
) -> dict[str, int]:
    selected = normalize_platforms(platforms or config.delivery_platforms)
    runners = {
        "devto": run_devto_once,
        "blogger": run_blogger_once,
        "wordpress": run_wordpress_once,
        "mastodon": run_mastodon_once,
    }
    results: dict[str, int] = {}
    for platform in selected:
        results[platform] = runners[platform](config, slug=slug, dry_run=dry_run)
    return results


def run_devto_once(config: Config, slug: str | None, dry_run: bool) -> int:
    config.ensure_runtime_dirs()
    store = DeliveryStore(config.database_path)
    publisher = DevtoPublisher(config)
    rewriter = DevtoRewriter(config)

    if slug:
        candidates = [get_candidate_by_slug(config, slug)]
    else:
        candidates = discover_articles(config, limit=max(config.max_articles_per_run * 3, 10))

    processed = 0

    for candidate in candidates:
        if not slug and store.has_success("devto", candidate.slug):
            continue

        click.echo(f"Preparing DEV.to delivery for: {candidate.slug}")
        source = load_source_article(config, candidate)
        store.mark_attempt(
            platform="devto",
            source_slug=candidate.slug,
            source_url=candidate.url,
            title=source.title,
            source_updated_at=candidate.last_modified,
        )

        try:
            rewritten = rewriter.rewrite(source)
            click.echo(f"Rewrite mode: {describe_rewrite_mode(rewritten)}")
            if rewriter.last_provider_label:
                click.echo(f"Rewrite model: {rewriter.last_provider_label}")
            if rewritten.rewrite_source != "llm":
                click.secho(
                    "Rewrite fallback detected; DEV.to delivery will stay in draft mode for safety.",
                    fg="yellow",
                )
            if dry_run:
                preview_path = publisher.save_preview(
                    rewritten,
                    source,
                    config.outputs_dir / "previews",
                )
                click.secho(f"Dry-run preview saved to: {preview_path}", fg="green")
            else:
                result = publisher.publish(rewritten, source)
                store.mark_success(
                    "devto",
                    candidate.slug,
                    result.external_id,
                    result.url or "",
                )
                if result.is_draft:
                    click.secho(
                        f"Draft created on DEV.to (id={result.external_id}, rewrite={describe_rewrite_mode(rewritten)}). "
                        "Open your DEV.to dashboard to review it.",
                        fg="yellow",
                    )
                else:
                    click.secho(
                        f"Published to DEV.to: {result.url} (rewrite={describe_rewrite_mode(rewritten)})",
                        fg="green",
                    )

            processed += 1
            if processed >= config.max_articles_per_run:
                break
        except Exception as exc:
            store.mark_failure("devto", candidate.slug, str(exc))
            click.secho(f"DEV.to delivery failed for {candidate.slug}: {exc}", fg="red")
            if slug:
                raise

    return processed


def run_blogger_once(config: Config, slug: str | None, dry_run: bool) -> int:
    config.ensure_runtime_dirs()
    store = DeliveryStore(config.database_path)
    publisher = BloggerPublisher(config)
    rewriter = BloggerRewriter(config)

    if slug:
        candidates = [get_candidate_by_slug(config, slug)]
    else:
        candidates = discover_articles(config, limit=max(config.max_articles_per_run * 3, 10))

    processed = 0

    for candidate in candidates:
        if not slug and store.has_success("blogger", candidate.slug):
            continue

        click.echo(f"Preparing Blogger delivery for: {candidate.slug}")
        source = load_source_article(config, candidate)
        store.mark_attempt(
            platform="blogger",
            source_slug=candidate.slug,
            source_url=candidate.url,
            title=source.title,
            source_updated_at=candidate.last_modified,
        )

        try:
            rewritten = rewriter.rewrite(source)
            click.echo(f"Rewrite mode: {describe_rewrite_mode(rewritten)}")
            if rewriter.last_provider_label:
                click.echo(f"Rewrite model: {rewriter.last_provider_label}")
            if rewritten.rewrite_source != "llm":
                click.secho(
                    "Rewrite fallback detected; Blogger delivery will stay in draft mode for safety.",
                    fg="yellow",
                )
            if dry_run:
                preview_path = publisher.save_preview(
                    rewritten,
                    source,
                    config.outputs_dir / "previews",
                )
                click.secho(f"Dry-run preview saved to: {preview_path}", fg="green")
            else:
                result = publisher.publish(rewritten, source)
                store.mark_success(
                    "blogger",
                    candidate.slug,
                    result.external_id,
                    result.url or "",
                )
                if result.is_draft:
                    click.secho(
                        f"Draft created on Blogger (id={result.external_id}, rewrite={describe_rewrite_mode(rewritten)}). "
                        "Review it in Blogger before publishing.",
                        fg="yellow",
                    )
                else:
                    click.secho(
                        f"Published to Blogger: {result.url} (rewrite={describe_rewrite_mode(rewritten)})",
                        fg="green",
                    )

            processed += 1
            if processed >= config.max_articles_per_run:
                break
        except Exception as exc:
            store.mark_failure("blogger", candidate.slug, str(exc))
            click.secho(f"Blogger delivery failed for {candidate.slug}: {exc}", fg="red")
            if slug:
                raise

    return processed


def run_wordpress_once(config: Config, slug: str | None, dry_run: bool) -> int:
    config.ensure_runtime_dirs()
    store = DeliveryStore(config.database_path)
    publisher = WordpressComPublisher(config)
    rewriter = WordpressRewriter(config)

    if slug:
        candidates = [get_candidate_by_slug(config, slug)]
    else:
        candidates = discover_articles(config, limit=max(config.max_articles_per_run * 3, 10))

    processed = 0

    for candidate in candidates:
        if not slug and store.has_success("wordpress", candidate.slug):
            continue

        click.echo(f"Preparing WordPress.com delivery for: {candidate.slug}")
        source = load_source_article(config, candidate)
        store.mark_attempt("wordpress", candidate.slug, candidate.url, source.title, candidate.last_modified)

        try:
            rewritten = rewriter.rewrite(source)
            click.echo(f"Rewrite mode: {describe_rewrite_mode(rewritten)}")
            if rewriter.last_provider_label:
                click.echo(f"Rewrite model: {rewriter.last_provider_label}")
            if rewritten.rewrite_source != "llm":
                click.secho(
                    "Rewrite fallback detected; WordPress.com delivery will stay in draft mode for safety.",
                    fg="yellow",
                )
            if dry_run:
                preview_path = publisher.save_preview(rewritten, source, config.outputs_dir / "previews")
                click.secho(f"Dry-run preview saved to: {preview_path}", fg="green")
            else:
                result = publisher.publish(rewritten, source)
                store.mark_success("wordpress", candidate.slug, result.external_id, result.url or "")
                if result.is_draft:
                    click.secho(
                        f"Draft created on WordPress.com (id={result.external_id}, rewrite={describe_rewrite_mode(rewritten)}). "
                        "Review it in WordPress before publishing.",
                        fg="yellow",
                    )
                else:
                    click.secho(
                        f"Published to WordPress.com: {result.url} (rewrite={describe_rewrite_mode(rewritten)})",
                        fg="green",
                    )

            processed += 1
            if processed >= config.max_articles_per_run:
                break
        except Exception as exc:
            store.mark_failure("wordpress", candidate.slug, str(exc))
            click.secho(f"WordPress.com delivery failed for {candidate.slug}: {exc}", fg="red")
            if slug:
                raise

    return processed


def run_mastodon_once(config: Config, slug: str | None, dry_run: bool) -> int:
    config.ensure_runtime_dirs()
    store = DeliveryStore(config.database_path)
    publisher = MastodonPublisher(config)
    rewriter = MastodonRewriter(config)

    if slug:
        candidates = [get_candidate_by_slug(config, slug)]
    else:
        candidates = discover_articles(config, limit=max(config.max_articles_per_run * 3, 10))

    processed = 0

    for candidate in candidates:
        if not slug and store.has_success("mastodon", candidate.slug):
            continue

        click.echo(f"Preparing Mastodon delivery for: {candidate.slug}")
        source = load_source_article(config, candidate)
        store.mark_attempt("mastodon", candidate.slug, candidate.url, source.title, candidate.last_modified)

        try:
            rewritten = rewriter.rewrite(source)
            click.echo(f"Rewrite mode: {describe_rewrite_mode(rewritten)}")
            if rewriter.last_provider_label:
                click.echo(f"Rewrite model: {rewriter.last_provider_label}")
            if rewritten.rewrite_source != "llm":
                click.secho(
                    "Rewrite fallback detected; Mastodon publish will be blocked by safety rules unless you disable the llm requirement.",
                    fg="yellow",
                )
            if dry_run:
                preview_path = publisher.save_preview(rewritten, source, config.outputs_dir / "previews")
                click.secho(f"Dry-run preview saved to: {preview_path}", fg="green")
            else:
                result = publisher.publish(rewritten, source)
                store.mark_success("mastodon", candidate.slug, result.external_id, result.url or "")
                click.secho(
                    f"Published to Mastodon: {result.url} (rewrite={describe_rewrite_mode(rewritten)})",
                    fg="green",
                )

            processed += 1
            if processed >= config.max_articles_per_run:
                break
        except Exception as exc:
            store.mark_failure("mastodon", candidate.slug, str(exc))
            click.secho(f"Mastodon delivery failed for {candidate.slug}: {exc}", fg="red")
            if slug:
                raise

    return processed


@click.group()
def cli() -> None:
    """Wappkit social distributor CLI."""


@cli.command("discover")
@click.option("--limit", default=5, show_default=True, help="How many article candidates to show.")
def discover(limit: int) -> None:
    config = Config.load()
    candidates = discover_articles(config, limit=limit)
    for candidate in candidates:
        click.echo(f"{candidate.slug} | {candidate.last_modified or 'n/a'} | {candidate.url}")


@cli.command("run-once")
@click.option("--slug", default=None, help="Force a specific blog slug.")
@click.option("--dry-run", is_flag=True, default=False, help="Generate preview files without publishing.")
def run_once(slug: str | None, dry_run: bool) -> None:
    config = Config.load()
    processed = run_devto_once(config, slug=slug, dry_run=dry_run)
    click.echo(f"Processed {processed} article(s).")


@cli.command("run-selected-once")
@click.option("--slug", default=None, help="Force a specific blog slug.")
@click.option("--dry-run", is_flag=True, default=False, help="Generate preview files without publishing.")
def run_selected_once_command(slug: str | None, dry_run: bool) -> None:
    config = Config.load()
    results = run_selected_platforms_once(config, slug=slug, dry_run=dry_run)
    summary = ", ".join(f"{platform}={count}" for platform, count in results.items())
    click.echo(f"Processed article counts: {summary}")


@cli.command("run-blogger-once")
@click.option("--slug", default=None, help="Force a specific blog slug.")
@click.option("--dry-run", is_flag=True, default=False, help="Generate preview files without publishing.")
def run_blogger_once_command(slug: str | None, dry_run: bool) -> None:
    config = Config.load()
    processed = run_blogger_once(config, slug=slug, dry_run=dry_run)
    click.echo(f"Processed {processed} article(s).")


@cli.command("run-wordpress-once")
@click.option("--slug", default=None, help="Force a specific blog slug.")
@click.option("--dry-run", is_flag=True, default=False, help="Generate preview files without publishing.")
def run_wordpress_once_command(slug: str | None, dry_run: bool) -> None:
    config = Config.load()
    processed = run_wordpress_once(config, slug=slug, dry_run=dry_run)
    click.echo(f"Processed {processed} article(s).")


@cli.command("run-mastodon-once")
@click.option("--slug", default=None, help="Force a specific blog slug.")
@click.option("--dry-run", is_flag=True, default=False, help="Generate preview files without publishing.")
def run_mastodon_once_command(slug: str | None, dry_run: bool) -> None:
    config = Config.load()
    processed = run_mastodon_once(config, slug=slug, dry_run=dry_run)
    click.echo(f"Processed {processed} article(s).")


@cli.command("worker")
@click.option("--dry-run", is_flag=True, default=False, help="Run continuously without publishing.")
def worker(dry_run: bool) -> None:
    config = Config.load()
    interval_seconds = max(config.check_interval_minutes, 1) * 60
    selected = normalize_platforms(config.delivery_platforms)
    log_runtime_config_summary(config)
    click.echo(
        f"Starting worker. interval={config.check_interval_minutes}m "
        f"max_articles_per_run={config.max_articles_per_run} platforms={','.join(selected)}"
    )
    while True:
        try:
            results = run_selected_platforms_once(config, slug=None, dry_run=dry_run, platforms=selected)
            summary = ", ".join(f"{platform}={count}" for platform, count in results.items())
            click.echo(f"Worker cycle finished. processed={summary}")
        except Exception as exc:
            click.secho(f"Worker cycle error: {exc}", fg="red")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    cli()
