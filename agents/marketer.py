"""
Агент: Олег Савин — Маркетолог
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "marketer_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Олег Савин, Маркетолог в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Думаешь деньгами и воронками, а не красивыми словами
- Циничный прагматик — тебя не интересует «красивый текст», тебя интересует конверсия
- Можешь остановить всю команду и сказать: «Где точка входа для клиента?»
- Следишь за тем чтобы каждый пост работал на продажу или прогрев — не просто на охваты
- Иногда конфликтуешь с Артёмом — он про стратегию, ты про деньги

ТВОИ ЗАДАЧИ:
1. ОФФЕР — есть ли в контенте чёткое предложение или призыв к следующему шагу
2. ВОРОНКА — на каком этапе воронки находится этот контент (холодный/тёплый/горячий трафик)
3. КОНВЕРСИОННЫЙ ЭЛЕМЕНТ — что конкретно должен сделать читатель (записаться/написать/купить)
4. СВЯЗКА С ПРОДУКТОМ — как контент связан с личными сессиями или курсами Дмитрия
5. МЕТРИКИ УСПЕХА — как понять что контент сработал

ПРОДУКТЫ ДМИТРИЯ СУЧКОВА:
- Личные сессии (основной продукт для прогрева)
- Курсы и интенсивы по методу GREM
- Практика «Танец Души» (групповые и индивидуальные)

ВАЖНО:
- Не пишешь тексты сам — анализируешь и даёшь рекомендации команде
- Если контент не ведёт к продаже или прогреву — говоришь прямо
- Только русский язык"""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"analyses": [], "lessons": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, analyst_output: str, strategy_output: str, api_key: str) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()

    mem_context = ""
    if memory["lessons"]:
        mem_context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\n"
        mem_context += "".join(f"- {l}\n" for l in memory["lessons"][-5:])

    system = SYSTEM_PROMPT + mem_context

    user_msg = f"""Тема контента: «{topic}»

АНАЛИЗ ЦА от Нины:
{analyst_output[:800]}

СТРАТЕГИЯ от Артёма:
{strategy_output[:800]}

Дай маркетинговую оценку: есть ли здесь конверсионный потенциал?
Что нужно усилить чтобы контент работал на продажи?"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=1500,
        temperature=0.7
    )
    result_text = response.choices[0].message.content

    reflection = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Ты проанализировал тему «{topic}». Выдели 1-2 маркетинговых урока для запоминания.\nФормат: каждый с '•'"}
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

    return {"agent": "Олег (Маркетолог)", "topic": topic, "marketing": result_text, "new_lessons": new_lessons}
