
"""Groq API client for ReportLens AI."""

import os
from groq import Groq


def chat(
    messages,
    *,
    api_key=None,
    model=None,
    temperature=0,
):
    key = api_key or os.getenv("GROQ_API_KEY")

    if not key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Check your .env file."
        )

    selected_model = (
        model
        or os.getenv("GROQ_MODEL")
        or "openai/gpt-oss-20b"
    )

    client = Groq(api_key=key)

    params = {
        "model": selected_model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": 2048,
        "timeout": 60,
    }

    if selected_model.startswith("openai/gpt-oss-"):
        params["reasoning_effort"] = "low"

    completion = client.chat.completions.create(**params)

    return completion.choices[0].message.content or ""
