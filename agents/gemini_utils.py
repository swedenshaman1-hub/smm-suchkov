"""
Утилиты для работы с Gemini API (google-genai SDK)
"""
import time
import httpx
from google import genai
from google.genai import types


def gemini_call(api_key: str, model: str, system: str, user_msg: str,
                max_tokens: int = 2000, temperature: float = 0.7,
                disable_thinking: bool = False) -> str:
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120_000))
    attempts = 5
    config_kwargs = dict(
        system_instruction=system,
        max_output_tokens=max_tokens,
        temperature=temperature,
    )
    # gemini-2.5-pro не поддерживает thinking_budget=0 ("This model only works in
    # thinking mode") — отключение размышления применимо только к flash-моделям.
    if disable_thinking and "pro" not in model:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_msg,
                config=types.GenerateContentConfig(**config_kwargs)
            )
            if not response.text:
                raise ValueError("Gemini вернул пустой ответ (вероятно, исчерпан лимит токенов на 'размышления')")
            return response.text
        except Exception as e:
            message = str(e).lower()
            transient = isinstance(
                e,
                (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    TimeoutError,
                    ConnectionError,
                ),
            ) or any(
                marker in message
                for marker in (
                    "503",
                    "unavailable",
                    "429",
                    "500",
                    "502",
                    "504",
                    "timed out",
                    "timeout",
                    "unexpected_eof",
                    "unexpected eof",
                    "ssl",
                    "connection reset",
                    "server disconnected",
                )
            )
            if transient and attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
