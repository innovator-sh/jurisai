"""Ported from jurisai/Backend/app.py (`query_mistral_api`), relocated only.

Still synchronous `requests`, still no timeout (D018), still returns an error
*string* on failure rather than raising (D025 — that string then gets stored
in Mongo and shown to the user as if it were a legal answer). All open,
Sprint 3, where this becomes the `LLMProvider` protocol with Groq as the
default and real retry/timeout handling.
"""

from typing import Any, cast

import requests

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


def query_mistral(prompt: str, api_key: str, model: str = "mistral-medium") -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    strict_prompt = f"""
    You are a legal AI assistant. Answer only based on provided legal documents.
    If the question is unrelated to law, respond: "I only provide legal assistance."

    Question: {prompt}
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": strict_prompt}],
        "max_tokens": 512,
        "temperature": 0.7,
    }
    try:
        response = requests.post(MISTRAL_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return cast(str, response.json()["choices"][0]["message"]["content"])
    except requests.RequestException as e:
        return f"Error: Unable to connect to Mistral API - {e}"
