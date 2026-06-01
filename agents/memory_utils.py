"""
Система глубокой памяти для агентов SMM-команды.
Каждый агент имеет структурированную, растущую память без произвольных ограничений.
"""

import json
import os
from datetime import datetime
from typing import Optional


MEMORY_BASE = os.path.join(os.path.dirname(__file__), "..", "memory")


def _path(agent_id: str) -> str:
    return os.path.join(MEMORY_BASE, f"{agent_id}_memory.json")


def load(agent_id: str) -> dict:
    path = _path(agent_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _empty_memory()


def save(agent_id: str, memory: dict):
    os.makedirs(MEMORY_BASE, exist_ok=True)
    memory["profile"]["last_active"] = datetime.now().isoformat()
    memory["profile"]["sessions_count"] = memory["profile"].get("sessions_count", 0) + 1
    with open(_path(agent_id), "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def _empty_memory() -> dict:
    return {
        "profile": {
            "sessions_count": 0,
            "last_active": None,
            "personality_notes": []
        },
        "techniques": {
            "successful": [],
            "failed": []
        },
        "insights": [],
        "topic_history": [],
        "team_feedback": []
    }


def add_insight(memory: dict, text: str, topic: str, category: str = "general"):
    """Добавить инсайт/урок. Без жёсткого лимита — хранится до 200 инсайтов."""
    memory["insights"].append({
        "text": text,
        "topic": topic,
        "category": category,
        "date": datetime.now().isoformat()
    })
    # Храним 200 последних инсайтов — агент постоянно растёт
    memory["insights"] = memory["insights"][-200:]


def add_technique(memory: dict, text: str, topic: str, successful: bool):
    key = "successful" if successful else "failed"
    memory["techniques"][key].append({
        "text": text,
        "topic": topic,
        "date": datetime.now().isoformat()
    })
    memory["techniques"][key] = memory["techniques"][key][-100:]


def add_topic(memory: dict, topic: str, summary: str):
    memory["topic_history"].append({
        "topic": topic,
        "summary": summary,
        "date": datetime.now().isoformat()
    })
    memory["topic_history"] = memory["topic_history"][-50:]


def add_feedback(memory: dict, from_agent: str, feedback: str, topic: str):
    memory["team_feedback"].append({
        "from": from_agent,
        "feedback": feedback,
        "topic": topic,
        "date": datetime.now().isoformat()
    })
    memory["team_feedback"] = memory["team_feedback"][-50:]


def get_relevant_insights(memory: dict, topic: str, n: int = 8) -> list[str]:
    """Возвращает наиболее релевантные инсайты по ключевым словам темы."""
    topic_words = set(topic.lower().split())
    scored = []
    for insight in memory["insights"]:
        insight_words = set(insight["text"].lower().split())
        topic_words_in_insight = set(insight.get("topic", "").lower().split())
        score = len(topic_words & insight_words) + len(topic_words & topic_words_in_insight) * 2
        scored.append((score, insight["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    # Возвращаем топ-n релевантных + всегда берём последние 3
    top = [text for _, text in scored[:n]]
    recent = [i["text"] for i in memory["insights"][-3:]]
    combined = list(dict.fromkeys(top + recent))  # убираем дубли, сохраняем порядок
    return combined[:n]


def build_context(memory: dict, topic: str) -> str:
    """Формирует строку контекста памяти для вставки в системный промпт."""
    lines = []

    count = memory["profile"].get("sessions_count", 0)
    if count > 0:
        lines.append(f"\n\n═══ ТВОЯ ПАМЯТЬ ({count} сессий) ═══")

    relevant = get_relevant_insights(memory, topic, n=8)
    if relevant:
        lines.append("\nКЛЮЧЕВЫЕ ИНСАЙТЫ (из прошлого опыта):")
        for ins in relevant:
            lines.append(f"• {ins}")

    successful = memory["techniques"]["successful"][-5:]
    if successful:
        lines.append("\nЧТО РАБОТАЛО ЛУЧШЕ ВСЕГО:")
        for t in successful:
            lines.append(f"✓ {t['text']} [тема: {t['topic']}]")

    failed = memory["techniques"]["failed"][-3:]
    if failed:
        lines.append("\nЧТО НЕ РАБОТАЛО (избегать):")
        for t in failed:
            lines.append(f"✗ {t['text']}")

    feedback = memory["team_feedback"][-4:]
    if feedback:
        lines.append("\nОТЗЫВЫ КОМАНДЫ:")
        for fb in feedback:
            lines.append(f"[{fb['from']}]: {fb['feedback']}")

    personality = memory["profile"].get("personality_notes", [])
    if personality:
        lines.append("\nМОЯ ЭВОЛЮЦИЯ (как я изменился):")
        for note in personality[-3:]:
            lines.append(f"→ {note}")

    return "\n".join(lines)
