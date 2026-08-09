"""Persistent editorial memory and deterministic diversity controls for /post."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone

from . import memory_utils


MEMORY_ID = "telegram_editorial_history_v1"  # read-only rollback/migration source
TABLE = "editorial_drafts"
logger = logging.getLogger(__name__)


class EditorialStorageError(RuntimeError):
    pass

ENTRANCES = ("direct_thesis", "concrete_moment", "observation", "short_question")
ENDINGS = ("clear_conclusion", "precise_distinction", "quiet_observation", "open_question")
VIEWPOINTS = ("author_first_person", "reader_second_person", "shared_we", "neutral")

LABELS = {
    "direct_thesis": "прямой авторский тезис",
    "concrete_moment": "короткий конкретный момент",
    "observation": "спокойное наблюдение",
    "short_question": "короткий вопрос по существу",
    "clear_conclusion": "завершённая авторская мысль",
    "precise_distinction": "точное различение двух состояний",
    "quiet_observation": "тихое наблюдение без морали",
    "statement_final": "утвердительный финал без надёжной смысловой классификации",
    "open_question": "один открытый вопрос",
    "contrast_question": "контрастный вопрос «не X, а Y»",
    "author_first_person": "первое лицо автора",
    "reader_second_person": "обращение к читателю",
    "shared_we": "совместное «мы»",
    "neutral": "нейтральное наблюдение",
    "mixed": "смешанная точка зрения",
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

CONTRAST_QUESTION_RE = re.compile(
    r"(?:\bне\b[\s\S]{1,220}?\bа\b|\bне\s+потому\s+что\b[\s\S]{1,220}?\bа\s+потому\s+что\b|"
    r"\bэто\s+не\b[\s\S]{1,180}?(?:\bэто\b|\bскорее\b))",
    re.I,
)

AUTHOR_FIRST_PERSON_RE = re.compile(
    r"\b(?:я\s+бы|мне\s+кажется|для\s+меня|я\s+не\s+стал(?:а)?\s+бы|я\s+считаю|"
    r"я\s+думаю|я\s+здесь\s+вижу|я\s+предлагаю)\b",
    re.I,
)
READER_SECOND_PERSON_RE = re.compile(r"\b(?:ты|тебя|тебе|тобой|тво[йеяию]|тво(?:его|ей|ему|ем|ём|им|их|ими|ю)|вы|вас|вам|вами|ваш\w*)\b", re.I)
SHARED_WE_RE = re.compile(r"\b(?:мы|нас|нам|нами|наш\w*)\b", re.I)

SEMANTIC_STOPWORDS = {
    "который", "которая", "которые", "потому", "просто", "может", "иногда",
    "человек", "людей", "отношения", "сейчас", "только", "своей", "своего",
    "самого", "самому", "этого", "такой", "между", "всегда", "когда", "чтобы",
    "почему", "после", "перед", "больше", "меньше", "внутри", "словно", "будто",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_memory() -> dict:
    mem = memory_utils.load(MEMORY_ID)
    mem.setdefault("editorial_records", [])
    return mem


def recent_accepted(limit: int = 5) -> list[dict]:
    client = memory_utils._get_client()
    if not client:
        raise EditorialStorageError("Supabase client is unavailable")
    try:
        response = (
            client.table(TABLE)
            .select("draft_id,topic,text,planned_profile,actual_fingerprint,warnings,decided_at,created_at")
            .eq("status", "accepted")
            .order("decided_at", desc=True, nullsfirst=False)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        # Selector expects chronological order, oldest -> newest.
        return [
            {
                "id": row.get("draft_id"),
                "topic": row.get("topic", ""),
                "text": row.get("text", ""),
                "planned": row.get("planned_profile") or {},
                "actual": row.get("actual_fingerprint") or {},
                "warnings": row.get("warnings") or [],
                "status": "accepted",
                "decided_at": row.get("decided_at"),
            }
            for row in reversed(response.data or [])
        ]
    except Exception as exc:
        logger.warning("editorial_history_read_failed type=%s", type(exc).__name__)
        raise EditorialStorageError("Editorial history is unavailable") from exc


def _pick(options: tuple[str, ...], excluded: set[str], seed: str) -> str:
    available = [item for item in options if item not in excluded] or list(options)
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(available)
    return available[index]


def select_profile(topic: str, history: list[dict] | None = None) -> dict:
    history = history if history is not None else recent_accepted(5)
    last_two = history[-2:]
    # Rotate the intended form. Falling back to actual keeps old records compatible,
    # while avoiding a planned+actual union that can exhaust the whole enum.
    used_entrances = {r.get("planned", {}).get("entrance") or r.get("actual", {}).get("entrance") for r in last_two}
    used_endings = {r.get("planned", {}).get("ending") or r.get("actual", {}).get("ending") for r in last_two}
    used_viewpoints = {r.get("planned", {}).get("viewpoint") or r.get("actual", {}).get("viewpoint") for r in last_two}
    if "contrast_question" in used_endings:
        used_endings.add("open_question")
    entrance = _pick(ENTRANCES, used_entrances, topic + ":entrance:" + str(len(history)))
    ending = _pick(ENDINGS, used_endings, topic + ":ending:" + str(len(history)))
    viewpoint = _pick(VIEWPOINTS, used_viewpoints, topic + ":viewpoint:" + str(len(history)))
    recent_metaphors = sum(bool(r.get("actual", {}).get("metaphor")) for r in history[-3:])
    metaphor = recent_metaphors == 0 and int(hashlib.sha256(topic.encode("utf-8")).hexdigest()[-1], 16) % 4 == 0
    return {"entrance": entrance, "ending": ending, "viewpoint": viewpoint, "metaphor": metaphor}


def profile_instruction(profile: dict) -> str:
    metaphor_rule = (
        "Допустима максимум одна простая метафора, только если она проясняет мысль."
        if profile.get("metaphor")
        else "Пиши без метафор и образных сравнений."
    )
    return (
        f"Вход: {LABELS[profile['entrance']]}.\n"
        f"Точка зрения: {LABELS[profile.get('viewpoint', 'neutral')]}.\n"
        f"Финал: {LABELS[profile['ending']]}.\n"
        f"{metaphor_rule}\n"
        + (
            "Вырази авторскую позицию хотя бы одной честной фразой вроде «Я бы здесь различал…» или «Мне кажется важным…». Не придумывай опыт и случаи клиентов.\n"
            if profile.get("viewpoint") == "author_first_person" else ""
        )
        +
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
            f"точка зрения={LABELS.get(actual.get('viewpoint'), actual.get('viewpoint', 'не определена'))}; "
            f"финал={LABELS.get(actual.get('ending'), actual.get('ending', 'не определён'))}; "
            f"метафора={'да' if actual.get('metaphor') else 'нет'}"
        )
    return "\n".join(lines)


def _semantic_key(word: str) -> str:
    """A conservative Russian content-word key; enough for inflectional variants."""
    word = word.lower().replace("ё", "е")
    aliases = {
        "идеаль": "идеал", "образ": "идеал", "эталон": "идеал",
        "достиг": "пройден", "дистанц": "пройден", "путь": "пройден", "пройден": "пройден",
        "пустот": "пустота", "нехват": "нехватка", "дефиц": "нехватка",
        "опор": "опора", "поддерж": "опора", "сравн": "сравнение",
        "взгляд": "сравнение", "посмотр": "сравнение",
    }
    for prefix, canonical in aliases.items():
        if word.startswith(prefix):
            return canonical
    suffixes = (
        "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "его",
        "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ей", "ую", "юю",
        "ам", "ям", "ах", "ях", "ом", "ем", "ов", "ев", "ы", "и", "а", "я", "у", "ю",
    )
    for suffix in suffixes:
        if word.endswith(suffix) and len(word) - len(suffix) >= 5:
            word = word[:-len(suffix)]
            break
    return word


def semantic_terms(text: str, limit: int = 14) -> list[str]:
    """Return stable content words for a cheap, deterministic meaning preflight."""
    counts: dict[str, int] = {}
    for word in re.findall(r"[а-яё]{5,}", (text or "").lower()):
        if word in SEMANTIC_STOPWORDS:
            continue
        key = _semantic_key(word)
        counts[key] = counts.get(key, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.search(
            rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)(?=\n\s*[А-ЯЁ0-9][А-ЯЁ0-9 –—-]{{2,}}:|\Z)",
            text or "",
            re.S,
        )
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()[:600]
    return ""


def semantic_preflight(candidate_thesis: str, history: list[dict]) -> dict:
    """Detect recent semantic overlap without another model call or rewrite loop."""
    candidate = set(semantic_terms(candidate_thesis))
    matches = []
    for record in history[-7:]:
        previous_terms = set(record.get("actual", {}).get("semantic_terms") or semantic_terms(record.get("text", "")))
        if not candidate or not previous_terms:
            continue
        shared = sorted(candidate & previous_terms)
        score = len(shared) / max(1, min(len(candidate), len(previous_terms)))
        if len(shared) >= 3 and score >= 0.28:
            matches.append({
                "topic": record.get("topic", ""),
                "shared_terms": shared[:8],
                "score": round(score, 2),
            })
    return {
        "candidate_thesis": candidate_thesis,
        "semantic_terms": sorted(candidate),
        "duplicates": matches,
    }


def semantic_preflight_instruction(result: dict) -> str:
    thesis = result.get("candidate_thesis") or "не извлечён"
    duplicates = result.get("duplicates") or []
    lines = [f"Тезис до написания: {thesis}"]
    if not duplicates:
        lines.append("Среди последних принятых постов близкий смысловой механизм не найден.")
    else:
        lines.append("Обнаружен близкий недавний механизм. Не повторяй его; раскрой тему через другое наблюдаемое различение:")
        for item in duplicates:
            lines.append(f"• {item['topic']} (общие смысловые слова: {', '.join(item['shared_terms'])})")
    return "\n".join(lines)


def fingerprint(text: str, planned: dict | None = None) -> dict:
    stripped = text.strip()
    first_paragraph = stripped.split("\n\n", 1)[0].strip()
    if first_paragraph.endswith("?") and len(first_paragraph) <= 240:
        entrance = "short_question"
    elif re.search(r"\b(?:телефон|сообщение|кухн|вечер|утро|комнат|экран|встреч|разговор|двер|стол|такси|метро)\w*\b", first_paragraph, re.I) and re.search(r"\b(?:лежит|сидит|стоит|пишет|смотрит|идёт|едет|возвращается|звучит|спрашивает)\w*\b", first_paragraph, re.I):
        entrance = "concrete_moment"
    elif re.match(r"^(?:иногда\s+(?:замечаешь|видно|бывает)|бывает\s+момент|можно\s+заметить)", first_paragraph, re.I):
        entrance = "observation"
    else:
        entrance = "direct_thesis"

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", stripped) if part.strip()]
    final_tail = " ".join(paragraphs[-2:])[-1000:]
    if len(paragraphs) < 2:
        final_tail = " ".join(re.split(r"(?<=[.!?])\s+", stripped)[-3:])[-1000:]
    normalized_tail = re.sub(r"\s+", " ", final_tail).lower()
    if stripped.endswith("?") and CONTRAST_QUESTION_RE.search(normalized_tail):
        ending = "contrast_question"
    elif stripped.endswith("?"):
        ending = "open_question"
    elif re.search(r"\b(?:различие|отличие|границ[аеу]|одно\s+дело|один\b[\s\S]{0,180}\bдругой|одно\b[\s\S]{0,180}\bдругое|два\s+(?:способ|состояни|вопрос|навык))\b", stripped[-520:], re.I):
        ending = "precise_distinction"
    elif re.search(r"\b(?:попробуй|спроси|заметь|обрати\s+внимание)\b", stripped[-300:], re.I):
        ending = "gentle_action"
    elif re.search(r"\b(?:поэтому|значит|итог|вот\s+почему|вывод|начинается|означает|показывает|важно|нужно)\b", stripped[-300:], re.I):
        ending = "clear_conclusion"
    elif re.search(r"\b(?:может|возможно|иногда|похоже|кажется|тихо|порой)\b", stripped[-300:], re.I):
        ending = "quiet_observation"
    else:
        ending = "statement_final"

    text_without_quotes = re.sub(r"[«\"“][^»\"”]{0,300}[»\"”]", " ", stripped)
    # Do not treat a listed inner question ("чего я хочу?") as the author's voice.
    text_without_quotes = re.sub(r":\s*[^.!?]{0,240}\?", " ", text_without_quotes)
    viewpoint_counts = {
        "author_first_person": len(AUTHOR_FIRST_PERSON_RE.findall(text_without_quotes)),
        "reader_second_person": len(READER_SECOND_PERSON_RE.findall(text_without_quotes)),
        "shared_we": len(SHARED_WE_RE.findall(text_without_quotes)),
    }
    total_viewpoint = sum(viewpoint_counts.values())
    dominant, dominant_count = max(viewpoint_counts.items(), key=lambda item: item[1])
    if not total_viewpoint:
        viewpoint = "neutral"
    elif dominant_count / total_viewpoint >= 0.60:
        viewpoint = dominant
    else:
        viewpoint = "mixed"

    metaphor_markers = {match.lower() for match in METAPHOR_RE.findall(stripped)}
    metaphor_level = "extended" if len(metaphor_markers) >= 2 else ("incidental" if metaphor_markers else "none")

    viewpoint_match = not planned or viewpoint == planned.get("viewpoint")
    if planned and viewpoint == "mixed" and total_viewpoint:
        viewpoint_match = viewpoint_counts.get(planned.get("viewpoint"), 0) / total_viewpoint >= 0.50
    ending_match = not planned or ending == planned.get("ending")
    if planned and ending == "contrast_question" and planned.get("ending") == "open_question":
        ending_match = True
    if planned and ending == "statement_final" and planned.get("ending") in {"clear_conclusion", "quiet_observation"}:
        ending_match = True

    return {
        "entrance": entrance,
        "ending": ending,
        "viewpoint": viewpoint,
        "metaphor": metaphor_level == "extended",
        "metaphor_level": metaphor_level,
        "viewpoint_counts": viewpoint_counts,
        "semantic_terms": semantic_terms(stripped),
        "question_final": stripped.endswith("?"),
        "length": len(stripped),
        "planned_match": {
            "entrance": not planned or entrance == planned.get("entrance"),
            "ending": ending_match,
            "viewpoint": viewpoint_match,
            "metaphor": not planned or bool(planned.get("metaphor")) == (metaphor_level == "extended"),
        },
    }


def _warning(code: str, description: str, planned_value=None, actual_value=None) -> dict:
    return {"code": code, "description": description,
            "planned_value": planned_value, "actual_value": actual_value}


def warning_text(item: dict | str) -> str:
    return item if isinstance(item, str) else str(item.get("description", item.get("code", "")))


def diagnose(text: str, actual: dict, history: list[dict] | None = None,
             planned: dict | None = None) -> list[dict]:
    if history is None:
        try:
            history = recent_accepted(10)
        except EditorialStorageError:
            history = []
    warnings: list[dict] = []
    found = [name for name, pattern in CLICHE_PATTERNS if name != "and_maybe" and pattern.search(text)]
    alternative_markers = re.findall(r"\b(?:а\s+может(?:\s+быть)?|возможно|может,?\s+дело)\b", text, re.I)
    if len(alternative_markers) >= 2 and re.search(r"\bа\s+может(?:\s+быть)?\b", text, re.I):
        found.append("and_maybe")
    if found:
        warnings.append(_warning("familiar_construction", "Обнаружена знакомая конструкция: " + ", ".join(found) + "."))
    if history:
        prev = history[-1].get("actual", {})
        if actual.get("entrance") == prev.get("entrance") and actual.get("ending") == prev.get("ending"):
            warnings.append(_warning("repeated_shape", "Вход и финал совпали с предыдущим принятым постом."))
    recent_questions = sum(bool(r.get("actual", {}).get("question_final")) for r in history[-9:])
    if actual.get("question_final") and recent_questions >= 5:
        warnings.append(_warning("question_final_frequency", "Финал-вопрос уже использован минимум в пяти из последних девяти постов."))
    if actual.get("ending") == "contrast_question":
        recent_contrast = sum(
            r.get("actual", {}).get("ending") == "contrast_question" for r in history[-2:]
        )
        if recent_contrast:
            warnings.append(_warning("contrast_question_repeat", "Контрастный вопрос «не X, а Y» уже встречался среди двух предыдущих постов."))
    if planned:
        for axis in ("entrance", "viewpoint", "ending", "metaphor"):
            planned_value = planned.get(axis)
            actual_value = actual.get(axis)
            matches = planned_value == actual_value
            if axis == "ending" and planned_value == "open_question" and actual_value == "contrast_question":
                matches = True
            if axis == "ending" and actual_value == "statement_final" and planned_value in {"clear_conclusion", "quiet_observation"}:
                matches = True
            if axis == "viewpoint" and actual_value == "mixed":
                scores = actual.get("viewpoint_counts") or {}
                total = sum(scores.values())
                matches = bool(total and scores.get(planned_value, 0) / total >= 0.50)
            if not matches:
                warnings.append(_warning(
                    f"mismatch_{axis}",
                    f"Ось «{axis}» не отражена в тексте: план={planned_value}, факт={actual_value}.",
                    planned_value, actual_value,
                ))
        if actual.get("ending") == "contrast_question":
            warnings.append(_warning("contrast_question", "Финал построен как контрастный вопрос «не X, а Y»."))
    if actual.get("metaphor") and any(r.get("actual", {}).get("metaphor") for r in history[-2:]):
        warnings.append(_warning("metaphor_repeat", "Метафора снова появилась после недавнего поста с метафорой."))
    return warnings


def _client():
    client = memory_utils._get_client()
    if not client:
        raise EditorialStorageError("Supabase client is unavailable")
    return client


def get_draft(draft_id: str, chat_id: int | None = None) -> dict | None:
    try:
        query = _client().table(TABLE).select("*").eq("draft_id", draft_id)
        if chat_id is not None:
            query = query.eq("chat_id", chat_id)
        rows = query.limit(1).execute().data or []
        return rows[0] if rows else None
    except EditorialStorageError:
        raise
    except Exception as exc:
        raise EditorialStorageError("Draft lookup failed") from exc


def record_draft(chat_id: int, topic: str, text: str, planned: dict, actual: dict,
                 warnings: list[dict], revision_context: dict | None = None) -> str:
    client = _client()
    draft_id = uuid.uuid4().hex[:12]
    for attempt in range(2):
        row = {"draft_id": draft_id, "chat_id": chat_id, "status": "generated",
               "topic": topic, "text": text, "planned_profile": planned,
               "actual_fingerprint": actual, "warnings": warnings,
               "revision_context": revision_context, "revision_count": 0}
        try:
            client.table(TABLE).insert(row).execute()
            return draft_id
        except Exception as exc:
            lowered = str(exc).lower()
            if "duplicate" in lowered or "23505" in lowered:
                # A retry after an ambiguous network response may find the row that
                # was actually committed. Treat the matching owned row as success.
                try:
                    existing = get_draft(draft_id, chat_id)
                    if existing:
                        return draft_id
                except EditorialStorageError:
                    pass
                draft_id = uuid.uuid4().hex[:12]
                continue
            if attempt == 0:
                continue
            raise EditorialStorageError("Draft insert failed") from exc
    raise EditorialStorageError("Draft id collision")


def decide(draft_id: str, chat_id: int, status: str) -> tuple[str, dict | None]:
    if status not in {"accepted", "rejected"}:
        raise ValueError("Unsupported editorial status")
    try:
        response = (_client().table(TABLE).update({
            "status": status, "decided_at": _now(), "revision_context": None,
        }).eq("draft_id", draft_id).eq("chat_id", chat_id).eq("status", "generated").execute())
        if response.data:
            return "updated", response.data[0]
        current = get_draft(draft_id, chat_id)
        return ("already_decided", current) if current else ("not_found", None)
    except EditorialStorageError:
        raise
    except Exception as exc:
        raise EditorialStorageError("Draft decision failed") from exc


def revise_draft(old_draft_id: str, chat_id: int, text: str, planned: dict,
                 actual: dict, warnings: list[dict], revision_context: dict | None) -> str:
    client = _client()
    for _ in range(2):
        new_draft_id = uuid.uuid4().hex[:12]
        try:
            response = client.rpc("revise_editorial_draft", {
                "p_old_draft_id": old_draft_id, "p_chat_id": chat_id,
                "p_new_draft_id": new_draft_id, "p_new_text": text,
                "p_planned_profile": planned, "p_actual_fingerprint": actual,
                "p_warnings": warnings, "p_revision_context": revision_context,
            }).execute()
            data = response.data
            if isinstance(data, dict) and data.get("draft_id"):
                return data["draft_id"]
            if isinstance(data, list) and data and data[0].get("draft_id"):
                return data[0]["draft_id"]
            return new_draft_id
        except Exception as exc:
            lowered = str(exc).lower()
            if "insert_conflict" in lowered or "23505" in lowered or "duplicate" in lowered:
                continue
            raise EditorialStorageError("Atomic revision failed") from exc
    raise EditorialStorageError("Draft id collision during revision")


def legacy_accepted() -> list[dict]:
    return [r for r in _legacy_memory().get("editorial_records", []) if r.get("status") == "accepted"]
