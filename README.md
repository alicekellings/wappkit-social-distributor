# wappkit-social-distributor

`wappkit-social-distributor` is the dedicated online distribution worker for Wappkit.

It does one job:

1. detect newly published blog posts from `wappkit-web`
2. adapt them for external platforms
3. publish them platform by platform
4. keep delivery state in a persistent data directory

The first live target is `DEV.to`.

The next integrated targets are:

- `Blogger / Blogspot`
- `WordPress.com`
- `Mastodon`

## Phase 1 Scope

- pull the latest blog candidates from `sitemap.xml`
- skip anything already delivered to `DEV.to`
- load the original article source from the public GitHub repo when possible
- fall back to webpage extraction if raw source is unavailable
- rewrite the article for `DEV.to`
- publish to `DEV.to` or save a dry-run preview
- optionally rewrite and publish to `Blogger`
- optionally rewrite and publish to `WordPress.com`
- optionally rewrite and publish short social posts to `Mastodon`
- persist delivery history in SQLite

## Rewrite Routing

The `DEV.to` rewrite flow now supports a reusable LLM routing layer:

- public API pool first when enabled
- direct OpenAI-compatible endpoint second if configured
- fallback providers such as Groq, NVIDIA, or Cloudflare after that
- deterministic light rewrite fallback if no model route is usable

This routing logic lives in `app/llm_router.py` so future platforms can reuse it.

Current publication policy:

- LLM rewrites aim for a moderate DEV.to adaptation, not a mirror copy
- fallback rewrites are safety drafts only
- if `DEVTO_PUBLISH_STATUS=published`, the worker still forces `fallback` rewrites to stay draft unless you disable `DEVTO_REQUIRE_LLM_FOR_PUBLICATION`
- Blogger follows the same safety rule through `BLOGGER_REQUIRE_LLM_FOR_PUBLICATION`
- WordPress.com follows the same safety rule through `WORDPRESS_REQUIRE_LLM_FOR_PUBLICATION`
- Mastodon can publish summaries through its API and can also require LLM rewrites through `MASTODON_REQUIRE_LLM_FOR_PUBLICATION`

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
python -m app.main run-blogger-once --dry-run
python -m app.main run-blogger-once --slug choosing-a-clean-tool-structure-for-wappkit --dry-run
python -m app.main run-wordpress-once --dry-run
python -m app.main run-mastodon-once --dry-run
python -m app.main run-selected-once --dry-run
```

## Multi-Platform Worker

Use `DELIVERY_PLATFORMS` to decide which platforms the long-running worker should process.

Examples:

```bash
DELIVERY_PLATFORMS=devto
DELIVERY_PLATFORMS=devto,blogger,wordpress
DELIVERY_PLATFORMS=devto,blogger,wordpress,mastodon
```

The worker now runs all selected platforms in sequence during each cycle.

## Blogger Setup

The Blogger integration is aimed at Blogspot / Blogger blogs such as `wappkit.blogspot.com`.

Required env vars:

- `BLOGGER_ACCESS_TOKEN`
- one of `BLOGGER_BLOG_ID` or `BLOGGER_BLOG_URL`

Recommended safety env vars:

```bash
BLOGGER_PUBLISH_STATUS=draft
BLOGGER_REQUIRE_LLM_FOR_PUBLICATION=1
```

Notes:

- the current implementation uses the official Blogger API
- `BLOGGER_BLOG_URL` can be a domain like `wappkit.blogspot.com` or a full URL
- draft/public behavior mirrors the DEV.to safety policy

Credential location:

- Google Cloud Console is not required for the current flow
- open `https://developers.google.com/oauthplayground/`
- click the gear icon and enable your own OAuth credentials
- use scope `https://www.googleapis.com/auth/blogger`
- complete the authorization flow and copy the returned `access_token`

Troubleshooting notes:

- if Blogger suddenly reports auth failures after Railway variable edits, check the saved env format first
- Railway env vars are safest in plain `KEY=value` form, without JSON syntax and without wrapping the whole value in quotes
- if a token contains unusual special characters and starts behaving inconsistently after copy/paste, regenerate it first, then re-save it carefully in Railway
- if needed later, Blogger can use the same base64 secret pattern as WordPress, but it is not required right now because the current Blogger flow is already working

## WordPress.com Setup

Required env vars:

- `WORDPRESS_ACCESS_TOKEN`
- `WORDPRESS_SITE`

Optional safer secret input:

- `WORDPRESS_ACCESS_TOKEN_B64`

Recommended safety env vars:

```bash
WORDPRESS_PUBLISH_STATUS=draft
WORDPRESS_REQUIRE_LLM_FOR_PUBLICATION=1
```

Notes:

- use the WordPress.com site identifier such as `blogxblog2.wordpress.com`
- the current implementation uses the official WordPress.com REST API
- draft/public behavior mirrors the DEV.to safety policy
- on Railway, `WORDPRESS_ACCESS_TOKEN_B64` is safer than raw `WORDPRESS_ACCESS_TOKEN` because some WordPress tokens contain special characters such as `#`

Credential location:

- create or manage the app at `https://developer.wordpress.com/apps`
- app edit page example: `https://developer.wordpress.com/apps/<app-id>/settings/`
- OAuth details page example: `https://developer.wordpress.com/apps/<app-id>/`
- `Client ID` and `Client Secret` are shown on the app details page, not the settings page
- exchange them for an `access_token` through `https://public-api.wordpress.com/oauth2/token`

Troubleshooting notes:

- if Railway logs show `WORDPRESS_ACCESS_TOKEN is required for publishing`, the variable was not loaded at runtime even if it appears in the UI
- search deploy logs for `Runtime config:` first; this shows whether the worker actually read `wordpress_access_token=yes/no`
- some WordPress.com tokens contain special characters such as `#`, `^`, `@`, `(`, `)`; these can break direct env handling on some platforms
- on Railway, prefer `WORDPRESS_ACCESS_TOKEN_B64` over raw `WORDPRESS_ACCESS_TOKEN`
- if WordPress returns `The OAuth2 token is invalid`, verify the token again or generate a fresh one from the same app credentials
- token validation endpoint:
  - `https://public-api.wordpress.com/oauth2/token-info?client_id=<client_id>&token=<token>`
- app-to-token pairing matters: use a token generated from the same `Client ID` and `Client Secret` that the project is documented with
- if WordPress returns `400 Bad Request`, reduce the payload first and inspect the API response body; tags, categories, or other optional fields may be the cause
- the current code already retries with a minimal `title/content/status` payload after a WordPress 400 response

## Mastodon Setup

Required env vars:

- `MASTODON_BASE_URL`
- `MASTODON_ACCESS_TOKEN`

Recommended safety env vars:

```bash
MASTODON_VISIBILITY=unlisted
MASTODON_REQUIRE_LLM_FOR_PUBLICATION=1
```

Notes:

- Mastodon is handled as a short summary + source link platform, not a full-article mirror
- the current implementation uses the official Mastodon API

## Deployment Direction

Recommended first deployment shape:

- one long-running worker process
- one persistent disk mounted to `/data`
- worker checks every 30 minutes

## Railway Deployment

Current preferred deployment is Railway.

Recommended Railway setup:

- service type: worker / background service
- runtime: Docker
- persistent volume mounted to `/data`
- start command: `python -m app.main worker`
- fill secret env vars in Railway:
  - `DEVTO_API_KEY`
  - `DEVTO_REQUIRE_LLM_FOR_PUBLICATION=1`
  - `USE_PUBLIC_API_POOL=1` if you want public GPT-compatible endpoints to be probed first
  - one of `PUBLIC_API_LIST_TEXT`, `PUBLIC_API_LIST_URL`, or `PUBLIC_API_LIST_FILE`
  - optional fallback vars such as `FALLBACK_GROQ_*`, `FALLBACK_NVIDIA_*`, `FALLBACK_CLOUDFLARE_*`

The existing [render.yaml](./render.yaml) can stay as a fallback reference, but Railway is the current live path.

If you want the first few runs to stay safe, keep:

```bash
DEVTO_PUBLISH_STATUS=draft
```

After verifying the output, switch it to:

```bash
DEVTO_PUBLISH_STATUS=published
```

Recommended safety setting:

```bash
DEVTO_REQUIRE_LLM_FOR_PUBLICATION=1
```

## Credential Notes

Useful current credential entry points:

- `DEV.to`
  - dashboard path: `https://dev.to/settings/account`
  - create or copy API key from the DEV Community API Key section
- `Blogger`
  - token flow page: `https://developers.google.com/oauthplayground/`
  - use Blogger scope and copy the returned `access_token`
- `WordPress.com`
  - app list: `https://developer.wordpress.com/apps`
  - app settings page only edits metadata
  - app details page shows `Client ID` and `Client Secret`

## Debug Checklist

When a platform stops publishing, use this order:

1. check Railway deploy logs for `Runtime config:`
2. confirm the platform token shows as loaded with `yes`
3. confirm the site/blog identifier is correct
4. inspect the first `... delivery failed ...` line for the real API error
5. if the token contains many special characters, suspect env formatting or encoding first
6. regenerate the token only after ruling out env formatting issues

Recommended Railway secret habits:

- prefer plain `KEY=value`
- do not paste JSON into single-variable fields
- do not wrap full values in quotes unless the platform explicitly requires it
- for secrets with problematic special characters, prefer a base64 env input and decode in app code
