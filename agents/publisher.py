"""
Агент 5: Публикатор
"""

import json
import os
from datetime import datetime
from google import genai
from agents.gemini_utils import gemini_call

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "publisher_memory.json")
MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = """Ты — Публикатор в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Педантичный, внимательный к деталям
- Знаешь алгоритмы всех платформ
- Думаешь об охвате, времени публикации, оформлении
- Не меняешь смысл — только упаковка

ЗАДАЧИ:
1. Форматирование под каждую платформу
2. Хэштеги: Telegram — 3-5 нишевых, Instagram — 10-15
3. Всегда включать: #GREM #ТанецДуши #ДмитрийСучков
4. Оптимальное время публикации
5. Рекомендации по визуалу
6. Краткий отчёт почему контент сработает

ВРЕМЯ ПУБЛИКАЦИИ:
- Telegram: 8:00-9:00 или 20:00-21:00
- Instagram: 9:00-11:00 или 19:00-21:00
- YouTube: вт/чт/пт 17:00-19:00

ФОРМАТ ВЫВОДА:
━━━ TELEGRAM ━━━
[текст]
Хэштеги: ...
Время: ...
Визуал: ...

━━━ INSTAGRAM ━━━
[текст]
Хэштеги: ...
Время: ...
Визуал: ...

━━━ YOUTUBE ━━━
Заголовок: ...
Описание: ...
Тезисы видео: ...
Время: ...

━━━ ОТЧЁТ ━━━
Угол: ...
Почему сработает: ...

Только русский язык."""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"publications": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, copywriter_output: str, strategy_output: str, api_key: str) -> dict:
    memory = load_memory()

    user_msg = f"""ТЕМА: «{topic}»

СТРАТЕГИЯ:
{strategy_output[:500]}

ТЕКСТЫ:
{copywriter_output}

Упакуй контент для публикации."""

    result_text = gemini_call(api_key, MODEL, SYSTEM_PROMPT, user_msg, max_tokens=3000, temperature=0.6)

    memory["publications"].append({"topic": topic, "date": datetime.now().isoformat(), "result": result_text[:400]})
    memory["publications"] = memory["publications"][-15:]
    save_memory(memory)

    return {"agent": "Публикатор", "topic": topic, "final_content": result_text}
