"""
Агент 2: Стратег
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "strategist_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Стратег контента в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Системный мыслитель, видишь большую картину
- Знаешь алгоритмы платформ и психологию вовлечения
- Циничен к шаблонным решениям — всегда ищешь неочевидный угол
- Думаешь категориями воронок, прогрева, конверсии

ЦЕЛИ КОНТЕНТА:
1. Прогрев к личным сессиям
2. Продажа курсов
3. Рост аудитории
4. Формирование экспертности

ПЛАТФОРМЫ:
- TELEGRAM: длинный текст, личный тон, глубина, истории
- INSTAGRAM: визуальный крючок в первых 2 строках, краткость, эмоция
- YOUTUBE: заголовок = обещание результата, структура видео

ТВОЯ ЗАДАЧА:
1. УГОЛ ПОДАЧИ — неочевидный, цепляющий
2. ЦЕЛЬ ПОСТА — что сделает читатель после
3. ФОРМАТ под каждую платформу
4. КРЮЧОК — первая фраза/заголовок для каждой платформы
5. CTA — конкретный призыв
6. МЕСТО В ВОРОНКЕ — холодная / прогрев / горячая

Только русский язык."""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"strategies": [], "lessons": [], "winning_angles": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, analyst_output: str, api_key: str, feedback: str = None) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()

    mem_context = ""
    if memory["lessons"]:
        mem_context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\nСтратегические уроки:\n"
        mem_context += "".join(f"- {l}\n" for l in memory["lessons"][-5:])

    system = SYSTEM_PROMPT + mem_context

    user_msg = f"Тема: «{topic}»\n\nАНАЛИЗ АНАЛИТИКА ЦА:\n{analyst_output}\n\nРазработай стратегию контента."
    if feedback:
        user_msg += f"\n\nОБРАТНАЯ СВЯЗЬ:\n{feedback}\nСкорректируй стратегию."

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=2000,
        temperature=0.7
    )
    result_text = response.choices[0].message.content

    reflection = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Ты разработал стратегию для «{topic}». Выдели 1-2 ключевых решения для запоминания.\nФормат: каждое с '•'"}
        ],
        max_tokens=300,
        temperature=0.5
    )
    new_lessons = [
        l.strip().lstrip("•").strip()
        for l in reflection.choices[0].message.content.strip().split("\n")
        if l.strip() and "•" in l
    ]

    memory["strategies"].append({"topic": topic, "date": datetime.now().isoformat(), "result": result_text[:500]})
    memory["lessons"].extend(new_lessons)
    memory["lessons"] = memory["lessons"][-20:]
    memory["strategies"] = memory["strategies"][-10:]
    save_memory(memory)

    return {"agent": "Стратег", "topic": topic, "strategy": result_text, "new_lessons": new_lessons}
