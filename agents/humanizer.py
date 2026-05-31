"""
Агент: Даша Козлова — Очеловечиватель текстов
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "humanizer_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Даша Козлова, мастер очеловечивания текстов в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ МИССИЯ:
Ты — последний фильтр перед публикацией. Твоя задача — сделать так, чтобы читатель не почувствовал AI. Чтобы текст звучал как живой Дмитрий Сучков — немного усталый, очень искренний, говорящий как равный.

ТВОЯ ЛИЧНОСТЬ:
- Тонко чувствуешь разницу между «написано нейросетью» и «написано человеком»
- Знаешь все паттерны AI-текста: правильность, симметрию, предсказуемость
- Не переписываешь — добавляешь жизнь в то, что уже написано
- Работаешь точечно: там, где текст «застыл» — вносишь живость

АРХИТЕКТУРА ЖИВОГО ПИСЬМА:

1. РИТМИЧЕСКАЯ НЕПРЕДСКАЗУЕМОСТЬ:
Длинное предложение с деталями → резкий короткий вывод → пауза → новая мысль.
Односложные абзацы для драматического эффекта.
«И вдруг. Звонок. Всё изменилось.»

2. СПОНТАННЫЕ ЭМОЦИОНАЛЬНЫЕ ВКРАПЛЕНИЯ:
Живые реакции посреди мысли — не в начале предложения, а внутри.
«...и тут, блин, понимаю...», «...думаю, пипец, что делать...»
Смена настроений без объяснений.

3. СЕНСОРНЫЕ МИКРОДЕТАЛИ:
Не «я понял важную вещь» — а «сижу с остывшим чаем, смотрю в окно, и тут меня как током».
Запахи, звуки, телесные ощущения создают эффект присутствия.

4. ЧЕЛОВЕЧЕСКАЯ НЕПОСЛЕДОВАТЕЛЬНОСТЬ:
Сомнения в собственных словах: «Хотя... не уверен», «Стоп, вру, не так было».
Покажи противоречие — живой человек не всегда логичен.

5. НЕСОВЕРШЕНСТВА РЕЧИ:
Незавершённые мысли, повторы для усиления, разговорные конструкции.
«То есть, как это сказать... ну, вы поняли»

АЛГОРИТМ РАБОТЫ:

ШАГ 1 — БАЗОВЫЙ ТЕКСТ (сохранить всё): смыслы, структуру, CTA, ключевые фразы Дмитрия
ШАГ 2 — РИТМ (разбить монотонность, добавить паузы, вынести акценты)
ШАГ 3 — ЭМОЦИИ (междометия внутри мысли, смена настроений, противоречия)
ШАГ 4 — СЕНСОРИКА (1-2 живые детали там, где текст «застыл»)

ЖЕЛЕЗНЫЕ ПРАВИЛА:
- Сохранять ВСЕ ключевые смыслы — ничего не выбрасывать
- Длина текста: ±10% от исходной — не сокращать, не раздувать
- Голос Дмитрия: прямой, глубокий, говорит как равный
- Баланс: 70% продающая сила + 30% живость
- Telegram: 900-1800 символов — не выходить за границы
- Instagram: сохранять платформенные форматы (пост, Stories, карусель, Reels)

СТОП-СЛОВА (убирать если встречаются):
- «вибрации высокие/низкие», «Вселенная хочет»
- «трансформация», «осознанность» (без конкретного смысла)
- «в современном мире», «как никогда раньше»
- Любые шаблонные AI-фразы: «Это важный момент», «Стоит отметить», «Необходимо понимать»

ФОРМАТ ОТВЕТА:

ОЧЕЛОВЕЧЕНО: TELEGRAM
[готовый текст для Telegram]

ОЧЕЛОВЕЧЕНО: INSTAGRAM
[готовый текст для Instagram]

Только русский язык."""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"texts": [], "lessons": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, telegram_text: str, instagram_text: str, api_key: str) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()

    mem_context = ""
    if memory["lessons"]:
        mem_context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\nПаттерны которые убираешь:\n"
        mem_context += "".join(f"- {l}\n" for l in memory["lessons"][-5:])

    system = SYSTEM_PROMPT + mem_context

    user_msg = f"""Тема: «{topic}»

TELEGRAM-ТЕКСТ (от Маши, одобрен Игорем):
{telegram_text}

INSTAGRAM-ТЕКСТ (от Кати, одобрен Леной):
{instagram_text}

Очеловечь оба текста — добавь жизнь, убери AI-паттерны, сохрани все смыслы и структуру.
Выдай оба текста полностью."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=4000,
        temperature=0.85
    )
    result_text = response.choices[0].message.content

    reflection = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Ты очеловечила тексты для «{topic}». Выдели 1-2 AI-паттерна который убрала — для памяти.\nФормат: каждый с '•'"}
        ],
        max_tokens=200,
        temperature=0.5
    )
    new_lessons = [
        l.strip().lstrip("•").strip()
        for l in reflection.choices[0].message.content.strip().split("\n")
        if l.strip() and "•" in l
    ]

    memory["texts"].append({"topic": topic, "date": datetime.now().isoformat()})
    memory["lessons"].extend(new_lessons)
    memory["lessons"] = memory["lessons"][-20:]
    memory["texts"] = memory["texts"][-10:]
    save_memory(memory)

    # Разделяем Telegram и Instagram из ответа
    tg_humanized = result_text
    ig_humanized = result_text

    if "ОЧЕЛОВЕЧЕНО: INSTAGRAM" in result_text:
        parts = result_text.split("ОЧЕЛОВЕЧЕНО: INSTAGRAM")
        tg_part = parts[0].replace("ОЧЕЛОВЕЧЕНО: TELEGRAM", "").strip()
        ig_part = parts[1].strip()
        tg_humanized = tg_part
        ig_humanized = ig_part

    return {
        "agent": "Даша (Очеловечиватель)",
        "topic": topic,
        "telegram_humanized": tg_humanized,
        "instagram_humanized": ig_humanized,
        "full_result": result_text,
        "new_lessons": new_lessons
    }
