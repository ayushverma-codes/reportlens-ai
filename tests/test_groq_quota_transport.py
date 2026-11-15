"""No-network tests of per-request Groq output-token pacing and 429 recovery."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from evaluation.groq_quota_transport import (
    GroqQuotaTransport, completion_tokens, retry_after_seconds,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def handle_async_request(self, request):
        self.calls += 1
        assert self.replies, 'unexpected extra HTTP request'
        code, body, headers = self.replies.pop(0)
        return httpx.Response(code, json=body, headers=headers, request=request)


def ok(tokens):
    return (200, {'choices': [{'message': {'content': 'OK'}}],
                  'usage': {'completion_tokens': tokens}}, {})


def too_many(wait):
    return (429, {'error': {'message': f'Rate limit reached. Please try again in {wait}s.'}}, {})


def test_parses_groq_retry_message_and_usage():
    resp = httpx.Response(429)
    body = json.dumps({'error': {'message': 'Please try again in 1m34.608s.'}}).encode()
    assert retry_after_seconds(resp, body) == pytest.approx(94.608)
    assert completion_tokens(json.dumps({'usage': {'completion_tokens': 954}}).encode()) == 954
    assert retry_after_seconds(httpx.Response(429, headers={'retry-after': '7.5'}), body) == 7.5


def test_retries_only_failed_http_request_on_429():
    async def check():
        fake = FakeTransport([too_many(16.5), ok(321)])
        clock = FakeClock()
        limiter = GroqQuotaTransport(fake, gap_s=0)
        limiter._clock = lambda: clock.now
        limiter._sleep = clock.sleep
        async with httpx.AsyncClient(transport=limiter) as client:
            response = await client.post('https://api.groq.com/openai/v1/chat/completions', json={})
        assert response.status_code == 200
        assert fake.calls == 2
        assert clock.waits == [20.5]  # 16.5 seconds from server + 4 seconds safety
    asyncio.run(check())


def test_waits_between_internal_requests_when_output_budget_low():
    async def check():
        fake = FakeTransport([ok(954), ok(321)])
        clock = FakeClock()
        limiter = GroqQuotaTransport(fake, gap_s=0)
        limiter._clock = lambda: clock.now
        limiter._sleep = clock.sleep
        async with httpx.AsyncClient(transport=limiter) as client:
            a = await client.post('https://api.groq.com/openai/v1/chat/completions', json={})
            b = await client.post('https://api.groq.com/openai/v1/chat/completions', json={})
        assert (a.status_code, b.status_code) == (200, 200)
        assert fake.calls == 2
        assert clock.waits == [65.0]
    asyncio.run(check())


def test_leaves_very_long_429_as_error_for_resume():
    async def check():
        fake = FakeTransport([too_many(600)])
        limiter = GroqQuotaTransport(fake, max_auto_wait_s=180)
        async with httpx.AsyncClient(transport=limiter) as client:
            response = await client.get('https://api.groq.com/openai/v1/models')
        assert response.status_code == 429
        assert fake.calls == 1
    asyncio.run(check())


def test_validates_quota_config():
    with pytest.raises(ValueError, match='reserve'):
        GroqQuotaTransport(output_tpm=1000, reserve=2000)
