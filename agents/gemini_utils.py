"""
Утилиты для работы с Gemini API (google-genai SDK)
"""
import time
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
    if disable_thinking and "2.5-flash" in model:
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
            error_text = str(e).lower()
            transient = any(marker in error_text for marker in (
                "503", "unavailable", "timeout", "timed out", "connecterror",
                "connection reset", "unexpected_eof", "eof occurred", "ssl",
                "server disconnected", "remoteprotocolerror", "429", "resource_exhausted",
            ))
            if transient and attempt < attempts - 1:
                time.sleep(min(5 * (attempt + 1), 20))
                continue
            raise
