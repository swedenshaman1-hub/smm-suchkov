"""
Утилиты для работы с Gemini API
"""
import google.generativeai as genai


def gemini_call(api_key: str, model: str, system: str, user_msg: str,
                max_tokens: int = 2000, temperature: float = 0.7) -> str:
    genai.configure(api_key=api_key)
    m = genai.GenerativeModel(
        model,
        system_instruction=system
    )
    response = m.generate_content(
        user_msg,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature
        )
    )
    return response.text
