from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import urlencode

import requests


AUTHORIZE_URL = "https://www.tumblr.com/oauth2/authorize"
TOKEN_URL = "https://api.tumblr.com/v2/oauth2/token"
USER_INFO_URL = "https://api.tumblr.com/v2/user/info"
DEFAULT_SCOPE = "basic write offline_access"


def build_authorize_url(client_id: str, redirect_uri: str, state: str, scope: str = DEFAULT_SCOPE) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    timeout: int = 30,
) -> dict:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def refresh_tokens(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: int = 30,
) -> dict:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def verify_access_token(access_token: str, timeout: int = 30) -> dict:
    response = requests.get(
        USER_INFO_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def save_tumblr_tokens_to_config(
    path: Path,
    access_token: str,
    refresh_token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    blog_identifier: str | None = None,
) -> Path:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    payload["TUMBLR_ACCESS_TOKEN_B64"] = base64.b64encode(access_token.encode("utf-8")).decode("utf-8")
    if refresh_token:
        payload["TUMBLR_REFRESH_TOKEN_B64"] = base64.b64encode(refresh_token.encode("utf-8")).decode("utf-8")
    if client_id:
        payload["TUMBLR_CLIENT_ID"] = client_id
    if client_secret:
        payload["TUMBLR_CLIENT_SECRET"] = client_secret
    if blog_identifier:
        payload["TUMBLR_BLOG_IDENTIFIER"] = blog_identifier

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
