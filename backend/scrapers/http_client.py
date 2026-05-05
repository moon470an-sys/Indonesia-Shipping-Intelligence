"""Shared HTTP helpers with exponential backoff."""
from __future__ import annotations

import time
from typing import Any, Callable

import requests

from backend.config import HTTP_RETRY_DELAYS, REQUEST_TIMEOUT, build_logger

log = build_logger("http")


def _do_with_retry(fn: Callable[[], requests.Response], target: str) -> requests.Response | None:
    last_exc: Exception | None = None
    for i, delay in enumerate([0] + HTTP_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            resp = fn()
            if resp.status_code in (200, 201):
                return resp
            log.warning("HTTP %s for %s (attempt %d)", resp.status_code, target, i + 1)
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
        except requests.RequestException as exc:
            log.warning("Request error %s for %s (attempt %d)", exc, target, i + 1)
            last_exc = exc
    log.error("Giving up on %s: %s", target, last_exc)
    return None


def post(url: str, headers: dict, data: dict | str, target: str) -> requests.Response | None:
    return _do_with_retry(
        lambda: requests.post(url, headers=headers, data=data, timeout=REQUEST_TIMEOUT),
        target,
    )


def get(url: str, headers: dict, target: str, params: dict[str, Any] | None = None) -> requests.Response | None:
    return _do_with_retry(
        lambda: requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT),
        target,
    )
