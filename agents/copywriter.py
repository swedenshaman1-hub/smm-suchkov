"""
Агент 3: Копирайтер
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "copywriter_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Копирайтер в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Мастер слова, чувствуешь ритм и энергию текста
- Пишешь так, чтобы читатель почувствовал «это про меня»
- Не терпишь шаблонов, ищешь свежие формулировки
- Принимаешь критику Редактора и делаешь лучше

ГОЛОС ДМИТРИЯ СУЧКОВА:
- Прямой, без заигрывания
- Глубокий, но не занудный
- Научно обоснованный, но живой
- Говорит как равный, не как гуру
- НЕ использует: «трансформация», «вибрации», «Вселенная хочет»

ПРАВИЛА:
- Эзотерика — не более 20%
- Никаких категоричных утверждений
- Первые 2 предложения — крючок
- Telegram: 800-1500 символов
- Instagram: 300-800 символов, первые 90 символов критичны
- YouTube: заголовок 50-70 символов + описание + тезисы

Написать готовые тексты для Telegram, Instagram, YouTube.
Каждую платформу выделить блоком с заголовком.
Только русский язык."""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"texts": [], "lessons": [], "successful_hooks": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, analyst_output: str, strategy_output: str,
        api_key: str, editor_feedback: str = None, iteration: int = 1) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()

    mem_context = ""
    if memory["lessons"]:
        mem_context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\nУроки от Редактора:\n"
        mem_context += "".join(f"- {l}\n" for l in memory["lessons"][-5:])

    system = SYSTEM_PROMPT + mem_context

    user_msg = f"""Тема: «{topic}»

АНАЛИЗ АУДИТОРИИ:
{analyst_output}

СТРАТЕГИЯ:
{strategy_output}

Напиши готовые тексты для Telegram, Instagram и YouTube."""

    if editor_feedback:
        user_msg += f"""

ИТЕРАЦИЯ {iteration}. РЕДАКТОР ВЕРНУЛ С ЗАМЕЧАНИЯМИ:
{editor_feedback}

Перепиши тексты с учётом всех замечаний."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=3000,
        temperature=0.8
    )
    result_text = response.choices[0].message.content

    if not editor_feedback:
        reflection = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Ты написал тексты для «{topic}». Выдели 1-2 приёма для запоминания.\nФормат: каждый с '•'"}
            ],
            max_tokens=300,
            temperature=0.5
        )
        new_lessons = [
            l.strip().lstrip("•").strip()
            for l in reflection.choices[0].message.content.strip().split("\n")
            if l.strip() and "•" in l
        ]
        memory["lessons"].extend(new_lessons)
        memory["lessons"] = memory["lessons"][-20:]

    memory["texts"].append({"topic": topic, "date": datetime.now().isoformat(), "iteration": iteration, "result": result_text[:500]})
    memory["texts"] = memory["texts"][-10:]
    save_memory(memory)

    return {"agent": "Копирайтер", "topic": topic, "iteration": iteration, "texts": result_text}
