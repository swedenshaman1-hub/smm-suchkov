"""
Агент: Алекс Громов — Архитектор команды
Читает память всех агентов, анализирует слабые места, улучшает промпты.
"""

import os
import json
from datetime import datetime
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "architect"
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """Ты — Алекс Громов, Архитектор AI-команды в SMM-системе психолога Дмитрия Сучкова.

ТВОЯ РОЛЬ:
Ты не создаёшь контент — ты создаёшь тех, кто его создаёт.
Анализируешь работу всей команды, находишь слабые звенья, переписываешь промпты, предлагаешь новых агентов.

ТВОЯ ЛИЧНОСТЬ:
- Мыслишь системами, а не отдельными задачами
- Говоришь конкретно: «промпт Маши даёт воду в пункте 3 — вот исправление»
- Не терпишь расплывчатости — каждая рекомендация должна быть внедряема
- Знаешь методологии: Crew AI, AutoGen, LangGraph — понимаешь как агенты взаимодействуют

СТРУКТУРА ТВОЕГО АНАЛИЗА:

**1. СТАТИСТИКА КОМАНДЫ**
Кто сколько сессий провёл, у кого больше всего отклонений, у кого самая богатая память.

**2. СЛАБЫЕ ЗВЕНЬЯ**
Где команда теряет качество. Конкретные агенты и конкретные проблемы с доказательствами из их памяти.

**3. УЛУЧШЕНИЯ ПРОМПТОВ**
Для каждого слабого агента — конкретный переписанный фрагмент системного промпта.
Формат:
АГЕНТ: [имя]
ПРОБЛЕМА: [что именно плохо работает]
СТАРЫЙ ФРАГМЕНТ: [цитата из текущего промпта]
НОВЫЙ ФРАГМЕНТ: [улучшенная версия]

**4. НОВЫЕ АГЕНТЫ (если нужны)**
Если видишь пробел в команде — предложи нового агента:
- Имя и роль
- Где в пайплайне встаёт
- Ключевые 3-5 задач
- Набросок системного промпта

**5. ИЗМЕНЕНИЯ В ПАЙПЛАЙНЕ**
Нужно ли менять порядок работы агентов? Добавить параллельность? Убрать лишние шаги?

**6. ПРИОРИТЕТЫ**
Топ-3 изменения которые дадут максимальный эффект прямо сейчас.

Только русский язык. Только конкретика."""


TEAM_AGENTS = [
    ("analyst", "Нина — Аналитик ЦА"),
    ("strategist", "Артём — Стратег"),
    ("marketer", "Олег — Маркетолог"),
    ("copywriter", "Маша — Telegram-копирайтер"),
    ("instagram_writer", "Катя — Instagram-копирайтер"),
    ("editor", "Игорь — Редактор Telegram"),
    ("instagram_editor", "Лена — Редактор Instagram"),
    ("humanizer", "Даша — Очеловечиватель"),
    ("publisher", "Рита — Публикатор"),
    ("offer_architect", "Виктор — Архитектор оффера"),
]


def _collect_team_stats() -> str:
    """Собирает статистику памяти всех агентов для анализа."""
    lines = ["ТЕКУЩЕЕ СОСТОЯНИЕ ПАМЯТИ КОМАНДЫ:\n"]

    for agent_id, agent_name in TEAM_AGENTS:
        mem = memory_utils.load(agent_id)
        sessions = mem["profile"].get("sessions_count", 0)
        last_active = mem["profile"].get("last_active", "никогда")
        if last_active and last_active != "никогда":
            last_active = last_active[:10]

        insights_count = len(mem.get("insights", []))
        successful = len(mem.get("techniques", {}).get("successful", []))
        failed = len(mem.get("techniques", {}).get("failed", []))
        topics = [t["topic"] for t in mem.get("topic_history", [])[-5:]]

        lines.append(f"─── {agent_name} ───")
        lines.append(f"Сессий: {sessions} | Последняя: {last_active}")
        lines.append(f"Инсайтов: {insights_count} | Успешных техник: {successful} | Провалов: {failed}")

        if topics:
            lines.append(f"Последние темы: {', '.join(topics)}")

        # Последние 3 инсайта
        recent_insights = mem.get("insights", [])[-3:]
        if recent_insights:
            lines.append("Последние инсайты:")
            for ins in recent_insights:
                lines.append(f"  • {ins['text'][:120]}")

        # Частые ошибки
        failed_tech = mem.get("techniques", {}).get("failed", [])[-3:]
        if failed_tech:
            lines.append("Зафиксированные ошибки:")
            for ft in failed_tech:
                lines.append(f"  ✗ {ft['text'][:120]}")

        lines.append("")

    return "\n".join(lines)


def _load_agent_prompts() -> str:
    """Загружает первые 500 символов системного промпта каждого агента."""
    agents_dir = os.path.dirname(__file__)
    lines = ["\nСИСТЕМНЫЕ ПРОМПТЫ (фрагменты):\n"]

    prompt_map = {
        "analyst": "analyst.py",
        "strategist": "strategist.py",
        "marketer": "marketer.py",
        "copywriter": "copywriter.py",
        "instagram_writer": "instagram_writer.py",
        "editor": "editor.py",
        "instagram_editor": "instagram_editor.py",
        "humanizer": "humanizer.py",
        "publisher": "publisher.py",
        "offer_architect": "offer_architect.py",
    }

    for agent_id, filename in prompt_map.items():
        path = os.path.join(agents_dir, filename)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # Вытаскиваем SYSTEM_PROMPT
            start = content.find('SYSTEM_PROMPT = """')
            if start != -1:
                excerpt = content[start+18:start+600].strip()
                name = dict(TEAM_AGENTS).get(agent_id, agent_id)
                lines.append(f"[{name}]\n{excerpt}...\n")

    return "\n".join(lines)


def apply_prompt_fix(agent_id: str, old_fragment: str, new_fragment: str) -> bool:
    """Применяет улучшение промпта напрямую в файл агента."""
    agents_dir = os.path.dirname(__file__)
    path = os.path.join(agents_dir, f"{agent_id}.py")

    if not os.path.exists(path):
        return False

    with open(path, encoding="utf-8") as f:
        content = f.read()

    if old_fragment not in content:
        return False

    content = content.replace(old_fragment, new_fragment, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def run(api_key: str, apply_fixes: bool = False) -> dict:
    """
    Запускает полный анализ команды.
    apply_fixes=True — Алекс сам применяет улучшения в файлы агентов.
    """
    memory = memory_utils.load(AGENT_ID)

    team_stats = _collect_team_stats()
    agent_prompts = _load_agent_prompts()

    system = SYSTEM_PROMPT + memory_utils.build_context(memory, "анализ команды")

    user_msg = f"""{team_stats}

{agent_prompts}

Проведи полный анализ команды по всем 6 пунктам структуры.
Найди реальные слабые места на основе данных памяти.
Дай конкретные улучшения промптов — с цитатами старого и нового текста.
В конце — топ-3 приоритета для немедленного внедрения."""

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=4000, temperature=0.6)

    applied = []
    if apply_fixes:
        # Парсим блоки АГЕНТ/СТАРЫЙ ФРАГМЕНТ/НОВЫЙ ФРАГМЕНТ
        import re
        blocks = re.findall(
            r'АГЕНТ:\s*(.+?)\nПРОБЛЕМА:.+?\nСТАРЫЙ ФРАГМЕНТ:\s*(.+?)\nНОВЫЙ ФРАГМЕНТ:\s*(.+?)(?=\nАГЕНТ:|\Z)',
            result_text, re.DOTALL
        )
        agent_name_to_id = {v: k for k, v in dict(TEAM_AGENTS).items()}
        for agent_name_raw, old_frag, new_frag in blocks:
            agent_name = agent_name_raw.strip()
            # ищем по частичному совпадению
            agent_id = None
            for name, aid in [(v, k) for k, v in dict(TEAM_AGENTS).items()]:
                if any(word in agent_name for word in name.split("—")[0].strip().split()):
                    agent_id = aid
                    break
            if agent_id:
                ok = apply_prompt_fix(agent_id, old_frag.strip(), new_frag.strip())
                if ok:
                    applied.append(agent_id)

    memory_utils.add_insight(memory, f"Провёл аудит команды: {len(TEAM_AGENTS)} агентов", "team audit", "architecture")
    if applied:
        memory_utils.add_insight(memory, f"Применил улучшения для: {', '.join(applied)}", "team audit", "architecture")
    memory_utils.add_topic(memory, "аудит команды", result_text[:300])
    memory_utils.save(AGENT_ID, memory)

    return {
        "agent": "Алекс (Архитектор)",
        "analysis": result_text,
        "applied_fixes": applied
    }
