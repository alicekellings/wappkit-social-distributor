# Wappkit Social Distributor Tasks

## Current State

- [x] `DEV.to` live publishing integrated
- [x] `Blogger` live publishing integrated
- [x] `WordPress.com` live publishing integrated
- [x] `Mastodon` live publishing integrated
- [x] `Tumblr` OAuth2 publishing reauthorized and re-stabilized
- [x] `Write.as` anonymous publishing integrated
- [x] Multi-platform worker verified on Railway
- [x] Delivery state persisted in SQLite
- [x] Secrets can load from a single config file
- [x] `GitBook` removed from the active platform set

## Operational Follow-Ups

- [ ] Move live secrets out of tracked `railway.secrets.json` into `/data/wappkit-secrets.json` or server-managed secrets when deployment is moved off Railway
- [ ] Keep `/data/delivery-state.sqlite3` and `/data/tumblr-oauth.json` during any server migration
- [ ] Re-check `verify-platforms` after every token rotation or deployment environment change
- [ ] Re-check a real `run-selected-once` after any deployment move

## Known Risk Areas

- [ ] `Tumblr` depends on refresh-token continuity and should not be treated as a permanent static token
- [ ] `DEV.to` can reject duplicate canonical URLs if local delivery state is missing older post history
- [ ] Local pytest on this machine may require `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `PYTHONPATH=.`
