"""
РЈС‚РёР»РёС‚С‹ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ Gemini API (google-genai SDK)
"""
from google import genai
from google.genai import types


def gemini_call(api_key: str, model: str, system: str, user_msg: str,
                max_tokens: int = 2000, temperature: float = 0.7) -> str:
    client = genai.Client(api_key=api_key)
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
