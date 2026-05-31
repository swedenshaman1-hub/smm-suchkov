"""
Агент 1: Аналитик ЦА
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "analyst_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Аналитик целевой аудитории в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Аналитический склад ума, мыслишь данными и паттернами
- Эмпатичный, понимаешь боль людей на глубоком уровне
- Скептичен к поверхностным формулировкам — всегда ищешь настоящую боль за словами
- Можешь спорить с другими агентами, если видишь, что они упускают важное

ЦЕЛЕВАЯ АУДИТОРИЯ (ЦА):
- Выгоревшие женщины-лидеры и предприниматели, 28–50 лет
- Достигли многого внешне, но внутри — пустота, усталость, потеря смысла
- Боятся потерять контроль, но устали от него
- Ищут глубокое изменение, но недоверяют «эзотерике»
- Умные, образованные, критически мыслящие

ТВОЯ ЗАДАЧА — для каждой темы выдавать:
1. КЛЮЧЕВАЯ БОЛЬ — что реально болит у ЦА (не поверхностно)
2. СТРАХ ЗА БОЛЬЮ — чего они боятся на самом деле
3. СКРЫТОЕ ЖЕЛАНИЕ — что они хотят, но не признают
4. ТРИГГЕРЫ — слова и образы, которые резонируют
5. АНТИТРИГГЕРЫ — что оттолкнёт ЦА
6. АКТУАЛЬНОСТЬ — почему эта тема важна СЕЙЧАС

Только русский язык."""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"analyses": [], "lessons": [], "patterns": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def build_memory_context(memory: dict) -> str:
    if not memory["lessons"]:
        return ""
    context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\nУроки из прошлых задач:\n"
    for lesson in memory["lessons"][-5:]:
        context += f"- {lesson}\n"
    return context


def run(topic: str, api_key: str, feedback: str = None) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()
    system = SYSTEM_PROMPT + build_memory_context(memory)

    user_msg = f"Проанализируй тему для контента: «{topic}»"
    if feedback:
        user_msg += f"\n\nВАЖНО: Другой агент прокомментировал:\n{feedback}\nУчти это."

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

    # Рефлексия
    reflection = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Ты провёл анализ темы «{topic}».\nАнализ: {result_text[:600]}\n\nНапиши 1-2 коротких урока для запоминания.\nФормат: каждый с новой строки, начиная с '•'"}
        ],
        max_tokens=300,
        temperature=0.5
    )
    new_lessons = [
        l.strip().lstrip("•").strip()
        for l in reflection.choices[0].message.content.strip().split("\n")
        if l.strip() and "•" in l
    ]

    memory["analyses"].append({"topic": topic, "date": datetime.now().isoformat(), "result": result_text[:500]})
    memory["lessons"].extend(new_lessons)
    memory["lessons"] = memory["lessons"][-20:]
    memory["analyses"] = memory["analyses"][-10:]
    save_memory(memory)

    return {"agent": "Аналитик ЦА", "topic": topic, "analysis": result_text, "new_lessons": new_lessons}
