"""Persistent editorial memory and deterministic diversity controls for /post."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

from . import memory_utils


MEMORY_ID = "telegram_editorial_history_v1"
MAX_RECORDS = 100

ENTRANCES = ("direct_thesis", "concrete_moment", "observation", "short_question")
ENDINGS = ("clear_conclusion", "precise_distinction", "quiet_observation", "open_question")

LABELS = {
    "direct_thesis": "прямой авторский тезис",
    "concrete_moment": "короткий конкретный момент",
    "observation": "спокойное наблюдение",
    "short_question": "короткий вопрос по существу",
    "clear_conclusion": "завершённая авторская мысль",
    "precise_distinction": "точное различение двух состояний",
    "quiet_observation": "тихое наблюдение без морали",
    "open_question": "один открытый вопрос",
}

CLICHE_PATTERNS = (
    ("main_question", re.compile(r"(?:главн\w*\s+)?вопрос\s+не\s+в\s+том[^.?!]{0,180}\bа\s+в\s+том", re.I)),
    ("not_a_but_b", re.compile(r"\bэто\s+не\s+про\b[^.?!]{0,140}\bа\s+про\b", re.I)),
    ("maybe_not", re.compile(r"\bвозможно,?\s+дело\s+не\s+в\b", re.I)),
    ("and_maybe", re.compile(r"\bа\s+может(?:\s+быть)?\b", re.I)),
)

METAPHOR_RE = re.compile(
    r"\b(?:это\s+похоже\s+на|словно|будто|как\s+будто|напоминает|увеличительное\s+стекло|"
    r"спасательн\w+\s+круг|брон[яеи]|крепост\w*|гонк\w*|дистанци\w*|вершин\w*)\b",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory() -> dict:
    mem = memory_utils.load(MEMORY_ID)
    mem.setdefault("editorial_records", [])
    return mem


def recent_accepted(limit: int = 5) -> list[dict]:
    records = _memory().get("editorial_records", [])
    accepted = [r for r in records if r.get("status") == "accepted"]
    return accepted[-limit:]


def _pick(options: tuple[str, ...], excluded: set[str], seed: str) -> str:
    available = [item for item in options if item not in excluded] or list(options)
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(available)
    return available[index]


def select_profile(topic: str, history: list[dict] | None = None) -> dict:
    history = history if history is not None else recent_accepted(5)
    last_two = history[-2:]
    used_entrances = {r.get("actual", {}).get("entrance") or r.get("planned", {}).get("entrance") for r in last_two}
    used_endings = {r.get("actual", {}).get("ending") or r.get("planned", {}).get("ending") for r in last_two}
    entrance = _pick(ENTRANCES, used_entrances, topic + ":entrance:" + str(len(history)))
    ending = _pick(ENDINGS, used_endings, topic + ":ending:" + str(len(history)))
    recent_metaphors = sum(bool(r.get("actual", {}).get("metaphor")) for r in history[-3:])
    metaphor = recent_metaphors == 0 and int(hashlib.sha256(topic.encode("utf-8")).hexdigest()[-1], 16) % 4 == 0
    return {"entrance": entrance, "ending": ending, "metaphor": metaphor}


def profile_instruction(profile: dict) -> str:
    metaphor_rule = (
        "Допустима максимум одна простая метафора, только если она проясняет мысль."
        if profile.get("metaphor")
        else "Пиши без метафор и образных сравнений."
    )
    return (
        f"Вход: {LABELS[profile['entrance']]}.\n"
        f"Финал: {LABELS[profile['ending']]}.\n"
        f"{metaphor_rule}\n"
        "Это направление, а не жёсткий шаблон. Не называй эти параметры в посте."
    )


def history_brief(history: list[dict] | None = None) -> str:
    history = history if history is not None else recent_accepted(5)
    if not history:
        return "Принятых публикаций пока нет."
    lines = []
    for record in history[-5:]:
        actual = record.get("actual", {})
        lines.append(
            f"• вход={LABELS.get(actual.get('entrance'), actual.get('entrance', 'не определён'))}; "
            f"финал={LABELS.get(actual.get('ending'), actual.get('ending', 'не определён'))}; "
            f"метафора={'да' if actual.get('metaphor') else 'нет'}"
        )
    return "\n".join(lines)


def fingerprint(text: str, planned: dict | None = None) -> dict:
    stripped = text.strip()
    first_paragraph = stripped.split("\n\n", 1)[0].strip()
    if first_paragraph.endswith("?") and len(first_paragraph) <= 240:
        entrance = "short_question"
    elif re.match(r"^(?:я\s+бы|для\s+меня|мне\s+кажется|важно\s+различать)", first_paragraph, re.I):
        entrance = "direct_thesis"
    elif re.search(r"\b(?:телефон|сообщение|кухн|вечер|утро|комнат|экран|встреч|разговор)\w*\b", first_paragraph, re.I):
        entrance = "concrete_moment"
    else:
        entrance = "observation"

    if stripped.endswith("?"):
        ending = "open_question"
    elif re.search(r"\b(?:различие|отличие|границ[аеу]|одно\s+дело)\b", stripped[-420:], re.I):
        ending = "precise_distinction"
    elif re.search(r"\b(?:попробуй|спроси|заметь|обрати\s+внимание)\b", stripped[-300:], re.I):
        ending = "gentle_action"
    else:
        ending = "clear_conclusion"

    return {
        "entrance": entrance,
        "ending": ending,
        "metaphor": bool(METAPHOR_RE.search(stripped)),
        "question_final": stripped.endswith("?"),
        "length": len(stripped),
        "planned_match": {
            "entrance": not planned or entrance == planned.get("entrance"),
            "ending": not planned or ending == planned.get("ending"),
            "metaphor": not planned or bool(planned.get("metaphor")) == bool(METAPHOR_RE.search(stripped)),
        },
    }


def diagnose(text: str, actual: dict, history: list[dict] | None = None) -> list[str]:
    history = history if history is not None else recent_accepted(10)
    warnings = []
    found = [name for name, pattern in CLICHE_PATTERNS if pattern.search(text)]
    if found:
        warnings.append("Обнаружена знакомая конструкция: " + ", ".join(found) + ".")
    if history:
        prev = history[-1].get("actual", {})
        if actual.get("entrance") == prev.get("entrance") and actual.get("ending") == prev.get("ending"):
            warnings.append("Вход и финал совпали с предыдущим принятым постом.")
    recent_questions = sum(bool(r.get("actual", {}).get("question_final")) for r in history[-9:])
    if actual.get("question_final") and recent_questions >= 5:
        warnings.append("Финал-вопрос уже использован минимум в пяти из последних девяти постов.")
    if actual.get("metaphor") and any(r.get("actual", {}).get("metaphor") for r in history[-2:]):
        warnings.append("Метафора снова появилась после недавнего поста с метафорой.")
    return warnings


def record_draft(chat_id: int, topic: str, text: str, planned: dict, actual: dict,
                 warnings: list[str], revision_of: str = "") -> str:
    mem = _memory()
    draft_id = uuid.uuid4().hex[:12]
    mem["editorial_records"].append({
        "id": draft_id,
        "chat_id": chat_id,
        "created_at": _now(),
        "topic": topic,
        "text": text,
        "planned": planned,
        "actual": actual,
        "warnings": warnings,
        "status": "generated",
        "revision_of": revision_of,
    })
    mem["editorial_records"] = mem["editorial_records"][-MAX_RECORDS:]
    memory_utils.save(MEMORY_ID, mem)
    return draft_id


def set_status(draft_id: str, status: str) -> dict | None:
    if status not in {"accepted", "rejected", "revised"}:
        raise ValueError("Unsupported editorial status")
    mem = _memory()
    result = None
    for record in mem.get("editorial_records", []):
        if record.get("id") == draft_id:
            record["status"] = status
            record["decided_at"] = _now()
            result = record
            break
    if result:
        memory_utils.save(MEMORY_ID, mem)
    return result

