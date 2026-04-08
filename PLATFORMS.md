# Platform Status

This file tracks which external distribution platforms are already wired into `wappkit-social-distributor`.

## Integrated Now

- `DEV.to`
  - Type: long-form article
  - Auth: API key
  - Status: live and already tested in production

- `Blogger / Blogspot`
  - Type: long-form article
  - Auth: access token
  - Status: code integrated, waiting for real token setup

- `WordPress.com`
  - Type: long-form article
  - Auth: access token
  - Status: code integrated, waiting for real token setup

- `Mastodon`
  - Type: short summary + source link
  - Auth: access token
  - Status: code integrated, waiting for real token setup

## Evaluated But Not Integrated Yet

- `WordPress self-hosted`
  - Possible through the WordPress REST API
  - Not added yet because current target is WordPress.com

- `Tumblr`
  - Possible through the Tumblr API
  - Not added yet because Blogger / WordPress.com cover the main blog-distribution need first

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
