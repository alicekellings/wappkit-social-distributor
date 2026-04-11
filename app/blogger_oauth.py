from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import urlencode

import requests


AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKEN_INFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"
DEFAULT_SCOPE = "https://www.googleapis.com/auth/blogger"


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    scope: str = DEFAULT_SCOPE,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "access_type": "offline",
            "prompt": "consent",
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
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
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
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def verify_access_token(access_token: str, timeout: int = 30) -> dict:
    response = requests.get(
        TOKEN_INFO_URL,
        params={"access_token": access_token},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def save_blogger_tokens_to_config(
    path: Path,
    access_token: str,
    refresh_token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    blog_url: str | None = None,
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

    payload["BLOGGER_ACCESS_TOKEN_B64"] = base64.b64encode(access_token.encode("utf-8")).decode("utf-8")
    if refresh_token:
        payload["BLOGGER_REFRESH_TOKEN_B64"] = base64.b64encode(refresh_token.encode("utf-8")).decode("utf-8")
    if client_id:
        payload["BLOGGER_CLIENT_ID"] = client_id
    if client_secret:
        payload["BLOGGER_CLIENT_SECRET_B64"] = base64.b64encode(client_secret.encode("utf-8")).decode("utf-8")
    if blog_url:
        payload["BLOGGER_BLOG_URL"] = blog_url

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
