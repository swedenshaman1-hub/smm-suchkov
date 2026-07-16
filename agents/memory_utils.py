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


TEAM_AGENT_ID = "team_shared"


def add_used_image(image: str, topic: str):
    """Реестр центральных образов на уровне всей команды, а не одного агента —
    иначе Артём в новой сессии не видит, что Маша/Катя уже увели образ в сторону,
    и наоборот. Без этого повтор образа ловится только человеческим глазом на проде."""
    if not image or not image.strip():
        return
    memory = load(TEAM_AGENT_ID)
    memory.setdefault("used_images", [])
    memory["used_images"].append({
        "image": image.strip(),
        "topic": topic,
        "date": datetime.now().isoformat()
    })
    memory["used_images"] = memory["used_images"][-15:]
    save(TEAM_AGENT_ID, memory)


def get_recent_images(n: int = 10) -> list:
    memory = load(TEAM_AGENT_ID)
    return [i["image"] for i in memory.get("used_images", [])[-n:]]


def _add_team_element(key: str, value: str, topic: str, keep_last: int = 15):
    if not value or not value.strip():
        return
    memory = load(TEAM_AGENT_ID)
    memory.setdefault(key, [])
    memory[key].append({"value": value.strip(), "topic": topic, "date": datetime.now().isoformat()})
    memory[key] = memory[key][-keep_last:]
    save(TEAM_AGENT_ID, memory)


def _get_team_elements(key: str, n: int) -> list:
    memory = load(TEAM_AGENT_ID)
    return [i["value"] for i in memory.get(key, [])[-n:]]


def add_used_format(fmt: str, topic: str):
    """Архитектура/формат поста (нарратив, диалог, монолог...) — трекается отдельно
    от центрального образа, чтобы Маша не повторяла один и тот же скелет два раза подряд
    даже когда образы уже разные."""
    _add_team_element("used_formats", fmt, topic)


def get_recent_formats(n: int = 6) -> list:
    return _get_team_elements("used_formats", n)


def add_used_cta(cta: str, topic: str):
    _add_team_element("used_ctas", cta, topic)


def get_recent_ctas(n: int = 6) -> list:
    return _get_team_elements("used_ctas", n)


def add_used_angle(angle: str, topic: str):
    """Аспект темы, выбранный Ниной (какую грань темы она раскрывает) — трекается
    отдельно от образа и формата, чтобы поймать повтор на уровне ВЫБОРА, а не только
    лексики: команда может каждый раз менять слова, но выбирать один и тот же
    психологический архетип (например, «человек всем помогает и забыл себя»)."""
    _add_team_element("used_angles", angle, topic)


def get_recent_angles(n: int = 8) -> list:
    return _get_team_elements("used_angles", n)


def add_used_scheme(scheme: str, topic: str):
    """Смысловая схема сюжета одним предложением (напр. «человек жертвует собой →
    истощается → возвращается к себе») — повтор схемы это повтор даже когда слова,
    образ и формат все разные."""
    _add_team_element("used_schemes", scheme, topic)


def get_recent_schemes(n: int = 8) -> list:
    return _get_team_elements("used_schemes", n)


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

    recent_images = get_recent_images(n=10)
    if recent_images:
        lines.append("\n⛔ ЗАПРЕЩЕНО ПОВТОРЯТЬ — центральные образы, уже использованные в недавних постах команды (не только дословно, но и по типу — «сторож» и «страж» и «охранник» это один и тот же образ):")
        for img in recent_images:
            lines.append(f"✗ {img}")

    recent_formats = get_recent_formats(n=6)
    if recent_formats:
        lines.append("\n⛔ НЕ ПОВТОРЯЙ АРХИТЕКТУРУ — форматы/скелеты, уже использованные в недавних постах команды (выбери другой тип):")
        for f in recent_formats:
            lines.append(f"✗ {f}")

    recent_ctas = get_recent_ctas(n=6)
    if recent_ctas:
        lines.append("\n⛔ НЕ ПОВТОРЯЙ ЭТИ CTA-СЛОВА/ФРАЗЫ — уже использованы в недавних постах команды:")
        for c in recent_ctas:
            lines.append(f"✗ {c}")

    recent_angles = get_recent_angles(n=8)
    if recent_angles:
        lines.append("\n⛔ НЕ ПОВТОРЯЙ ЭТОТ ВЫБОР — грани/аспекты темы, уже раскрытые в недавних материалах команды (выбери другую грань, даже если слова будут другими):")
        for a in recent_angles:
            lines.append(f"✗ {a}")

    recent_schemes = get_recent_schemes(n=8)
    if recent_schemes:
        lines.append("\n⛔ НЕ ПОВТОРЯЙ ЭТУ СХЕМУ СЮЖЕТА — уже использована в недавних материалах команды, даже если слова и образ будут другими:")
        for s in recent_schemes:
            lines.append(f"✗ {s}")

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
