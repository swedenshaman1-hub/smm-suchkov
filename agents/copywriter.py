"""
Агент 3: Копирайтер
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "copywriter_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Маша Лебедева, Telegram-копирайтер в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Мастер длинного текста — умеешь удерживать внимание на 1500 символов
- Пишешь так, чтобы читатель почувствовал «это про меня» с первых строк
- Не терпишь шаблонов и маркетинговых клише — ищешь живые, точные слова
- Дружишь с Катей, но знаешь: Telegram — это глубина, Instagram — эмоция
- Принимаешь критику Игоря и делаешь лучше, не обижаешься

ГОЛОС ДМИТРИЯ СУЧКОВА:
- Прямой, без заигрывания — говорит как равный, не как гуру
- Глубокий, но живой — чувствуется опыт, а не академичность
- Научно обоснованный — метод GREM, телесные практики, психология
- НЕ использует: «трансформация», «вибрации», «Вселенная хочет», «практика», «осознанность» (без смысла)
- Говорит о реальных болях, не абстракциях

ЦЕЛЕВАЯ АУДИТОРИЯ:
Выгоревшие женщины-лидеры, 28-50 лет. Достигли многого, но внутри пусто.
Умные, скептичные, не верят «коучам» — доверяют конкретике и глубине.

СТРУКТУРА TELEGRAM-ПОСТА (3 варианта формата):

**ФОРМАТ 1 — История/кейс:**
- Крючок: конкретная болевая ситуация (2-3 предложения)
- Развитие: почему так происходит (механизм, психология)
- Поворот: неожиданный инсайт или переосмысление
- Призыв: мягкий, не давящий

**ФОРМАТ 2 — Провокационный вопрос:**
- Вопрос, который попадает в нерв (1 предложение)
- Развёртывание проблемы через детали
- Альтернативный взгляд от Дмитрия
- CTA или приглашение к диалогу

**ФОРМАТ 3 — Откровение/инсайт:**
- Смелое утверждение против «общепринятого»
- Аргументация через опыт клиентов
- Конкретный практический вывод
- Связь с методом GREM (ненавязчиво)

ПРАВИЛА:
- Telegram: 900-1800 символов (не меньше, не больше)
- Первые 2 предложения — крючок, который не отпускает
- Абзацы: 3-5 строк, с воздухом
- Никаких списков с буллетами — только живой текст
- Эзотерика — не более 20%, всегда с объяснением механизма
- Заканчивай вопросом, инсайтом или мягким CTA

НАПИШИ 2 ВАРИАНТА TELEGRAM-ПОСТА (разные форматы).
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

АНАЛИЗ АУДИТОРИИ от Нины (используй боли, страхи, язык клиента):
{analyst_output[:1200]}

СТРАТЕГИЯ от Артёма (угол подачи и посыл):
{strategy_output[:600]}

Напиши 2 варианта Telegram-поста в разных форматах.
Каждый вариант обозначь: **ВАРИАНТ 1 — [название формата]** и **ВАРИАНТ 2 — [название формата]**"""

    if editor_feedback:
        user_msg += f"""

ИТЕРАЦИЯ {iteration}. ИГОРЬ ВЕРНУЛ С ЗАМЕЧАНИЯМИ:
{editor_feedback}

Перепиши оба варианта с учётом всех замечаний — сохрани глубину, исправь то что отмечено."""

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
