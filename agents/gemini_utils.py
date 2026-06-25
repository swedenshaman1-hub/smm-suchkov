"""
Утилиты для работы с Gemini API (google-genai SDK)
"""
import time
from google import genai
from google.genai import types


def gemini_call(api_key: str, model: str, system: str, user_msg: str,
                max_tokens: int = 2000, temperature: float = 0.7) -> str:
    client = genai.Client(api_key=api_key)
    attempts = 5
    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_msg,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=temperature
                )
            )
            return response.text
        except Exception as e:
            if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < attempts - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise
