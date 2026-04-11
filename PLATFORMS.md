# Platform Status

This file tracks which external distribution platforms are already wired into `wappkit-social-distributor`.

## Integrated Now

- `DEV.to`
  - Type: long-form article
  - Auth: API key
  - Status: live and already tested in production
  - Current target: `https://dev.to/`
  - Credential entry: `https://dev.to/settings/account`
  - Main env vars: `DEVTO_API_KEY`, `DEVTO_PUBLISH_STATUS`, `DEVTO_REQUIRE_LLM_FOR_PUBLICATION`
  - Notes:
    - strong article adaptation is recommended, not light copy editing
    - keep it in `draft` until quality looks stable

- `Blogger / Blogspot`
  - Type: long-form article
  - Auth: access token, with optional refresh-capable OAuth credentials
  - Status: publishing code live; current production token needs renewal
  - Current target: `https://wappkit.blogspot.com/`
  - Credential entry: `https://developers.google.com/oauthplayground/`
  - Main env vars: `BLOGGER_ACCESS_TOKEN`, `BLOGGER_BLOG_URL`, `BLOGGER_PUBLISH_STATUS`, `BLOGGER_REQUIRE_LLM_FOR_PUBLICATION`
  - Optional long-term vars: `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET`, `BLOGGER_REFRESH_TOKEN`
  - Notes:
    - current `BLOGGER_ACCESS_TOKEN` was verified to be expired with a real `401 Invalid Credentials`
    - for quick recovery, renew `BLOGGER_ACCESS_TOKEN`
    - for long-term stability, keep `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET`, and `BLOGGER_REFRESH_TOKEN` in the single secrets file so the worker can auto-refresh
    - if you use the single secrets file, you do not need to manage a pile of Blogger fields in Railway UI

- `WordPress.com`
  - Type: long-form article
  - Auth: access token, with `*_OBF` preferred in tracked repo config
  - Status: live and tested in production
  - Current target: `https://blogxblog2.wordpress.com/`
  - Credential entry:
    - app list: `https://developer.wordpress.com/apps`
    - app details page shows `Client ID` and `Client Secret`
    - token endpoint: `https://public-api.wordpress.com/oauth2/token`
  - Main env vars: `WORDPRESS_SITE`, `WORDPRESS_ACCESS_TOKEN`, `WORDPRESS_ACCESS_TOKEN_B64`, `WORDPRESS_ACCESS_TOKEN_OBF`, `WORDPRESS_PUBLISH_STATUS`, `WORDPRESS_REQUIRE_LLM_FOR_PUBLICATION`
  - Notes:
    - tracked repo config now prefers `WORDPRESS_ACCESS_TOKEN_OBF`
    - when debugging, search logs for `Runtime config:` before anything else
    - if WordPress returns `400`, the code already retries with a minimal payload

- `Mastodon`
  - Type: short summary + source link
  - Auth: access token, with `*_OBF` preferred in tracked repo config
  - Status: live and tested in production
  - Current target: `https://mastodon.social/`
  - Credential entry: `https://mastodon.social/settings/applications`
  - Main env vars: `MASTODON_BASE_URL`, `MASTODON_ACCESS_TOKEN`, `MASTODON_ACCESS_TOKEN_B64`, `MASTODON_ACCESS_TOKEN_OBF`, `MASTODON_VISIBILITY`, `MASTODON_REQUIRE_LLM_FOR_PUBLICATION`
  - Notes:
    - current publishing path works in production
    - tracked repo config now prefers `MASTODON_ACCESS_TOKEN_OBF`
  - for early stage use, `MASTODON_REQUIRE_LLM_FOR_PUBLICATION=0` is more practical
  - Mastodon is intentionally treated as a short social summary platform, not a long-form mirror

- `Tumblr`
  - Type: adapted blog draft / curated note
  - Auth: OAuth2 access token + refresh token
  - Status: live and verified with a real draft publish in Railway
  - Current target: `https://myawesomeblogs.tumblr.com/`
  - Credential entry:
    - app list: `https://www.tumblr.com/oauth/apps`
    - OAuth2 authorize URL: `https://www.tumblr.com/oauth2/authorize`
    - OAuth2 token URL: `https://api.tumblr.com/v2/oauth2/token`
  - Main env vars:
    - `TUMBLR_CLIENT_ID`
    - `TUMBLR_CLIENT_SECRET`
    - `TUMBLR_ACCESS_TOKEN`
    - `TUMBLR_ACCESS_TOKEN_B64`
    - `TUMBLR_ACCESS_TOKEN_OBF`
    - `TUMBLR_REFRESH_TOKEN`
    - `TUMBLR_REFRESH_TOKEN_B64`
    - `TUMBLR_REFRESH_TOKEN_OBF`
    - `TUMBLR_BLOG_IDENTIFIER`
    - `TUMBLR_PUBLISH_STATUS`
    - `TUMBLR_REQUIRE_LLM_FOR_PUBLICATION`
  - Notes:
    - current implementation automatically refreshes the access token after a `401`
    - `offline_access` is mandatory during authorization, otherwise the worker will not get a stable refresh token
    - the repo config is now only the bootstrap source; the worker persists the latest Tumblr OAuth state into `/data/tumblr-oauth.json`
    - after the first successful authorization, later refreshes should not require daily manual token replacement
    - blog identifier can be `myawesomeblogs` or `myawesomeblogs.tumblr.com`
    - tracked repo config now prefers `TUMBLR_*_OBF`
    - current live result was `Draft created on Tumblr`, so the publication chain is already confirmed working

## Evaluated But Not Integrated Yet

- `WordPress self-hosted`
  - Possible through the WordPress REST API
  - Not added yet because current target is WordPress.com

- `LinkedIn`
  - API exists, but publishing is more constrained and less suitable for full-article mirroring

- `X`
  - API exists, but pricing / permission constraints make it lower priority for now

- `Medium`
  - Not a current priority because official publishing access is more limited than the platforms above

## Current Recommendation

For Wappkit right now, the most practical publishing stack is:

1. `DEV.to`
2. `Blogger`
3. `WordPress.com`
4. `Mastodon`
5. `Tumblr`
