"""Conservative per-request Groq rate limiter for RAGAS judge calls.

Unlike sleeping between RAGAS *scores*, this HTTPX transport meters every
underlying OpenAI-compatible HTTP request. In particular, FactualCorrectness
makes multiple judge requests per score. On 429, it retries only the rejected
HTTP request, not all previously successful subcalls of the same score.

No application logic, answer, ground truth, or retrieval result is changed.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque

import httpx


_RETRY_SECONDS = re.compile(
    r"(?:please\s+try\s+again\s+in|retry\s+after)\s*"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?\s*)?"
    r"(?P<seconds>\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?",
    re.IGNORECASE,
)


def retry_after_seconds(response: httpx.Response, body: bytes) -> float:
    """Prefer the real Retry-After header; fall back to Groq's error message."""
    header = response.headers.get('retry-after', '').strip()
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
    try:
        error = json.loads(body).get('error', {})
        message = str(error.get('message', ''))
    except (ValueError, AttributeError, TypeError):
        message = body.decode('utf-8', 'replace')
    match = _RETRY_SECONDS.search(message)
    if match:
        return float(match.group('minutes') or 0) * 60 + float(match.group('seconds') or 0)
    return 65.0  # Conservative fallback when the server gives no usable delay.


def completion_tokens(body: bytes) -> int:
    """Count actual generated tokens, including reasoning tokens if reported."""
    try:
        usage = json.loads(body).get('usage', {})
        return max(0, int(usage.get('completion_tokens') or 0))
    except (ValueError, AttributeError, TypeError):
        return 0


class GroqQuotaTransport(httpx.AsyncBaseTransport):
    """Serializes requests, tracks 1-minute output usage, retries 429 safely.

    The reserved-token heuristic is intentionally conservative: it holds room
    for the *next* completion's output before sending it. If a completion uses
    more than the reserve, the next request is paused. Unexpected 429 errors
    use Retry-After from Groq instead of restarting the entire RAGAS metric.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None, *,
                 output_tpm: int = 1000, reserve: int = 400,
                 window_s: float = 65.0, gap_s: float = 3.0,
                 max_429_retries: int = 8, max_auto_wait_s: float = 180.0,
                 retry_padding_s: float = 4.0):
        if output_tpm <= 0 or reserve <= 0 or reserve > output_tpm:
            raise ValueError('Require 0 < reserve <= output_tpm')
        if window_s <= 0 or gap_s < 0 or max_429_retries < 0:
            raise ValueError('Invalid quota interval or retry count')
        self.inner = inner if inner is not None else httpx.AsyncHTTPTransport(retries=0)
        self.output_tpm = output_tpm
        self.reserve = reserve
        self.window_s = window_s
        self.gap_s = gap_s
        self.max_429_retries = max_429_retries
        self.max_auto_wait_s = max_auto_wait_s
        self.retry_padding_s = retry_padding_s
        self.events: deque[tuple[float, int]] = deque()
        self.last_sent = -float('inf')
        self.lock = asyncio.Lock()
        self._clock = time.monotonic
        self._sleep = asyncio.sleep

    async def _throttle(self) -> None:
        while True:
            now = self._clock()
            while self.events and now - self.events[0][0] >= self.window_s:
                self.events.popleft()
            output_used = sum(tokens for _, tokens in self.events)
            spacing = max(0.0, self.last_sent + self.gap_s - now)
            budget = 0.0
            if output_used + self.reserve > self.output_tpm and self.events:
                budget = max(0.0, self.events[0][0] + self.window_s - now)
            wait = max(spacing, budget)
            if wait <= 0:
                return
            print(f'Judge quota pacing: pausing {wait:.0f}s before next API request.', flush=True)
            await self._sleep(wait)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # RAGAS may issue several requests within a single score. This lock
        # limits even those requests, including during recovery waits.
        async with self.lock:
            for attempt in range(self.max_429_retries + 1):
                await self._throttle()
                self.last_sent = self._clock()
                response = await self.inner.handle_async_request(request)
                body = await response.aread()
                if response.status_code != 429:
                    if 200 <= response.status_code < 300:
                        tokens = completion_tokens(body)
                        # If usage is absent, reserve a conservative estimate.
                        self.events.append((self._clock(), tokens or self.reserve))
                    return response

                wait = retry_after_seconds(response, body) + self.retry_padding_s
                await response.aclose()
                if attempt >= self.max_429_retries or wait > self.max_auto_wait_s:
                    # Preserve the 429 for the outer evaluation runner to save
                    # a checkpoint, rather than waiting indefinitely.
                    return httpx.Response(429, headers={'content-type': 'application/json'},
                                          content=body, request=request)
                print(f'Groq 429: recovering this API request in {wait:.0f}s '
                      f'(retry {attempt + 1}/{self.max_429_retries}).', flush=True)
                await self._sleep(wait)
        raise AssertionError('unreachable')

    async def aclose(self) -> None:
        await self.inner.aclose()
