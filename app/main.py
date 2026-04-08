from __future__ import annotations

import time

import click

from app.config import Config
from app.discovery import discover_articles, get_candidate_by_slug
from app.platforms.devto import DevtoPublisher
from app.rewrite import DevtoRewriter
from app.source_loader import load_source_article
from app.store import DeliveryStore


def describe_rewrite_mode(rewritten) -> str:
    return f"{rewritten.rewrite_source}/{rewritten.rewrite_strength}"


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


@cli.command("worker")
@click.option("--dry-run", is_flag=True, default=False, help="Run continuously without publishing.")
def worker(dry_run: bool) -> None:
    config = Config.load()
    interval_seconds = max(config.check_interval_minutes, 1) * 60
    click.echo(
        f"Starting worker. interval={config.check_interval_minutes}m max_articles_per_run={config.max_articles_per_run}"
    )
    while True:
        try:
            processed = run_devto_once(config, slug=None, dry_run=dry_run)
            click.echo(f"Worker cycle finished. processed={processed}")
        except Exception as exc:
            click.secho(f"Worker cycle error: {exc}", fg="red")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    cli()
