"""
Система глубокой памяти агентов — хранение в Supabase (PostgreSQL).
Fallback на локальные JSON-файлы если Supabase недоступен.
"""

import json
import os
from datetime import datetime

MEMORY_BASE = os.path.join(os.path.dirname(__file__), "..", "memory")

# Supabase клиент — инициализируется один раз
_supabase_client = None

def _get_client():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if url and key:
        try:
            from supabase import create_client
            _supabase_client = create_client(url, key)
        except Exception:
            _supabase_client = None
    return _supabase_client


def _path(agent_id: str) -> str:
    return os.path.join(MEMORY_BASE, f"{agent_id}_memory.json")


def load(agent_id: str) -> dict:
    client = _get_client()
    if client:
        try:
            res = client.table("agent_memory").select("memory").eq("agent_id", agent_id).execute()
            if res.data:
                return res.data[0]["memory"]
        except Exception:
            pass
    # Fallback — локальный файл
    path = _path(agent_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _empty_memory()


def save(agent_id: str, memory: dict):
    memory["profile"]["last_active"] = datetime.now().isoformat()
    memory["profile"]["sessions_count"] = memory["profile"].get("sessions_count", 0) + 1

    client = _get_client()
    if client:
        try:
            client.table("agent_memory").upsert({
                "agent_id": agent_id,
                "memory": memory
            }).execute()
            return
        except Exception:
            pass
    # Fallback — локальный файл
    os.makedirs(MEMORY_BASE, exist_ok=True)
    with open(_path(agent_id), "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def save_session_state(chat_id, state: dict):
    """Сохраняет состояние диалога с конкретным чатом (тема последнего поста, ожидание
    правки, готовые-но-не-отправленные разделы Instagram), чтобы рестарт/деплой процесса
    не сбрасывал то, на чём остановился разговор."""
    client = _get_client()
    if client:
        try:
            client.table("bot_session_state").upsert({
                "chat_id": chat_id,
                "state": state,
            }).execute()
            return
        except Exception:
            pass
    os.makedirs(MEMORY_BASE, exist_ok=True)
    with open(os.path.join(MEMORY_BASE, f"session_{chat_id}.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def load_session_state(chat_id) -> dict:
    client = _get_client()
    if client:
        try:
            res = client.table("bot_session_state").select("state").eq("chat_id", chat_id).execute()
            if res.data:
                return res.data[0]["state"]
        except Exception:
            pass
    path = os.path.join(MEMORY_BASE, f"session_{chat_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


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


def set_audience_profile(memory: dict, text: str):
    """Сохраняет актуальный реальный профиль аудитории (выведенный из данных канала),
    заменяя предыдущую версию — это не накопительный список, а текущий снимок."""
    memory["profile"]["audience_profile"] = {
        "text": text,
        "updated": datetime.now().isoformat(),
    }


def get_audience_profile(memory: dict) -> str:
    return memory["profile"].get("audience_profile", {}).get("text", "")


def add_insight(memory: dict, text: str, topic: str, category: str = "general"):
    memory["insights"].append({
        "text": text,
        "topic": topic,
        "category": category,
        "date": datetime.now().isoformat()
    })
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


def get_relevant_insights(memory: dict, topic: str, n: int = 8) -> list:
    topic_words = set(topic.lower().split())
    scored = []
    for insight in memory["insights"]:
        insight_words = set(insight["text"].lower().split())
        topic_words_in_insight = set(insight.get("topic", "").lower().split())
        score = len(topic_words & insight_words) + len(topic_words & topic_words_in_insight) * 2
        scored.append((score, insight["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [text for _, text in scored[:n]]
    recent = [i["text"] for i in memory["insights"][-3:]]
    combined = list(dict.fromkeys(top + recent))
    return combined[:n]


def build_context(memory: dict, topic: str) -> str:
    lines = []
    count = memory["profile"].get("sessions_count", 0)
    if count > 0:
        lines.append(f"\n\n═══ ТВОЯ ПАМЯТЬ ({count} сессий) ═══")

    audience_profile = get_audience_profile(memory)
    if audience_profile:
        lines.append("\nРЕАЛЬНЫЙ ПРОФИЛЬ АУДИТОРИИ (выведен из данных канала, актуален на сегодня):")
        lines.append(audience_profile)

    relevant = get_relevant_insights(memory, topic, n=8)
    if relevant:
        lines.append("\nКЛЮЧЕВЫЕ ИНСАЙТЫ (из прошлого опыта):")
        for ins in relevant:
            lines.append(f"• {ins}")

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

    topic_history = memory["topic_history"][-5:]
    if topic_history:
        lines.append("\nПОСЛЕДНИЕ ТЕМЫ КОМАНДЫ (проверь, не повторяешь ли ту же структуру/образ):")
        for t in topic_history:
            lines.append(f"• «{t['topic']}» — {t['summary'][:200]}")

    return "\n".join(lines)
