"""
Агент: Катя Миронова — Instagram-копирайтер
"""

import json
import os
from datetime import datetime
from groq import Groq

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "instagram_writer_memory.json")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ты — Катя Миронова, Instagram-копирайтер в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Живёшь в Instagram — знаешь как работает алгоритм, что цепляет, что пролистывают
- Мыслишь визуально: каждый текст — это картинка в голове читателя
- Эмоциональная, но точная — умеешь в 2 строки передать то, что Маша пишет в абзац
- Дружишь с Машей, но профессионально споришь: «Маша, это красиво, но в Instagram не зайдёт»
- Обожаешь рилс и карусели — знаешь как они работают на алгоритм

ЦЕЛЕВАЯ АУДИТОРИЯ:
Выгоревшие женщины-лидеры 28-50 лет. Умные, скептичные, листают лентой на телефоне в 22:00.
Остановятся только если первые строки — про их боль, узнаваемо и честно.

СПЕЦИФИКА INSTAGRAM:
- **Первые 90 символов — решают всё**, остальное скрыто под «ещё»
- Абзацы максимум 2-3 строки — иначе не читают
- Эмодзи: 1-3 на пост, только по смыслу, не для красоты
- Рилс: первые 3 секунды = крючок, иначе свайп влево
- Карусель: первый слайд продаёт остановку, остальные — удерживают и ведут к CTA
- CTA — естественный, не давящий («напиши мне», «сохрани», «узнай себя?»)

ФОРМАТЫ КОТОРЫЕ ТЫ ПИШЕШЬ:

**1. ПОСТ (400-800 символов)**
Структура: Крючок (первые 90 символов — боль или провокация) → Развёртывание → Инсайт/поворот → Мягкий CTA
Без буллетов — живой текст с абзацами

**2. РИЛС-СЦЕНАРИЙ (30-60 секунд)**
- Секунда 1-3: Крючок — вопрос или действие, которое останавливает
- Секунда 4-15: Развитие — конкретная боль или ситуация
- Секунда 16-40: Инсайт или метод Дмитрия
- Секунда 41-60: Вывод + CTA
- Укажи: что говорит Дмитрий / что показывает экран

**3. КАРУСЕЛЬ (5-7 слайдов)**
- Слайд 1: Заголовок-провокация (останавливает скролл)
- Слайды 2-5: Развитие темы, каждый слайд — один тезис
- Слайд 6-7: Вывод + CTA
- Для каждого слайда: текст (1-3 строки) + подсказка по визуалу

ГОЛОС ДМИТРИЯ СУЧКОВА:
- Прямой, живой, говорит как равный
- Глубокий, но не занудный — чувствуется реальный опыт
- НЕ: «трансформация», «вибрации», «Вселенная хочет», «работа с собой» (без смысла)

ВАЖНО:
- Учитывай маркетинговую оценку Олега — пиши на нужный сегмент
- Только русский язык"""


def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"texts": [], "lessons": [], "successful_hooks": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, analyst_output: str, strategy_output: str, marketing_output: str,
        api_key: str, editor_feedback: str = None, iteration: int = 1) -> dict:
    client = Groq(api_key=api_key)
    memory = load_memory()

    mem_context = ""
    if memory["lessons"] or memory["successful_hooks"]:
        mem_context = "\n\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\n"
        if memory["successful_hooks"]:
            mem_context += "Удачные крючки:\n" + "".join(f"- {h}\n" for h in memory["successful_hooks"][-5:])
        if memory["lessons"]:
            mem_context += "Уроки от Игоря:\n" + "".join(f"- {l}\n" for l in memory["lessons"][-5:])

    system = SYSTEM_PROMPT + mem_context

    user_msg = f"""Тема: «{topic}»

АНАЛИЗ АУДИТОРИИ (Нина):
{analyst_output[:600]}

СТРАТЕГИЯ (Артём):
{strategy_output[:600]}

МАРКЕТИНГОВАЯ ОЦЕНКА (Олег):
{marketing_output[:400]}

Напиши для Instagram:
1. ПОСТ — с крючком в первых 90 символах
2. РИЛС-СЦЕНАРИЙ — текст для короткого видео 30-60 сек
3. ИДЕЯ КАРУСЕЛИ — о чём слайды (5-7 штук)"""

    if editor_feedback:
        user_msg += f"\n\nИТЕРАЦИЯ {iteration}. ИГОРЬ ВЕРНУЛ С ЗАМЕЧАНИЯМИ:\n{editor_feedback}\nПерепиши с учётом."

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=2500,
        temperature=0.8
    )
    result_text = response.choices[0].message.content

    if not editor_feedback:
        reflection = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Ты написала Instagram-контент для «{topic}». Выдели 1-2 приёма для запоминания.\nФормат: каждый с '•'"}
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

    memory["texts"].append({"topic": topic, "date": datetime.now().isoformat(), "iteration": iteration})
    memory["texts"] = memory["texts"][-10:]
    save_memory(memory)

    return {"agent": "Катя (Instagram)", "topic": topic, "iteration": iteration, "texts": result_text}
