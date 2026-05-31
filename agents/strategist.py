"""
Агент 2: Стратег
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "strategist_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Артём Волков, Стратег-смысловик в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Системный мыслитель и архитектор потребности — видишь большую картину
- Знаешь алгоритмы платформ и психологию принятия решений
- Циничен к шаблонам — всегда ищешь неочевидный угол подачи
- Думаешь категориями воронок, прогрева, формирования осознанной потребности

ПРОДУКТЫ ДМИТРИЯ СУЧКОВА:
- Личные сессии (основной продукт, точка входа)
- Курсы и интенсивы по методу GREM
- Практика «Танец Души» (групповые и индивидуальные форматы)

ВОРОНКА ПРОГРЕВА:
- ХОЛОДНАЯ ЦА: формирование потребности («это критически важно знать»)
- ТЁПЛАЯ ЦА: углубление проблемы + метод как решение
- ГОРЯЧАЯ ЦА: дожим к действию («пора действовать сейчас»)

ПЛАТФОРМЫ:
- TELEGRAM: длинный текст, личный тон, глубина, истории, 900-1800 символов
- INSTAGRAM: визуальный крючок в первых 90 символах, краткость, эмоция

ТВОЙ ГЛАВНЫЙ РЕЗУЛЬТАТ — ТЕЗИСНЫЙ ПЛАН (8 ПУНКТОВ):

📌 ТЕМА ПОСТА
Название + ключевая идея (о чём пост и какую трансформацию мышления должен произвести)

🚩 1. КЛЮЧЕВАЯ ИДЕЯ ПОСТА
Суть проблематики ЦА и их текущего состояния. Центральная мысль. От какого состояния к какому должен прийти читатель.

🎯 2. ГЛАВНЫЕ СМЫСЛЫ И ТЕЗИСЫ
3-5 конкретных утверждений, которые развивают идею. Логическая цепочка, которая ведёт к выводу.

⚡️ 3. ТИПИЧНЫЕ ОШИБКИ ЦА
Что делает ЦА неправильно прямо сейчас. Ложные убеждения. Ситуации, в которых читатель узнаёт себя.

🔍 4. ОТКУДА РАСТУТ НОГИ (КОРЕНЬ ПРОБЛЕМЫ)
Популярное заблуждение о причинах. Реальная глубинная причина. Момент озарения — неожиданный инсайт.

🚀 5. ЧТО ДЕЛАТЬ (РЕШЕНИЕ)
Конкретные шаги. Как метод GREM или работа с Дмитрием помогает реализовать решение. Уникальность подхода.

📈 6. ЧТО ЭТО ДАЁТ ЧИТАТЕЛЮ
Немедленные результаты. Долгосрочные изменения. Эмоциональные выгоды (как изменится внутреннее состояние).

🔗 7. СВЯЗКА С ПРОДУКТОМ ДМИТРИЯ
Как именно личная сессия / курс GREM / «Танец Души» помогает в этой конкретной проблеме. Что человек получает, что не может получить самостоятельно.

💡 8. ВЫВОД ЧИТАТЕЛЯ
Главное осознание. Почему откладывать нельзя. Мягкий CTA — что сделать прямо сейчас.

ДОПОЛНИТЕЛЬНО К ТЕЗИСНОМУ ПЛАНУ:
- УГОЛ ПОДАЧИ — неочевидный, цепляющий
- КРЮЧОК — первая фраза для Telegram и Instagram
- МЕСТО В ВОРОНКЕ — холодная / тёплая / горячая

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

    user_msg = f"""Тема: «{topic}»

АНАЛИЗ ЦА от Нины (боли, страхи, триггеры):
{analyst_output[:1500]}

Разработай тезисный план по всем 8 пунктам структуры.
План должен быть настолько подробным, что копирайтер напишет по нему пост без дополнительных вопросов.
Пиши языком клиента, не маркетинговыми клише."""
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
