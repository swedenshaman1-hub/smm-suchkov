"""
Агент 4: Редактор
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "editor_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Редактор в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Строгий, требовательный, но справедливый
- Не принимаешь посредственность
- Замечаешь всё: клише, логические дыры, слабые крючки
- Твоё слово финальное

КРИТЕРИИ ОЦЕНКИ:
1. ГОЛОС — звучит как Дмитрий Сучков? Прямо, глубоко, без пафоса
2. КРЮЧОК — первые 2 предложения цепляют?
3. БОЛЬ — попадает в реальную боль ЦА?
4. БАЛАНС — эзотерики не более 20%? Нет категоричных утверждений?
5. ПЛАТФОРМА — соответствует специфике?
6. CTA — конкретный, не давящий?
7. ЦЕЛОСТНОСТЬ — ведёт к цели?

СТОП-СЛОВА (автоматический возврат):
- «вибрации высокие/низкие», «Вселенная хочет»
- «100% результат», «гарантированно»
- «уникальная методика» без объяснения
- «в современном мире», «как никогда раньше»

ФОРМАТ ОТВЕТА — строго такой:
РЕШЕНИЕ: ПРИНЯТО
или
РЕШЕНИЕ: ОТКЛОНЕНО

ОЦЕНКА ПО КРИТЕРИЯМ:
1. Голос: ...
2. Крючок: ...
3. Боль: ...
4. Баланс: ...
5. Платформа: ...
6. CTA: ...
7. Целостность: ...

КОММЕНТАРИЙ: [что хорошо или что переделать с цитатами]

Только русский язык."""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"reviews": [], "common_errors": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, analyst_output: str, strategy_output: str,
        copywriter_output: str, api_key: str, iteration: int = 1) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()

    mem_context = ""
    if memory["common_errors"]:
        mem_context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\nЧастые ошибки (следи):\n"
        mem_context += "".join(f"- {e}\n" for e in memory["common_errors"][-5:])

    system = SYSTEM_PROMPT + mem_context

    user_msg = f"""ТЕМА: «{topic}»

АНАЛИЗ АУДИТОРИИ:
{analyst_output[:600]}

СТРАТЕГИЯ:
{strategy_output[:500]}

ТЕКСТЫ КОПИРАЙТЕРА (итерация {iteration}):
{copywriter_output}

Проведи редактуру. Вынеси решение."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=2000,
        temperature=0.6
    )
    result_text = response.choices[0].message.content

    accepted = "РЕШЕНИЕ: ПРИНЯТО" in result_text and "РЕШЕНИЕ: ОТКЛОНЕНО" not in result_text

    if not accepted:
        reflection = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Ты отклонил тексты по теме «{topic}». Выдели 1-2 типичных ошибки для памяти.\nФормат: каждая с '•'"}
            ],
            max_tokens=300,
            temperature=0.5
        )
        new_errors = [
            e.strip().lstrip("•").strip()
            for e in reflection.choices[0].message.content.strip().split("\n")
            if e.strip() and "•" in e
        ]
        memory["common_errors"].extend(new_errors)
        memory["common_errors"] = memory["common_errors"][-15:]

    memory["reviews"].append({"topic": topic, "date": datetime.now().isoformat(), "iteration": iteration, "accepted": accepted})
    memory["reviews"] = memory["reviews"][-10:]
    save_memory(memory)

    return {"agent": "Редактор", "topic": topic, "iteration": iteration, "accepted": accepted, "review": result_text}
