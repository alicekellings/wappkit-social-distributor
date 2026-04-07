# Wappkit Social Distributor Tasks

## Phase 1: DEV.to First

- [x] Create a dedicated distribution project directory
- [x] Define the first-stage architecture around `sitemap -> source -> rewrite -> DEV.to`
- [x] Add persistent delivery state with SQLite
- [x] Add source discovery from Wappkit `sitemap.xml`
- [x] Add source loading from public GitHub raw article files
- [x] Add webpage extraction fallback
- [x] Add deterministic `DEV.to` rewrite fallback
- [x] Add optional AI rewrite path for higher-quality adaptation
- [x] Add `DEV.to` publishing client
- [x] Add CLI commands for `discover`, `run-once`, and `worker`
- [x] Add Docker and environment templates

## Immediate Next Checks

- [ ] Fill `DEVTO_API_KEY`
- [ ] Run `python -m app.main run-once --dry-run`
- [ ] Review the generated preview under `outputs/previews/`
- [ ] Run one real article publish to `DEV.to`
- [ ] Confirm the article renders correctly on `DEV.to`
