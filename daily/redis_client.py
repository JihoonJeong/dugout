"""Upstash Redis REST client — 최소 구현."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

def is_redis_available() -> bool:
    return bool(os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"))


class UpstashRedis:
    """Upstash Redis REST API 래퍼."""

    def __init__(self):
        url = os.getenv("UPSTASH_REDIS_REST_URL", "")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
        if not url or not token:
            raise RuntimeError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be set")
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._client = httpx.Client(timeout=10)

    def _cmd(self, *args: str) -> Any:
        resp = self._client.post(self._url, headers=self._headers, json=list(args))
        resp.raise_for_status()
        data = resp.json()
        return data.get("result")

    def get(self, key: str) -> str | None:
        return self._cmd("GET", key)

    def set(self, key: str, value: str) -> None:
        self._cmd("SET", key, value)

    def delete(self, key: str) -> None:
        self._cmd("DEL", key)

    def keys(self, pattern: str) -> list[str]:
        result = self._cmd("KEYS", pattern)
        return result if result else []

    def get_json(self, key: str) -> Any:
        raw = self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: Any) -> None:
        self.set(key, json.dumps(value))
