"""
РЎРёСЃС‚РµРјР° РіР»СѓР±РѕРєРѕР№ РїР°РјСЏС‚Рё Р°РіРµРЅС‚РѕРІ вЂ” С…СЂР°РЅРµРЅРёРµ РІ Supabase (PostgreSQL).
Fallback РЅР° Р»РѕРєР°Р»СЊРЅС‹Рµ JSON-С„Р°Р№Р»С‹ РµСЃР»Рё Supabase РЅРµРґРѕСЃС‚СѓРїРµРЅ.
"""

import json
import os
from datetime import datetime

MEMORY_BASE = os.path.join(os.path.dirname(__file__), "..", "memory")

# Supabase РєР»РёРµРЅС‚ вЂ” РёРЅРёС†РёР°Р»РёР·РёСЂСѓРµС‚СЃСЏ РѕРґРёРЅ СЂР°Р·
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
    # Fallback вЂ” Р»РѕРєР°Р»СЊРЅС‹Р№ С„Р°Р№Р»
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
    # Fallback вЂ” Р»РѕРєР°Р»СЊРЅС‹Р№ С„Р°Р№Р»
    os.makedirs(MEMORY_BASE, exist_ok=True)
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
        lines.append(f"\n\nв•ђв•ђв•ђ РўР’РћРЇ РџРђРњРЇРўР¬ ({count} СЃРµСЃСЃРёР№) в•ђв•ђв•ђ")

    relevant = get_relevant_insights(memory, topic, n=8)
    if relevant:
        lines.append("\nРљР›Р®Р§Р•Р’Р«Р• РРќРЎРђР™РўР« (РёР· РїСЂРѕС€Р»РѕРіРѕ РѕРїС‹С‚Р°):")
        for ins in relevant:
            lines.append(f"вЂў {ins}")

    successful = memory["techniques"]["successful"][-5:]
    if successful:
        lines.append("\nР§РўРћ Р РђР‘РћРўРђР›Рћ Р›РЈР§РЁР• Р’РЎР•Р“Рћ:")
        for t in successful:
            lines.append(f"вњ“ {t['text']} [С‚РµРјР°: {t['topic']}]")

    failed = memory["techniques"]["failed"][-3:]
    if failed:
        lines.append("\nР§РўРћ РќР• Р РђР‘РћРўРђР›Рћ (РёР·Р±РµРіР°С‚СЊ):")
        for t in failed:
            lines.append(f"вњ— {t['text']}")

    feedback = memory["team_feedback"][-4:]
    if feedback:
        lines.append("\nРћРўР—Р«Р’Р« РљРћРњРђРќР”Р«:")
        for fb in feedback:
            lines.append(f"[{fb['from']}]: {fb['feedback']}")

    return "\n".join(lines)
