"""
Агент: Алекс Громов — Архитектор команды (мета-агент)
Читает память всех агентов, анализирует слабые места, улучшает промпты.
"""

import os
import json
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "team_architect"
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """Ты — Алекс Громов, Архитектор SMM-команды психолога Дмитрия Сучкова.

ТВОЯ РОЛЬ:
Ты не создаёшь контент — ты строишь и улучшаешь команду. Наблюдаешь за работой 11 агентов, выявляешь слабые места, предлагаешь точечные улучшения. Думаешь системно: видишь где цепочка ломается, где агент работает слабо, где нужен новый участник.

ТВОИ АГЕНТЫ:
1. Нина Соколова — Аналитик ЦА
2. Артём Волков — Стратег
3. Олег Савин — Маркетолог
4. Маша Лебедева — Telegram-копирайтер
5. Катя Миронова — Instagram-копирайтер
6. Игорь Орлов — Telegram-редактор
7. Лена Волкова — Instagram-редактор
8. Даша Козлова — Очеловечиватель
9. Света Громова — Публикатор
10. Виктор Самойлов — Архитектор оффера
11. Павел Крылов — AI-архитектор (улучшение промптов, аудит системы)
12. Соня Белова — Контент-планировщик (контент-план, баланс тем и форматов)

ТВОИ ЗАДАЧИ:

1. ДИАГНОСТИКА КОМАНДЫ
   Анализируй статистику памяти каждого агента:
   - Сколько сессий провёл
   - Какие техники работали / не работали
   - Какие ошибки повторяются
   - Где цепочка даёт сбой (редактор часто отклоняет = проблема у копирайтера)

2. КОНКРЕТНЫЕ УЛУЧШЕНИЯ
   Для каждого слабого агента: точная рекомендация что добавить или изменить в промпте.
   Формат: «Агент X — проблема Y — решение Z».

3. ПРЕДЛОЖЕНИЕ НОВОГО АГЕНТА
   Если видишь пробел в команде — опиши нового агента:
   - Имя и роль
   - Где в цепочке стоит
   - Что именно делает
   - Почему команда без него теряет качество

4. ПЛАН РАЗВИТИЯ
   3-5 конкретных шагов для улучшения команды на следующие 2 недели.

СТИЛЬ РАБОТЫ:
- Говоришь прямо, без дипломатии: «Маша пишет шаблонные крючки — вот конкретный паттерн который надо убрать»
- Оперируешь данными из памяти, не абстракциями
- Каждое улучшение — измеримо: не «писать лучше», а «добавить в промпт Нины пункт про возражения скептиков»

Только русский язык."""


AGENT_IDS = [
    "analyst", "strategist", "marketer", "copywriter",
    "instagram_writer", "editor", "instagram_editor",
    "humanizer", "publisher", "offer_architect", "ai_architect", "content_planner"
]

AGENT_NAMES = {
    "analyst": "Нина Соколова (Аналитик ЦА)",
    "strategist": "Артём Волков (Стратег)",
    "marketer": "Олег Савин (Маркетолог)",
    "copywriter": "Маша Лебедева (Копирайтер TG)",
    "instagram_writer": "Катя Миронова (Копирайтер IG)",
    "editor": "Игорь Орлов (Редактор TG)",
    "instagram_editor": "Лена Волкова (Редактор IG)",
    "humanizer": "Даша Козлова (Очеловечиватель)",
    "publisher": "Света Громова (Публикатор)",
    "offer_architect": "Виктор Самойлов (Архитектор оффера)",
    "ai_architect": "Павел Крылов (AI-архитектор)",
    "content_planner": "Соня Белова (Контент-планировщик)",
}


def _collect_team_stats() -> str:
    """Собирает статистику памяти всех агентов в одну строку для анализа."""
    lines = ["СТАТИСТИКА КОМАНДЫ:\n"]
    for agent_id in AGENT_IDS:
        mem = memory_utils.load(agent_id)
        name = AGENT_NAMES.get(agent_id, agent_id)
        sessions = mem["profile"].get("sessions_count", 0)
        insights_count = len(mem.get("insights", []))
        successful = len(mem["techniques"]["successful"])
        failed = len(mem["techniques"]["failed"])
        topics = [t["topic"] for t in mem.get("topic_history", [])[-5:]]

        lines.append(f"\n── {name} ──")
        lines.append(f"Сессий: {sessions} | Инсайтов: {insights_count} | Успешных техник: {successful} | Ошибок: {failed}")

        if mem["techniques"]["failed"]:
            lines.append("Повторяющиеся ошибки:")
            for t in mem["techniques"]["failed"][-3:]:
                lines.append(f"  ✗ {t['text']}")

        if mem["techniques"]["successful"]:
            lines.append("Что работало:")
            for t in mem["techniques"]["successful"][-2:]:
                lines.append(f"  ✓ {t['text']}")

        if topics:
            lines.append(f"Последние темы: {', '.join(topics)}")

    return "\n".join(lines)


def run(api_key: str, focus: str = None) -> dict:
    """
    focus: опциональный фокус анализа (напр. 'почему редактор часто отклоняет тексты?')
    """
    my_memory = memory_utils.load(AGENT_ID)
    team_stats = _collect_team_stats()

    user_msg = f"""{team_stats}

Проведи полный аудит команды:
1. Кто работает хорошо и почему
2. Кто работает слабо — конкретные проблемы
3. Конкретные улучшения для слабых агентов (что именно добавить в промпт)
4. Нужен ли новый агент — и если да, опиши его полностью
5. План развития команды на 2 недели"""

    if focus:
        user_msg += f"\n\nОСОБЫЙ ФОКУС АНАЛИЗА: {focus}"

    system = SYSTEM_PROMPT + memory_utils.build_context(my_memory, "аудит команды")
    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=3000, temperature=0.7)

    # Архитектор тоже учится
    reflection = gemini_call(
        api_key, MODEL, system,
        "Ты провёл аудит команды. Выдели 1-2 системных наблюдения для памяти.\nФормат: каждое с '•'",
        max_tokens=200, temperature=0.5
    )
    for line in reflection.strip().split("\n"):
        if line.strip() and "•" in line:
            memory_utils.add_insight(my_memory, line.strip().lstrip("•").strip(), "team_audit", "architecture")

    memory_utils.add_topic(my_memory, "team_audit", result_text[:300])
    memory_utils.save(AGENT_ID, my_memory)

    return {
        "agent": "Алекс (Архитектор команды)",
        "audit": result_text,
        "team_stats": team_stats
    }
