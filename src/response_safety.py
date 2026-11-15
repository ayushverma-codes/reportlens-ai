"""Keep answer citations resolvable and avoid displaying backend exceptions."""
from __future__ import annotations

import re

INVALID_CITATIONS = (
    "I couldn't verify source citations for that answer from the retrieved "
    "documents. Please ask a more specific question."
)


def validate_generated_citations(response: str, sources: list[dict]) -> dict:
    """Normalize Groq bracket variants; never pass through invented source IDs.

    A factual answer with no verifiable citation is withheld. Explicit refusals
    may have no citations. This is a structural check, not a claim-support check.
    """
    response = re.sub(
        r'(?:\[|【)\s*(S\d+)\s*(?:\]|】)',
        lambda m: f'[{m.group(1).upper()}]', response,
        flags=re.I,
    )
    allowed = {s['id'] for s in sources}
    response = re.sub(
        r'(?<![\w\[【])S\d+(?![\w\]】])',
        lambda m: f'[{m.group(0)}]' if m.group(0) in allowed else m.group(0),
        response,
    )
    cited = set(re.findall(r'\[(S\d+)\]', response, re.I))
    if cited.difference(allowed):
        return {'answer': INVALID_CITATIONS, 'sources': []}
    if not cited and not re.search(
        r"\b(?:couldn.t|could not|cannot|can.t|unable to|insufficient|not available|"
        r"not provided|not found|no evidence|no information)\b",
        response, re.I,
    ):
        return {'answer': INVALID_CITATIONS, 'sources': []}
    return {'answer': response, 'sources': [s for s in sources if s['id'] in cited]}


def safe_answer_error(error: Exception) -> str:
    """Do not show secrets, request payloads, or raw stack traces in the UI."""
    name = type(error).__name__
    if name == 'RateLimitError':
        return ('Groq rate limit reached (HTTP 429). Retry after the provider '
                'quota recovers; uploaded documents are safe.')
    if name in ('APITimeoutError', 'TimeoutError', 'ConnectTimeout'):
        return 'The model request timed out. Please try again.'
    if name in ('APIConnectionError', 'ConnectError'):
        return 'The model service could not be reached. Please try again.'
    if name in ('AuthenticationError', 'PermissionDeniedError'):
        return 'The Groq API credentials were rejected. Check your configured secret.'
    if isinstance(error, ValueError) and 'GROQ_API_KEY' in str(error):
        return 'GROQ_API_KEY is missing. Add it to your .env file or Streamlit Secrets.'
    return 'The request could not be completed. Check the server logs for details.'
