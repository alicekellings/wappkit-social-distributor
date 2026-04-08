from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI

from app.config import Config


@dataclass(slots=True)
class LLMCandidate:
    name: str
    api_key: str
    base_url: str
    model: str
    source: str
    response_time: float | None = None


class LLMRouter:
    """Reusable OpenAI-compatible router for public pools and fallback providers."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.candidates = resolve_llm_candidates(config)
        self._candidate_index = 0
        self.active_candidate: LLMCandidate | None = None
        self.client: OpenAI | None = None

        if self.candidates:
            self._activate_candidate(0)

    @property
    def enabled(self) -> bool:
        return self.client is not None and bool(self.candidates)

    @property
    def active_label(self) -> str | None:
        if not self.active_candidate:
            return None
        return f"{self.active_candidate.name} | {self.active_candidate.model}"

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = self._create_chat_completion(messages, temperature, require_text=True)
        content = self._extract_text(response)
        if content:
            return content
        raise ValueError("Model returned no text content.")

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict[str, Any]:
        attempts = [
            (
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                {"response_format": {"type": "json_object"}},
            ),
            (
                [
                    {
                        "role": "system",
                        "content": system_prompt
                        + "\n\nReturn one raw JSON object only. No markdown fences. No tools. No commentary.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                {},
            ),
        ]

        last_error: Exception | None = None
        for messages, extra_kwargs in attempts:
            try:
                response = self._create_chat_completion(messages, temperature, require_text=True, **extra_kwargs)
                content = self._extract_text(response)
                if not content:
                    raise ValueError("Model returned no JSON text.")
                return self._parse_json_content(content)
            except Exception as exc:
                last_error = exc
                continue

        raise ValueError(f"Model did not return parseable JSON after retries: {last_error}")

    def _create_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        require_text: bool = False,
        **kwargs: Any,
    ) -> Any:
        if not self.client:
            raise RuntimeError("No usable LLM candidate available.")

        last_error: Exception | None = None

        for index in self._candidate_indexes():
            self._activate_candidate(index)
            assert self.client is not None
            try:
                response = self.client.chat.completions.create(
                    model=self.active_candidate.model,
                    temperature=temperature,
                    messages=messages,
                    **kwargs,
                )
                if require_text and not self._extract_text(response):
                    last_error = ValueError("Model returned no text content.")
                    continue
                return response
            except Exception as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("No completion candidates were available.")

    def _candidate_indexes(self) -> list[int]:
        total = len(self.candidates)
        return [((self._candidate_index + offset) % total) for offset in range(total)]

    def _activate_candidate(self, index: int) -> None:
        candidate = self.candidates[index]
        if (
            self.active_candidate
            and self._candidate_index == index
            and self.active_candidate.api_key == candidate.api_key
            and self.active_candidate.base_url == candidate.base_url
            and self.active_candidate.model == candidate.model
        ):
            return

        self._candidate_index = index
        self.active_candidate = candidate
        self.client = OpenAI(api_key=candidate.api_key, base_url=candidate.base_url)

    def _extract_text(self, response: Any) -> str:
        message = response.choices[0].message
        content = message.content

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
                elif hasattr(part, "type") and getattr(part, "type") == "text":
                    text_parts.append(str(getattr(part, "text", "")))
            return "".join(text_parts).strip()

        return ""

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.S)
        if fenced_match:
            return json.loads(fenced_match.group(1))

        object_match = re.search(r"(\{.*\})", content, re.S)
        if object_match:
            return json.loads(object_match.group(1))

        raise ValueError(f"Model did not return parseable JSON: {content[:300]}")


def resolve_llm_candidates(config: Config) -> list[LLMCandidate]:
    ordered: list[LLMCandidate] = []

    for candidate in resolve_public_api_selections(config):
        _append_unique(ordered, candidate)

    direct_candidate = _build_direct_candidate(config)
    if direct_candidate is not None:
        _append_unique(ordered, direct_candidate)

    for candidate in _load_model_pool_candidates(config):
        _append_unique(ordered, candidate)

    for candidate in _load_direct_fallback_candidates(config):
        _append_unique(ordered, candidate)

    return ordered


def resolve_public_api_selections(config: Config) -> list[LLMCandidate]:
    if not config.use_public_api_pool:
        return []

    source_text = _load_public_api_source_text(config)
    if not source_text:
        return []

    cache_key = _build_public_api_cache_key(config, source_text)
    cached = _load_cached_public_api_selections(config, cache_key)
    if cached:
        return cached

    candidates = _parse_public_api_candidates(source_text)
    if not candidates:
        return []

    successes = _probe_public_candidates(config, candidates)
    if not successes:
        return []

    ordered = sorted(successes, key=lambda item: (item.response_time or 9999, item.name.lower()))
    _save_cached_public_api_selections(config, cache_key, ordered)
    return ordered


def _build_direct_candidate(config: Config) -> LLMCandidate | None:
    if not config.openai_api_key:
        return None
    return LLMCandidate(
        name="configured-openai-compatible",
        api_key=config.openai_api_key,
        base_url=(config.openai_base_url or "https://api.openai.com/v1").rstrip("/"),
        model=config.openai_model,
        source="env.openai",
    )


def _load_model_pool_candidates(config: Config) -> list[LLMCandidate]:
    raw = _load_model_pool_payload(config)
    if not raw:
        return []

    candidates: list[LLMCandidate] = []
    for item in raw.get("primary_pool", []) or []:
        try:
            candidates.append(
                LLMCandidate(
                    name=str(item["name"]),
                    api_key=str(item["api_key"]),
                    base_url=_normalize_base_url(str(item["base_url"])),
                    model=str(item["model"]),
                    source="model_pool.primary",
                )
            )
        except Exception:
            continue

    fallback_pool = raw.get("fallback_pool", {}) or {}
    candidates.extend(_parse_provider_block("groq", fallback_pool.get("groq"), default_base_url="https://api.groq.com/openai/v1"))
    candidates.extend(
        _parse_provider_block(
            "nvidia",
            fallback_pool.get("nvidia"),
            default_base_url="https://integrate.api.nvidia.com/v1",
        )
    )
    candidates.extend(_parse_cloudflare_block(fallback_pool.get("cloudflare")))
    return candidates


def _load_direct_fallback_candidates(config: Config) -> list[LLMCandidate]:
    candidates: list[LLMCandidate] = []

    if config.fallback_groq_api_key:
        for model in config.fallback_groq_models or []:
            candidates.append(
                LLMCandidate(
                    name=f"groq-{model}",
                    api_key=config.fallback_groq_api_key,
                    base_url=_normalize_base_url(config.fallback_groq_base_url),
                    model=model,
                    source="env.fallback.groq",
                )
            )

    if config.fallback_nvidia_api_key:
        for model in config.fallback_nvidia_models or []:
            candidates.append(
                LLMCandidate(
                    name=f"nvidia-{model}",
                    api_key=config.fallback_nvidia_api_key,
                    base_url=_normalize_base_url(config.fallback_nvidia_base_url),
                    model=model,
                    source="env.fallback.nvidia",
                )
            )

    if config.fallback_cloudflare_api_key and config.fallback_cloudflare_account_id:
        base_url = _normalize_base_url(
            f"https://api.cloudflare.com/client/v4/accounts/{config.fallback_cloudflare_account_id}/ai/v1"
        )
        for model in config.fallback_cloudflare_models or []:
            candidates.append(
                LLMCandidate(
                    name=f"cloudflare-{model}",
                    api_key=config.fallback_cloudflare_api_key,
                    base_url=base_url,
                    model=model,
                    source="env.fallback.cloudflare",
                )
            )

    return candidates


def _load_public_api_source_text(config: Config) -> str | None:
    if config.public_api_list_text:
        return config.public_api_list_text.strip()

    if config.public_api_list_file and config.public_api_list_file.exists():
        return config.public_api_list_file.read_text(encoding="utf-8")

    if config.public_api_list_url:
        response = requests.get(config.public_api_list_url, timeout=config.request_timeout_seconds)
        response.raise_for_status()
        return response.text

    return None


def _parse_public_api_candidates(payload: str) -> list[LLMCandidate]:
    candidates: list[LLMCandidate] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        name, key, url, model = parts[:4]
        candidates.append(
            LLMCandidate(
                name=name,
                api_key=key,
                base_url=url.rstrip("/"),
                model=model,
                source="public_api_pool",
            )
        )
    return candidates


def _build_candidate_urls(base_url: str) -> list[str]:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return []
    candidates = [normalized]
    if normalized.endswith("/v1"):
        candidates.append(normalized[:-3].rstrip("/"))
    else:
        candidates.append(f"{normalized}/v1")
    return list(dict.fromkeys(item for item in candidates if item))


def _probe_public_candidates(config: Config, candidates: list[LLMCandidate]) -> list[LLMCandidate]:
    results: list[LLMCandidate] = []
    with ThreadPoolExecutor(max_workers=max(1, config.public_api_probe_workers)) as executor:
        futures = [executor.submit(_probe_public_candidate, config, candidate) for candidate in candidates]
        for future in as_completed(futures):
            candidate = future.result()
            if candidate is not None:
                results.append(candidate)
    return results


def _probe_public_candidate(config: Config, candidate: LLMCandidate) -> LLMCandidate | None:
    session = requests.Session()
    headers = {
        "Authorization": f"Bearer {candidate.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": candidate.model,
        "messages": [{"role": "user", "content": config.public_api_probe_prompt}],
        "max_tokens": 60,
        "temperature": 0.2,
        "stream": False,
    }

    for base_url in _build_candidate_urls(candidate.base_url):
        endpoint = f"{base_url}/chat/completions"
        try:
            started = time.time()
            response = session.post(endpoint, headers=headers, json=payload, timeout=config.public_api_probe_timeout)
            elapsed = round(time.time() - started, 2)
            if response.status_code != 200:
                continue
            data = response.json()
            if _is_success_payload(data):
                return LLMCandidate(
                    name=candidate.name,
                    api_key=candidate.api_key,
                    base_url=base_url,
                    model=candidate.model,
                    source=candidate.source,
                    response_time=elapsed,
                )
        except Exception:
            continue
    return None


def _is_success_payload(data: dict[str, Any]) -> bool:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first = choices[0]
    if not isinstance(first, dict):
        return False
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return True
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and str(item.get("text", "")).strip():
                    return True
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return True
    return False


def _load_model_pool_payload(config: Config) -> dict[str, Any]:
    raw_text: str | None = None
    if config.model_pool_config_json:
        raw_text = config.model_pool_config_json
    elif config.model_pool_config_file and config.model_pool_config_file.exists():
        raw_text = config.model_pool_config_file.read_text(encoding="utf-8")
    elif config.model_pool_config_url:
        response = requests.get(config.model_pool_config_url, timeout=config.request_timeout_seconds)
        response.raise_for_status()
        raw_text = response.text

    if not raw_text:
        return {}

    try:
        return json.loads(raw_text)
    except Exception:
        return {}


def _parse_provider_block(provider_name: str, payload: Any, default_base_url: str) -> list[LLMCandidate]:
    if not isinstance(payload, dict):
        return []
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        return []
    base_url = _normalize_base_url(str(payload.get("base_url") or default_base_url))
    models = payload.get("models") or []
    candidates: list[LLMCandidate] = []
    for model in models:
        model_name = str(model).strip()
        if not model_name:
            continue
        candidates.append(
            LLMCandidate(
                name=f"{provider_name}-{model_name}",
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                source=f"model_pool.{provider_name}",
            )
        )
    return candidates


def _parse_cloudflare_block(payload: Any) -> list[LLMCandidate]:
    if not isinstance(payload, dict):
        return []
    api_key = str(payload.get("api_key") or "").strip()
    account_id = str(payload.get("account_id") or "").strip()
    if not api_key or not account_id:
        return []
    base_url = _normalize_base_url(f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1")
    candidates: list[LLMCandidate] = []
    for model in payload.get("models") or []:
        model_name = str(model).strip()
        if not model_name:
            continue
        candidates.append(
            LLMCandidate(
                name=f"cloudflare-{model_name}",
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                source="model_pool.cloudflare",
            )
        )
    return candidates


def _normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def _append_unique(candidates: list[LLMCandidate], candidate: LLMCandidate) -> None:
    signature = (candidate.api_key, candidate.base_url, candidate.model)
    existing = {(item.api_key, item.base_url, item.model) for item in candidates}
    if signature not in existing:
        candidates.append(candidate)


def _public_api_cache_path(config: Config) -> Path:
    return config.outputs_dir / "llm-public-api-selection.json"


def _build_public_api_cache_key(config: Config, source_text: str) -> str:
    origin = str(config.public_api_list_file or config.public_api_list_url or "inline")
    digest = sha256(source_text.encode("utf-8")).hexdigest()
    return f"{origin}:{digest}"


def _load_cached_public_api_selections(config: Config, cache_key: str) -> list[LLMCandidate]:
    cache_path = _public_api_cache_path(config)
    if not cache_path.exists():
        return []

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        created_at = float(payload.get("created_at", 0))
        ttl_seconds = max(0, config.public_api_cache_ttl_minutes) * 60
        if ttl_seconds and time.time() - created_at > ttl_seconds:
            return []
        if payload.get("cache_key") != cache_key:
            return []
        selections = payload.get("selections")
        if not isinstance(selections, list):
            return []
        return [
            LLMCandidate(
                name=str(item["name"]),
                api_key=str(item["api_key"]),
                base_url=str(item["base_url"]),
                model=str(item["model"]),
                source=str(item.get("source") or "public_api_pool"),
                response_time=float(item["response_time"]) if item.get("response_time") is not None else None,
            )
            for item in selections
        ]
    except Exception:
        return []


def _save_cached_public_api_selections(config: Config, cache_key: str, selections: list[LLMCandidate]) -> None:
    config.ensure_runtime_dirs()
    cache_path = _public_api_cache_path(config)
    payload = {
        "created_at": time.time(),
        "cache_key": cache_key,
        "selections": [
            {
                "name": selection.name,
                "api_key": selection.api_key,
                "base_url": selection.base_url,
                "model": selection.model,
                "source": selection.source,
                "response_time": selection.response_time,
            }
            for selection in selections
        ],
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
