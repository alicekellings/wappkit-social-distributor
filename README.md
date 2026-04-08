# wappkit-social-distributor

`wappkit-social-distributor` is the dedicated online distribution worker for Wappkit.

It does one job:

1. detect newly published blog posts from `wappkit-web`
2. adapt them for external platforms
3. publish them platform by platform
4. keep delivery state in a persistent data directory

The first live target is `DEV.to`.

## Phase 1 Scope

- pull the latest blog candidates from `sitemap.xml`
- skip anything already delivered to `DEV.to`
- load the original article source from the public GitHub repo when possible
- fall back to webpage extraction if raw source is unavailable
- rewrite the article for `DEV.to`
- publish to `DEV.to` or save a dry-run preview
- persist delivery history in SQLite

## Rewrite Routing

The `DEV.to` rewrite flow now supports a reusable LLM routing layer:

- public API pool first when enabled
- direct OpenAI-compatible endpoint second if configured
- fallback providers such as Groq, NVIDIA, or Cloudflare after that
- deterministic light rewrite fallback if no model route is usable

This routing logic lives in `app/llm_router.py` so future platforms can reuse it.

Supported public pool inputs:

- `PUBLIC_API_LIST_FILE`
- `PUBLIC_API_LIST_URL`
- `PUBLIC_API_LIST_TEXT`

Supported fallback config inputs:

- `MODEL_POOL_CONFIG_FILE`
- `MODEL_POOL_CONFIG_URL`
- `MODEL_POOL_CONFIG_JSON`

Or provider-specific env vars:

- `FALLBACK_GROQ_*`
- `FALLBACK_NVIDIA_*`
- `FALLBACK_CLOUDFLARE_*`

## Local Usage

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main discover --limit 5
python -m app.main run-once --dry-run
python -m app.main run-once --slug choosing-a-clean-tool-structure-for-wappkit --dry-run
```

## Deployment Direction

Recommended first deployment shape:

- one long-running worker process
- one persistent disk mounted to `/data`
- worker checks every 30 minutes

## Render Deployment

This repo now includes [render.yaml](./render.yaml) for a Render Blueprint deployment.

Recommended Render setup:

- service type: `Background Worker`
- runtime: `Docker`
- persistent disk mounted at `/data`
- fill secret env vars in Render:
  - `DEVTO_API_KEY`
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL` if you are not using the default OpenAI endpoint

If you want the first few runs to stay safe, keep:

```bash
DEVTO_PUBLISH_STATUS=draft
```

After verifying the output, switch it to:

```bash
DEVTO_PUBLISH_STATUS=published
```
