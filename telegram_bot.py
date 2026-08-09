"""
Telegram-бот SMM-команды Дмитрия Сучкова.
"""

import asyncio
import re
import logging
import os
import sys
import tempfile
import wave
import edge_tts

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters,
    PicklePersistence,
)
from google import genai as google_genai
from google.genai import types as genai_types

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# python-telegram-bot uses URLs containing the bot token; never emit them to logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

sys.path.insert(0, os.path.dirname(__file__))

from agents import (
    analyst, strategist, marketer, copywriter,
    instagram_writer, editor, instagram_editor,
    humanizer, publisher, offer_architect, team_architect, content_planner,
    community_manager, comment_analyst, channel_stats, channel_analyst,
    instagram_stats, instagram_analyst, instagram_messaging
)
from agents import memory_utils, notebook_live, team_registry
from agents import editorial_history, telegram_team

CHANNEL_CHAT_ID = -1001800141714

ROLES = {
    "Нина": "Нина Соколова (аналитик ЦА)",
    "Артём": "Артём Волков (стратег)",
    "Олег": "Олег Савин (маркетолог-аналитик)",
    "Маша": "Маша Лебедева (Telegram-копирайтер)",
    "Катя": "Катя Миронова (Instagram-копирайтер)",
    "Игорь": "Игорь Орлов (редактор Telegram)",
    "Лена": "Лена Волкова (редактор Instagram)",
    "Даша": "Даша Козлова (очеловечивание текста)",
    "Света": "Света Громова (финальный контроль)",
    "Виктор": "Виктор Самойлов (архитектор оффера)",
    "Соня": "Соня Белова (контент-планировщик)",
    "Миша": "Миша Захаров (менеджер комьюнити)",
    "Таня": "Таня Серова (аналитик комментариев и репутации)",
    "Алекс": "Алекс Громов (аудитор команды)",
}


def _clean_markdown(text: str) -> str:
    """Убирает markdown-разметку (### заголовки, **жирный**), которую агенты используют
    в структуре вывода — Telegram её не рендерит без parse_mode, и она остаётся как сырые символы."""
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", r"\1", text)
    return text


_VOICE_FILLER_RE = re.compile(r"\b(ммм+|э-э+|эм+|ну вот|короче|так)\b[,.]?\s*", re.IGNORECASE)
_VOICE_COMMAND_PREFIX_RE = re.compile(
    r"^(о'?кей[,.]?\s*)?(создай|напиши|сделай|сгенерируй)\s+(мне\s+)?(пост|оффер)\s+(на\s+тему|про|о)\s+",
    re.IGNORECASE
)


def _clean_voice_topic(text: str) -> str:
    """Убирает из расшифровки голосовой команды служебную обёртку («окей, создай пост на тему»)
    и слова-паразиты («ммм», «э-э»), оставляя только содержательную тему — иначе она целиком
    уходит в пайплайн как тема и сбивает анализ ЦА и стратегию."""
    cleaned = text.strip()
    cleaned = _VOICE_FILLER_RE.sub("", cleaned)
    cleaned = _VOICE_COMMAND_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.")
    return cleaned if cleaned else text.strip()


def _store_topic(user_data: dict, key: str, value: str):
    """Сохраняет длинный текст в user_data и возвращает короткий ключ для callback_data."""
    if "topics" not in user_data:
        user_data["topics"] = {}
    user_data["topics"][key] = value


def _get_topic(user_data: dict, key: str) -> str:
    return user_data.get("topics", {}).get(key, "")


_processed_message_ids = set()


def _already_processed(chat_id: int, message_id: int) -> bool:
    """Защита от повторной обработки одного и того же сообщения — бывает, что Telegram
    или перекрытие двух процессов во время деплоя присылают/обрабатывают update дважды,
    и бот отвечает на одно голосовое/текст по два раза."""
    key = (chat_id, message_id)
    if key in _processed_message_ids:
        return True
    _processed_message_ids.add(key)
    if len(_processed_message_ids) > 2000:
        _processed_message_ids.clear()
    return False


SESSION_KEYS = [
    "last_post_topic", "waiting_feedback", "pending_feedback", "pending_ig_sections", "topics",
    "ambiguous_feedback_text", "last_analysis", "last_strategy", "last_final_tg", "last_final_ig_post",
    "last_pipeline_mode", "last_hook_brief", "last_blueprint", "last_voice_brief",
    "last_ethics_context", "last_editorial_profile", "last_history_brief",
    "pending_editorial_draft_id", "revise_target_draft_id", "post_revision_count",
]

# Слова-триггеры чисто тональной правки — по ним доработка идёт сразу к Даше, минуя
# Нину, Артёма, Машу и Катю (маршрут "Даша → редактор" из ТЗ на правки команды).
_TONAL_FEEDBACK_KEYWORDS = (
    "тепл", "жив", "проще", "простот", "ближе", "пафос", "легче", "по-человечески", "человечнее",
)


def _is_tonal_feedback(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _TONAL_FEEDBACK_KEYWORDS)


def _persist_session(chat_id: int, user_data: dict):
    """Сохраняет ключевые поля разговора (тема последнего поста, ожидание правки,
    несотправленные разделы Instagram) в Supabase — переживает рестарт/деплой процесса,
    в отличие от чистого context.user_data."""
    state = {k: user_data[k] for k in SESSION_KEYS if k in user_data}
    try:
        memory_utils.save_session_state(chat_id, state)
    except Exception:
        logger.exception("Не удалось сохранить состояние сессии")


def _hydrate_session(chat_id: int, user_data: dict):
    """Подтягивает состояние разговора из Supabase, если процесс перезапустился
    и context.user_data оказался пустым."""
    if "last_post_topic" in user_data:
        return
    try:
        state = memory_utils.load_session_state(chat_id)
    except Exception:
        logger.exception("Не удалось загрузить состояние сессии")
        return
    for k, v in state.items():
        user_data.setdefault(k, v)


async def _send(msg: Message, text: str):
    text = _clean_markdown(text)
    limit = 4000
    listen_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔊 Слушать", callback_data="tts")]])

    header = text.strip().splitlines()[0] if text.strip() else ""
    is_header_line = header.endswith(":") and len(header) < 80

    chunks = [text[i:i + limit] for i in range(0, len(text), limit)]
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        if not chunk.strip():
            # Пустой/пробельный чанк возникает, когда граница в 4000 символов попадает
            # ровно на пробелы/переносы строк — Telegram отклоняет reply_text("") с
            # "Text must be non-empty" (падало на проде на длинных ревью редакторов,
            # которые выросли из-за обязательного changelog + полного текста).
            continue
        if is_header_line and idx > 1:
            chunk = f"{header} (часть {idx}/{total}):\n\n{chunk}"
        await msg.reply_text(chunk, reply_markup=listen_keyboard)


def _strip_label_header(text: str) -> str:
    """Убирает первую строку вида «ИМЯ (роль):» перед озвучкой — она не часть текста для чтения."""
    lines = text.split("\n", 1)
    if len(lines) == 2 and lines[0].rstrip().endswith(":") and len(lines[0]) < 100:
        return lines[1].lstrip("\n")
    return text


async def handle_tts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    raw_text = query.message.text or ""
    text = _strip_label_header(raw_text)
    if not text.strip():
        await query.message.reply_text("Нечего озвучивать — сообщение пустое.")
        return
    label_line = raw_text.strip().splitlines()[0] if raw_text != text else ""
    audio_path = None
    await query.message.reply_text("🔊 Озвучиваю — может занять до пары минут...")
    try:
        loop = asyncio.get_running_loop()
        try:
            audio_path = await asyncio.wait_for(
                loop.run_in_executor(None, _text_to_speech, text), timeout=55
            )
        except Exception as primary_error:
            logger.warning("Gemini TTS failed, switching to Edge TTS: %s", primary_error)
            await query.message.reply_text("Основной голос не ответил — переключаюсь на резервный...")
            audio_path = await asyncio.wait_for(_edge_text_to_speech(text), timeout=120)
        preview = text.strip().splitlines()[0][:60]
        caption = f"🔊 {label_line}\n{preview}…" if label_line else f"🔊 {preview}…"
        with open(audio_path, "rb") as f:
            await query.message.reply_audio(f, title=label_line or "Озвучка сообщения", caption=caption)
    except Exception as e:
        logger.exception("Ошибка озвучки")
        await query.message.reply_text("Не удалось озвучить: оба голосовых сервиса временно не ответили. Попробуй ещё раз через минуту.")
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except Exception:
                pass


def _text_to_speech(text: str) -> str:
    """Озвучивает текст через Gemini TTS (надёжнее на облачных серверах, чем gTTS,
    который ходит на неофициальный эндпоинт Google Translate и часто блокирует datacenter IP)."""
    client = google_genai.Client(api_key=GEMINI_API_KEY, http_options=genai_types.HttpOptions(timeout=45_000))
    last_error = None
    for attempt in range(1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text[:3000],
                config=genai_types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=genai_types.SpeechConfig(
                        voice_config=genai_types.VoiceConfig(
                            prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Kore")
                        )
                    ),
                ),
            )
            break
        except Exception as e:
            last_error = e
            if "DEADLINE_EXCEEDED" in str(e) or "504" in str(e) or "timeout" in str(e).lower():
                continue
            raise
    else:
        raise TimeoutError(f"Gemini TTS не ответил: {last_error}")
    pcm_data = response.candidates[0].content.parts[0].inline_data.data

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_data)
    return path


async def _edge_text_to_speech(text: str) -> str:
    """Fallback Russian neural voice when Gemini preview TTS is unavailable."""
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        communicate = edge_tts.Communicate(text[:3800], "ru-RU-SvetlanaNeural")
        await communicate.save(path)
        return path
    except Exception:
        try:
            os.unlink(path)
        except Exception:
            pass
        raise


_REFUSAL_MARKERS = (
    "требуется полностью новое тз", "не могу переписать", "не могу написать",
    "не могу продолжить работу", "додумываю самостоятельно", "нужно новое тз",
    "работаю строго в рамках стратегии", "не могу самостоятельно выбрать",
)


def _looks_like_real_post(text: str) -> bool:
    """Отличает готовый текст поста от внутренней переписки агентов (например, письма
    Кати с отказом писать без нового ТЗ). Раньше проверяли по тому, начинается ли текст
    с обращения к коллеге («Привет, Артём») — но писатели иногда предваряют настоящий,
    полноценный пакет коротким приветствием, и это ложно помечалось как отказ. Надёжнее
    искать сами фразы отказа по смыслу, а не по первому слову."""
    if not text or len(text.strip()) < 100:
        return False
    t = text.lower()
    return not any(marker in t for marker in _REFUSAL_MARKERS)


def _split_instagram_sections(text: str) -> list:
    """Разбивает Instagram-пакет (пост / сторис / карусель / Reels) на отдельные
    блоки, чтобы каждый формат можно было отправить отдельным сообщением."""
    labels = {
        "ОСНОВНОЙ ПОСТ": "ПОСТ",
        "СТОРИС-ПРОГРЕВ": "СТОРИС",
        "КАРУСЕЛЬ": "КАРУСЕЛЬ",
        "REELS": "REELS",
    }
    pattern = r"^[#\s]*\**\s*\d*[.\)]?\s*(ОСНОВНОЙ ПОСТ|СТОРИС[- ]ПРОГРЕВ|КАРУСЕЛЬ|REELS)\**\s*[^\n]*$"
    matches = list(re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE))
    if not matches:
        return [("INSTAGRAM-ПАКЕТ", text)]

    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        matched = m.group(1).upper().replace("-", " ")
        matched = re.sub(r"\s+", " ", matched).replace("СТОРИС ПРОГРЕВ", "СТОРИС-ПРОГРЕВ")
        label = labels.get(matched, matched)
        sections.append((label, text[start:end].strip()))
    return sections


def _extract_variant(text: str, letter: str) -> str:
    """Достаёт текст конкретного варианта (А/Б) из ответа копирайтера, чтобы
    дальше по цепочке передавался только выбранный вариант, а не оба сразу.
    Если редактор не назвал явный вариант (Gemini иногда не выводит строку
    "РЕКОМЕНДУЕМЫЙ ВАРИАНТ") — нельзя отдавать сырой текст с обоими вариантами
    дальше по конвейеру, иначе оба варианта склеятся в финальном посте.
    В этом случае берём вариант А по умолчанию, а не весь текст."""
    pattern_for = lambda l: rf"ВАРИАНТ\s+{l}\b.*?(?=ВАРИАНТ\s+[АБ]\b|ПОЧЕМУ\s+ЭТИ\s+ДВА\s+ВАРИАНТА|\Z)"

    def _try_extract(l: str):
        match = re.search(pattern_for(l), text, re.DOTALL | re.IGNORECASE)
        if not match:
            return None
        chunk = match.group(0).strip()
        lines = chunk.split("\n", 1)
        return lines[1].strip() if len(lines) > 1 else chunk

    if letter:
        result = _try_extract(letter)
        if result:
            return result
    # Нет явного выбора или паттерн не нашёлся — берём вариант А как детерминированный фолбэк
    fallback = _try_extract("А")
    return fallback if fallback else text


async def _run_blocking(fn, *args, **kwargs):
    """Выполняет блокирующий (синхронный) вызов агента в отдельном потоке,
    чтобы не замораживать цикл обработки событий бота (и его опрос Telegram)
    на те секунды-минуты, которые требует вызов Gemini. Таймаут — страховка
    на случай, если сетевой вызов внутри повиснет без собственной ошибки."""
    loop = asyncio.get_running_loop()
    try:
        # 240с, не 180 — чек-листы редакторов (Игорь/Лена/Олег) выросли: причинная цепочка,
        # тест переноса вины, обязательный changelog с полным текстом на итерации 2+ — это
        # больше выходных токенов на один вызов, чем раньше, а не только сетевые флуктуации.
        return await asyncio.wait_for(loop.run_in_executor(None, lambda: fn(*args, **kwargs)), timeout=240)
    except asyncio.TimeoutError:
        raise TimeoutError("Запрос к Gemini не ответил за 4 минуты — вероятно, временный сбой сети. Попробуй ещё раз.")


async def _transcribe_voice(file_path: str) -> str:
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    client = google_genai.Client(api_key=GEMINI_API_KEY, http_options=genai_types.HttpOptions(timeout=120_000))
    attempts = 5
    for attempt in range(attempts):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai_types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                    """Расшифруй это голосовое сообщение на русском языке.

Контекст: говорит Дмитрий Сучков — психолог, автор метода ГРЭМ, ведёт практику «Танец Души». Работает с предпринимателями и руководителями. Часто упоминает: ГРЭМ, Танец Души, сессии, выгорание, родовые программы, телесные практики.

Правила:
- Пиши точно как сказано, без пересказа
- Правильно расставляй знаки препинания
- Имена собственные и названия практик пиши с заглавной буквы: «Танец Души», «ГРЭМ»
- Только текст расшифровки, без комментариев и пояснений"""
                ]
            )
            return response.text.strip()
        except Exception as e:
            if ("503" in str(e) or "UNAVAILABLE" in str(e)) and attempt < attempts - 1:
                await asyncio.sleep(10 * (attempt + 1))
                continue
            raise


_active_pipelines = set()


async def _run_post(msg: Message, topic: str, user_data: dict, feedback: str = None, delivery_filter: str = "all"):
    chat_id = msg.chat_id
    if chat_id in _active_pipelines:
        await msg.reply_text(
            "Команда уже работает над предыдущим постом — подожди, пока он закончится, "
            "прежде чем запускать новый (иначе агенты будут работать вдвойне и мешать друг другу)."
        )
        return
    _active_pipelines.add(chat_id)
    try:
        await _run_post_inner_v3(msg, topic, user_data, feedback)
    finally:
        _active_pipelines.discard(chat_id)


class _StopPipeline(Exception):
    """Сигнал остановки пайплайна изнутри вложенной _revise_strategy — там обычный
    `return` останавливает только саму вложенную функцию, а не весь _run_post_inner.
    Сообщение пользователю уже отправлено до raise, здесь просто прекращаем работу
    без лишнего "Ошибка: ..." от общего except Exception ниже."""
    pass


async def _run_post_inner_v3(
    msg: Message,
    topic: str,
    user_data: dict,
    feedback: str = None,
):
    """One-pass writer room: expertise, copy, hook and human language."""
    route = team_registry.route_for(topic)
    reuse_previous = bool(
        feedback
        and user_data.get("last_post_topic") == topic
        and user_data.get("last_final_tg")
        and user_data.get("last_analysis")
    )
    try:
        if reuse_previous:
            editorial_context = user_data["last_analysis"]
            planned_profile = user_data.get("last_editorial_profile") or editorial_history.select_profile(topic)
            recent_history_brief = user_data.get("last_history_brief", "")
            await msg.reply_text(
                "Редакция — сохраняю один текст и вношу только твою правку..."
            )
        else:
            history_unavailable = False
            try:
                recent_history = editorial_history.recent_accepted(5)
            except editorial_history.EditorialStorageError:
                logger.warning("editorial_history_unavailable chat_id=%s", msg.chat_id)
                recent_history = []
                history_unavailable = True
            planned_profile = editorial_history.select_profile(topic, recent_history)
            recent_history_brief = editorial_history.history_brief(recent_history)
            await msg.reply_text(
                f"Создаю Telegram-пост по теме:\n«{topic}»\n\n"
                "Одна редакция, один автор, один готовый текст. "
                "Последовательных переписываний не будет."
            )
            await msg.reply_text(
                "NotebookLM — собираю четыре коротких заключения: экспертная "
                "опора и голос Дмитрия, копирайтинг Joanna Wiebe, хук Paddy "
                "Galloway и живой язык Ann Handley..."
            )
            try:
                contexts = await _run_blocking(
                    notebook_live.build_topic_context,
                    topic,
                    route.mode,
                    (
                        "smm02a_audience",
                        "smm02c_human_text",
                        "smm06_voice",
                        "smm09_hooks",
                    ),
                )
            except notebook_live.NotebookLiveError as exc:
                await msg.reply_text(
                    "Не начинаю текст: редакционные NotebookLM-блокноты "
                    f"не ответили. Причина: {exc}"
                )
                return
            candidate_thesis = (
                editorial_history.extract_labeled_value(
                    contexts.message_strategy, ("ЦЕНТРАЛЬНЫЙ ТЕЗИС",)
                )
                or editorial_history.extract_labeled_value(
                    contexts.author_voice, ("ЭКСПЕРТНАЯ ОПОРА",)
                )
                or topic
            )
            semantic_check = editorial_history.semantic_preflight(
                candidate_thesis, recent_history
            )
            planned_profile["semantic_thesis"] = candidate_thesis
            planned_profile["semantic_terms"] = semantic_check.get("semantic_terms", [])
            editorial_context = (
                "=== ДМИТРИЙ: ЭКСПЕРТИЗА И ГОЛОС ===\n"
                + contexts.author_voice
                + "\n\n=== JOANNA WIEBE: ЦЕНТРАЛЬНАЯ МЫСЛЬ ===\n"
                + contexts.message_strategy
                + "\n\n=== PADDY GALLOWAY: ТОЛЬКО ХУК ===\n"
                + contexts.dramaturgy
                + "\n\n=== ANN HANDLEY: ЖИВОЙ ЯЗЫК ===\n"
                + contexts.human_text
                + "\n\n=== РЕДАКЦИОННАЯ ФОРМА ЭТОГО ПОСТА ===\n"
                + editorial_history.profile_instruction(planned_profile)
                + "\n\n=== СМЫСЛОВОЙ PREFLIGHT ДО НАПИСАНИЯ ===\n"
                + editorial_history.semantic_preflight_instruction(semantic_check)
                + "\n\n=== ЧЕГО НЕ ПОВТОРЯТЬ ИЗ НЕДАВНИХ ПРИНЯТЫХ ПОСТОВ ===\n"
                + recent_history_brief
            )
            await msg.reply_text(
                "NotebookLM — четыре заключения готовы. Передаю их одному автору..."
            )

        await msg.reply_text(
            "Автор — пишу пост один раз, удерживая одну мысль от хука до финала..."
        )
        final_text = await _run_blocking(
            telegram_team.write_one_pass_editorial_post,
            topic,
            editorial_context,
            GEMINI_API_KEY,
            user_data.get("last_final_tg", "") if reuse_previous else "",
            feedback or "",
        )
        final_text = telegram_team.clean_editorial_output(final_text)
        if not final_text.strip():
            await msg.reply_text("Не публикую пустой ответ модели. Повтори запрос.")
            return
        if len(final_text) > 3900:
            await msg.reply_text(
                "Ответ превысил технический предел Telegram. Сформулируй тему короче."
            )
            return

        actual_fingerprint = editorial_history.fingerprint(final_text, planned_profile)
        diagnostic_warnings = editorial_history.diagnose(
            final_text, actual_fingerprint,
            history=(recent_history if not reuse_previous else None),
            planned=planned_profile,
        )
        revision_context = {
            "editorial_context": editorial_context[:16000],
            "history_brief": recent_history_brief,
        }
        previous_draft_id = user_data.get("revise_target_draft_id", "") if reuse_previous else ""
        try:
            if previous_draft_id:
                draft_id = editorial_history.revise_draft(
                    previous_draft_id, msg.chat_id, final_text, planned_profile,
                    actual_fingerprint, diagnostic_warnings, revision_context,
                )
            else:
                draft_id = editorial_history.record_draft(
                    msg.chat_id, topic, final_text, planned_profile,
                    actual_fingerprint, diagnostic_warnings, revision_context,
                )
        except editorial_history.EditorialStorageError:
            logger.exception("editorial_draft_save_failed chat_id=%s", msg.chat_id)
            await msg.reply_text(
                "━━━━━━━━━━━━━━━━━━━\nTelegram-пост готов\n━━━━━━━━━━━━━━━━━━━"
            )
            await _send(msg, final_text)
            await msg.reply_text(
                "⚠️ Черновик не сохранён из-за ошибки хранилища. Кнопки недоступны. "
                "Повтори запрос командой /post после восстановления."
            )
            return
        if feedback:
            mem = memory_utils.load("copywriter")
            memory_utils.add_feedback(mem, "Дмитрий", feedback, topic)
            memory_utils.save("copywriter", mem)

        user_data["last_post_topic"] = topic
        user_data["last_analysis"] = editorial_context[:16000]
        user_data["last_strategy"] = editorial_context[:8000]
        user_data["last_hook_brief"] = editorial_context[:8000]
        user_data["last_blueprint"] = editorial_context[:8000]
        user_data["last_message_map"] = editorial_context[:8000]
        user_data["last_voice_brief"] = contexts.author_voice if not reuse_previous else ""
        user_data["last_human_text_context"] = editorial_context[:6000]
        user_data["last_ethics_context"] = ""
        user_data["last_final_tg"] = final_text
        user_data["last_final_ig_post"] = ""
        user_data["last_pipeline_mode"] = "post"
        user_data["pending_ig_sections"] = {}
        user_data["waiting_feedback"] = False
        user_data["last_editorial_profile"] = planned_profile
        user_data["last_history_brief"] = recent_history_brief
        user_data["pending_editorial_draft_id"] = draft_id  # compatibility only; buttons do not read it
        user_data["revise_target_draft_id"] = ""
        user_data["post_revision_count"] = (int(user_data.get("post_revision_count", 0)) + 1) if reuse_previous else 0
        _persist_session(msg.chat_id, user_data)

        await msg.reply_text(
            "━━━━━━━━━━━━━━━━━━━\nTelegram-пост готов\n━━━━━━━━━━━━━━━━━━━"
        )
        await _send(msg, final_text)
        if diagnostic_warnings:
            await msg.reply_text(
                "Редакционная диагностика — предупреждения, не блокировка:\n\n• "
                + "\n• ".join(editorial_history.warning_text(item) for item in diagnostic_warnings)
            )
        if not reuse_previous and history_unavailable:
            await msg.reply_text(
                "⚠️ Редакционная история была недоступна; форма поста выбрана без учёта прошлых публикаций."
            )
        await msg.reply_text(
            "Выбери, что сделать с текстом. В историю принятых постов он попадёт только после подтверждения.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять текст", callback_data=f"post_accept:{draft_id}")],
                *([] if reuse_previous else [[InlineKeyboardButton("✏️ Одна правка", callback_data=f"post_revise:{draft_id}")]]),
                [InlineKeyboardButton("🗑 Отклонить", callback_data=f"post_reject:{draft_id}")],
            ]),
        )
    except Exception as exc:
        logger.exception("Ошибка в one-pass editorial pipeline")
        if (
            "503" in str(exc)
            or "UNAVAILABLE" in str(exc)
            or "overloaded" in str(exc).lower()
        ):
            await msg.reply_text(
                "Gemini временно перегружен даже после автоматического "
                "переключения на резервную модель. Попробуй позднее."
            )
        else:
            await msg.reply_text(f"Ошибка: {exc}")


async def _run_post_inner_v3_three_pass_legacy(
    msg: Message,
    topic: str,
    user_data: dict,
    feedback: str = None,
):
    """Simple pipeline: Masha draft -> Joanna master copy -> Dmitry voice."""
    route = team_registry.route_for(topic)
    reuse_previous = bool(
        feedback
        and user_data.get("last_post_topic") == topic
        and user_data.get("last_final_tg")
        and user_data.get("last_voice_brief")
    )
    try:
        if reuse_previous:
            voice_brief = user_data["last_voice_brief"]
            await msg.reply_text(
                "Маша — вношу только твою правку в предыдущий текст..."
            )
        else:
            await msg.reply_text(
                f"Создаю Telegram-пост по теме:\n«{topic}»\n\n"
                "Рабочая цепочка: Маша пишет один цельный черновик, Joanna "
                "Wiebe делает мастер-редактуру, SMM-06 возвращает голос Дмитрия."
            )
            await msg.reply_text(
                "NotebookLM — запрашиваю только Joanna Wiebe и голос Дмитрия..."
            )
            try:
                notebook_contexts = await _run_blocking(
                    notebook_live.build_topic_context,
                    topic,
                    route.mode,
                    ("smm02a_audience", "smm06_voice"),
                )
            except notebook_live.NotebookLiveError as exc:
                await msg.reply_text(
                    "Не начинаю текст: два обязательных NotebookLM-блокнота "
                    f"не ответили. Причина: {exc}"
                )
                return
            await msg.reply_text(
                "NotebookLM — готовы: "
                + ", ".join(notebook_contexts.selected_notebooks)
                + "."
            )
            voice_brief = await _run_blocking(
                telegram_team.build_voice_brief,
                topic,
                notebook_contexts.author_voice,
                GEMINI_API_KEY,
            )

        await msg.reply_text(
            "Маша — пишу один связный черновик прямо по заданной теме..."
        )
        draft = await _run_blocking(
            telegram_team.write_simple_draft,
            topic,
            GEMINI_API_KEY,
            user_data.get("last_final_tg", "") if reuse_previous else "",
            feedback or "",
        )

        await msg.reply_text(
            "Joanna Wiebe — перестраиваю черновик в один цельный пост..."
        )
        try:
            joanna_context = await _run_blocking(
                notebook_live.build_joanna_copy_context,
                topic,
                draft,
                route.mode,
            )
        except notebook_live.NotebookLiveError as exc:
            await msg.reply_text(
                "Мастер-копирайтер Joanna Wiebe не ответил. Пост не подменяю "
                f"обычной редактурой. Причина: {exc}"
            )
            return
        master_text = await _run_blocking(
            telegram_team.joanna_master_edit,
            topic,
            draft,
            joanna_context,
            GEMINI_API_KEY,
        )

        await msg.reply_text(
            "SMM-06 — возвращаю тексту ритм и лексику Дмитрия, не меняя смысл..."
        )
        final_text = await _run_blocking(
            telegram_team.apply_dmitry_voice,
            topic,
            master_text,
            voice_brief,
            GEMINI_API_KEY,
        )
        final_text = telegram_team.clean_editorial_output(final_text)
        if not final_text.strip():
            await msg.reply_text("Не публикую пустой ответ модели. Повтори запрос.")
            return
        if len(final_text) > 3900:
            await msg.reply_text(
                "Не публикую технически слишком длинный ответ Telegram. "
                "Сформулируй тему короче."
            )
            return

        memory_utils.register_published(
            topic,
            angle=joanna_context[:300],
            formats=["telegram_post"],
        )
        if feedback:
            for agent_id in ("copywriter", "humanizer"):
                mem = memory_utils.load(agent_id)
                memory_utils.add_feedback(mem, "Дмитрий", feedback, topic)
                memory_utils.save(agent_id, mem)

        user_data["last_post_topic"] = topic
        user_data["last_analysis"] = joanna_context[:10000]
        user_data["last_strategy"] = joanna_context
        user_data["last_hook_brief"] = joanna_context
        user_data["last_blueprint"] = joanna_context
        user_data["last_message_map"] = joanna_context
        user_data["last_voice_brief"] = voice_brief
        user_data["last_human_text_context"] = joanna_context[:6000]
        user_data["last_ethics_context"] = ""
        user_data["last_final_tg"] = final_text
        user_data["last_final_ig_post"] = ""
        user_data["last_pipeline_mode"] = "post"
        user_data["pending_ig_sections"] = {}
        user_data["waiting_feedback"] = False
        _persist_session(msg.chat_id, user_data)

        await msg.reply_text(
            "━━━━━━━━━━━━━━━━━━━\nTelegram-пост готов\n━━━━━━━━━━━━━━━━━━━"
        )
        await _send(msg, final_text)
        await msg.reply_text(
            "Если нужна правка — нажми кнопку и напиши, что изменить.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Доработать пост", callback_data="revise")
            ]]),
        )
    except Exception as exc:
        logger.exception("Ошибка в simple copywriter Telegram pipeline")
        if (
            "503" in str(exc)
            or "UNAVAILABLE" in str(exc)
            or "overloaded" in str(exc).lower()
        ):
            await msg.reply_text(
                "Gemini временно перегружен даже после автоматического "
                "переключения на резервную модель. Попробуй позднее."
            )
        else:
            await msg.reply_text(f"Ошибка: {exc}")


async def _run_post_inner_v3_legacy(
    msg: Message,
    topic: str,
    user_data: dict,
    feedback: str = None,
):
    """Bounded pipeline: message map → blueprint → draft → human edit → audit."""
    route = team_registry.route_for(topic)
    reuse_previous = bool(
        feedback
        and user_data.get("last_post_topic") == topic
        and user_data.get("last_blueprint")
        and user_data.get("last_message_map")
        and user_data.get("last_voice_brief")
        and user_data.get("last_human_text_context")
        and user_data.get("last_final_tg")
    )
    try:
        if reuse_previous:
            await msg.reply_text(
                "Сохраняю утверждённый экспертный blueprint. "
                "Меняю только то, о чём ты попросил."
            )
            blueprint = user_data["last_blueprint"]
            voice_brief = user_data["last_voice_brief"]
            human_text_context = user_data.get("last_human_text_context", "")
            message_map = user_data.get("last_message_map", "")
            ethics_context = user_data.get("last_ethics_context", "")
            expert_context = user_data.get("last_analysis", blueprint)
            selected_notebooks = ()
        else:
            await msg.reply_text(
                f"Создаю Telegram-пост по теме:\n«{topic}»\n\n"
                f"Режим: {team_registry.MODE_LABELS[route.mode]}.\n"
                "Сначала Joanna Wiebe формирует карту сообщения, затем "
                "NotebookLM-эксперты и главред фиксируют blueprint. Один автор "
                "пишет текст, Ann Handley делает одну человечную редактуру. "
                "Максимум одна содержательная правка."
            )
            await msg.reply_text(
                "NotebookLM — собираю раздельные решения по языку, углу, "
                "драматургии, хуку, этике и голосу..."
            )
            try:
                notebook_contexts = await _run_blocking(
                    notebook_live.build_topic_context,
                    topic,
                    route.mode,
                )
            except notebook_live.NotebookLiveError as exc:
                await msg.reply_text(
                    "Останавливаюсь до написания текста: живой маршрут "
                    f"NotebookLM не прошёл.\n\nПричина: {exc}\n\n"
                    "Скрытой подмены обычным Gemini не будет."
                )
                return

            selected_notebooks = notebook_contexts.selected_notebooks
            await msg.reply_text(
                "NotebookLM — решения получены: "
                + ", ".join(selected_notebooks)
                + "."
                + (
                    "\nНеобязательные источники пропущены: "
                    + ", ".join(notebook_contexts.skipped_optional)
                    if notebook_contexts.skipped_optional
                    else ""
                )
            )

            # Raw ethics language is intentionally excluded from creation:
            # it often names the very market metaphors it forbids. Ethics gets
            # the finished text as a veto, never ownership of the thesis.
            audience_memory = memory_utils.load("analyst")
            audience_evidence = memory_utils.get_audience_profile(
                audience_memory
            )
            await msg.reply_text(
                "Joanna Wiebe — фиксирую конфликт, обещание читателю и три "
                "честных хука до создания blueprint..."
            )
            message_map = await _run_blocking(
                telegram_team.build_message_map,
                topic,
                notebook_contexts.message_strategy,
                GEMINI_API_KEY,
                audience_evidence,
            )

            expert_context = notebook_contexts.without_roles(
                "voice",
                "ethics",
                "audience",
                "human_text",
            )
            ethics_context = notebook_contexts.ethics
            await msg.reply_text(
                "Главред — свожу экспертные решения в один неизменяемый "
                "blueprint и разрешаю конфликты в пользу этики и честности..."
            )
            blueprint = await _run_blocking(
                telegram_team.build_editorial_blueprint,
                topic,
                expert_context,
                GEMINI_API_KEY,
                route.mode,
                message_map,
            )
            blueprint_issues = await _run_blocking(
                telegram_team.full_blueprint_issues,
                topic,
                blueprint,
                GEMINI_API_KEY,
            )
            if blueprint_issues:
                await msg.reply_text(
                    "Главред — автоматическое этическое вето отклонило первый "
                    "каркас. Исправляю каркас один раз до написания текста..."
                )
                blueprint = await _run_blocking(
                    telegram_team.repair_editorial_blueprint,
                    topic,
                    blueprint,
                    blueprint_issues,
                    GEMINI_API_KEY,
                    route.mode,
                )
                blueprint_issues = await _run_blocking(
                    telegram_team.full_blueprint_issues,
                    topic,
                    blueprint,
                    GEMINI_API_KEY,
                )
                if blueprint_issues:
                    blueprint_blockers = (
                        telegram_team.blueprint_publication_blockers(
                            blueprint_issues
                        )
                    )
                    if blueprint_blockers:
                        await msg.reply_text(
                            "Не запускаю автора: экспертный каркас после одной "
                            "коррекции всё ещё содержит опасный смысловой риск: "
                            + "; ".join(blueprint_blockers)
                            + "."
                        )
                        return
                    blueprint = telegram_team.add_blueprint_cautions(
                        blueprint,
                        blueprint_issues,
                    )
                    await msg.reply_text(
                        "Главред — спорная причинная формулировка не запускает "
                        "новый круг. Программа запрещает переносить её в текст "
                        "и оставляет только наблюдаемое различие..."
                    )

            await msg.reply_text(
                "Даша — извлекаю из SMM-06 только ритм, синтаксис и лексику. "
                "Содержание блокнота в пост не попадёт..."
            )
            voice_brief = await _run_blocking(
                telegram_team.build_voice_brief,
                topic,
                notebook_contexts.author_voice,
                GEMINI_API_KEY,
            )

        await msg.reply_text(
            "Маша — пишу один пост по утверждённому blueprint..."
        )
        draft = await _run_blocking(
            telegram_team.write_editorial_post,
            topic,
            blueprint,
            voice_brief,
            GEMINI_API_KEY,
            user_data.get("last_final_tg", "") if reuse_previous else "",
            feedback or "",
        )

        await msg.reply_text(
            "Ann Handley — проверяю конкретный черновик по её NotebookLM, "
            "затем один раз убираю лекционный тон, повторы и неестественные "
            "конструкции, не меняя blueprint..."
        )
        try:
            human_text_context = await _run_blocking(
                notebook_live.build_human_text_context,
                topic,
                draft,
                route.mode,
            )
        except notebook_live.NotebookLiveError as exc:
            logger.warning("Ann Handley NotebookLM fallback: %s", exc)
            human_text_context = (
                "Резервная редактура формы: убрать лекционный тон и повторы; "
                "заменить абстрактные категории наблюдаемыми действиями; "
                "исправить неестественный русский; прочитать фразы вслух; "
                "не менять blueprint, тезис, сцену, факты и вывод."
            )
            await msg.reply_text(
                "Ann Handley — блокнот дважды вернул пустой ответ. "
                "Продолжаю без остановки по резервному контракту живого языка; "
                "blueprint и смысл сохраняются."
            )
        draft = await _run_blocking(
            telegram_team.human_edit_editorial_post,
            topic,
            blueprint,
            draft,
            human_text_context,
            voice_brief,
            GEMINI_API_KEY,
        )
        draft = telegram_team.clean_human_surface(topic, draft)
        draft_issues = telegram_team.editorial_contract_issues(topic, draft)

        await msg.reply_text(
            "Игорь — провожу один аудит смысла, этики, хука и завершённости..."
        )
        audit = await _run_blocking(
            telegram_team.audit_editorial_post,
            topic,
            blueprint,
            draft,
            ethics_context,
            GEMINI_API_KEY,
            draft_issues,
            message_map,
            human_text_context,
        )

        final_text = draft
        if not audit["accepted"]:
            await msg.reply_text(
                "Игорь нашёл блокирующий дефект. Маша исправляет этот же текст "
                "один раз. Новых вариантов и редакционных кругов не будет..."
            )
            final_text = await _run_blocking(
                telegram_team.repair_editorial_post,
                topic,
                blueprint,
                draft,
                audit["review"],
                voice_brief,
                GEMINI_API_KEY,
                draft_issues,
                human_text_context,
            )
            final_text = telegram_team.clean_human_surface(topic, final_text)
            final_issues = telegram_team.editorial_contract_issues(
                topic,
                final_text,
            )
            final_blockers = telegram_team.editorial_publication_blockers(
                topic,
                final_text,
            )
            if telegram_team.only_technical_surface_blockers(final_blockers):
                await msg.reply_text(
                    "Света — после содержательной правки остался только "
                    "формальный дефект. Исправляю род и грамматику без "
                    "изменения смысла..."
                )
                final_text = await _run_blocking(
                    telegram_team.technical_surface_cleanup,
                    topic,
                    final_text,
                    final_blockers,
                    GEMINI_API_KEY,
                )
                final_text = telegram_team.clean_human_surface(topic, final_text)
                final_issues = telegram_team.editorial_contract_issues(
                    topic,
                    final_text,
                )
                final_blockers = telegram_team.editorial_publication_blockers(
                    topic,
                    final_text,
                )
            if final_blockers:
                await msg.reply_text(
                    "Ограниченный цикл завершён. Не публикую текст, который "
                    "всё ещё содержит смысловой, фактический или брендовый риск: "
                    + "; ".join(final_blockers)
                    + ". Нового автоматического переписывания не будет."
                )
                return
            non_blocking_notes = [
                issue for issue in final_issues if issue not in final_blockers
            ]
            if non_blocking_notes:
                logger.info(
                    "Non-blocking editorial notes after the single repair: %s",
                    "; ".join(non_blocking_notes),
                )

        memory_utils.register_published(
            topic,
            angle=blueprint[:300],
            formats=["telegram_post"],
        )
        if feedback:
            for agent_id in ("copywriter", "editor", "humanizer"):
                mem = memory_utils.load(agent_id)
                memory_utils.add_feedback(mem, "Дмитрий", feedback, topic)
                memory_utils.save(agent_id, mem)

        user_data["last_post_topic"] = topic
        user_data["last_analysis"] = expert_context[:10000]
        user_data["last_strategy"] = blueprint
        user_data["last_hook_brief"] = blueprint
        user_data["last_blueprint"] = blueprint
        user_data["last_message_map"] = message_map
        user_data["last_voice_brief"] = voice_brief
        user_data["last_human_text_context"] = human_text_context[:6000]
        user_data["last_ethics_context"] = ethics_context
        user_data["last_final_tg"] = final_text
        user_data["last_final_ig_post"] = ""
        user_data["last_pipeline_mode"] = "post"
        user_data["pending_ig_sections"] = {}
        user_data["waiting_feedback"] = False
        _persist_session(msg.chat_id, user_data)

        await msg.reply_text(
            "━━━━━━━━━━━━━━━━━━━\nTelegram-пост готов\n━━━━━━━━━━━━━━━━━━━"
        )
        await _send(msg, final_text)
        await msg.reply_text(
            "Если нужна правка — нажми кнопку и напиши, что изменить. "
            "Blueprint и смысловой угол сохранятся.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Доработать пост", callback_data="revise")
            ]]),
        )
    except Exception as exc:
        logger.exception("Ошибка в bounded expert Telegram pipeline")
        if (
            "503" in str(exc)
            or "UNAVAILABLE" in str(exc)
            or "overloaded" in str(exc).lower()
        ):
            await msg.reply_text(
                "Gemini временно перегружен. Повтори тему через пару минут."
            )
        else:
            await msg.reply_text(f"Ошибка: {exc}")


async def _run_post_inner(msg: Message, topic: str, user_data: dict, feedback: str = None):
    """Compact Telegram-only pipeline: research → angles → drafts → edit → voice."""
    route = team_registry.route_for(topic)
    reuse_previous = bool(
        feedback and user_data.get("last_post_topic") == topic
        and user_data.get("last_analysis") and user_data.get("last_strategy")
    )
    try:
        await msg.reply_text(
            f"Создаю Telegram-пост по теме:\n«{topic}»\n\n"
            f"Режим: {team_registry.MODE_LABELS[route.mode]}.\n"
            "Сначала маршрутизатор выбирает релевантные NotebookLM-блокноты, "
            "затем запускает редакционную команду. Обычно 2–4 минуты."
        )

        await msg.reply_text(
            "NotebookLM — запрашиваю только назначенных этому режиму экспертов..."
        )
        try:
            notebook_contexts = await _run_blocking(
                notebook_live.build_topic_context, topic, route.mode
            )
        except notebook_live.NotebookLiveError as exc:
            await msg.reply_text(
                "Останавливаюсь до написания текста: живой маршрут через Gemini "
                f"Notebook не прошёл.\n\nПричина: {exc}\n\n"
                "Обычный Gemini вместо блокнотов скрытно не использую."
            )
            return
        await msg.reply_text(
            "NotebookLM — обязательные блокноты ответили. "
            f"В маршрут вошли: {', '.join(notebook_contexts.selected_notebooks)}."
            + (
                "\nНеобязательные источники пока пропущены: "
                + ", ".join(notebook_contexts.skipped_optional)
                if notebook_contexts.skipped_optional
                else ""
            )
        )

        # Do not feed recent channel posts back into the writer automatically.
        # A generated post can be published before Dmitriy has approved it as a
        # voice reference; reusing it here creates a self-reinforcing AI style.
        # Until an explicit approved-posts collection exists, SMM-06 is the only
        # source of Dmitriy's voice.
        voice_samples = ""

        if reuse_previous:
            research_note = user_data["last_analysis"]
            strategy_output = user_data["last_strategy"]
            commercial_blueprint = user_data.get("last_commercial_blueprint", "")
            await msg.reply_text("Сохраняю ранее выбранную стратегию и меняю только текст по твоей правке.")
        else:
            await msg.reply_text("Нина — собираю фактическую опору и живые ситуации...")
            research_note = await _run_blocking(
                telegram_team.research, topic, GEMINI_API_KEY,
                notebook_contexts.for_agents("researcher"),
            )

            commercial_blueprint = ""
            if route.mode == team_registry.COMMERCIAL:
                await msg.reply_text(
                    "Виктор — собираю честный коммерческий каркас без "
                    "выдуманных обещаний и дефицита..."
                )
                offer_result = await _run_blocking(
                    offer_architect.run,
                    topic,
                    research_note,
                    GEMINI_API_KEY,
                    notebook_context=(
                        notebook_contexts.for_agents("offer_architect")
                        + "\n\n"
                        + notebook_contexts.ethics
                    ),
                )
                commercial_blueprint = offer_result["offer"]

            await msg.reply_text("Артём — создаю пять разных смысловых углов и выбираю сильнейший...")
            strategy_notebooks = notebook_contexts.for_agents("strategist")
            if commercial_blueprint:
                strategy_notebooks += (
                    "\n\nКОММЕРЧЕСКИЙ КАРКАС ВИКТОРА:\n"
                    + commercial_blueprint
                )
            strategy_output = await _run_blocking(
                telegram_team.strategize, topic, research_note, GEMINI_API_KEY,
                strategy_notebooks,
            )
            strategy_issues = telegram_team.strategy_warnings(strategy_output)
            if strategy_issues:
                await msg.reply_text(
                    "Артём использовал недоказанный психологический механизм. "
                    "Перестраиваю смысловой угол до написания текста..."
                )
                strategy_output = await _run_blocking(
                    telegram_team.repair_strategy,
                    topic,
                    research_note,
                    strategy_output,
                    strategy_issues,
                    GEMINI_API_KEY,
                    notebook_context=(
                        notebook_contexts.for_agents("strategist") + "\n\n"
                        + notebook_contexts.ethics
                    ),
                )
                remaining_strategy_issues = telegram_team.strategy_warnings(
                    strategy_output
                )
                if remaining_strategy_issues:
                    await msg.reply_text(
                        "Стратегия всё ещё назначает причину. Последний раз "
                        "перевожу её в формат честного различения..."
                    )
                    strategy_output = await _run_blocking(
                        telegram_team.repair_strategy,
                        topic,
                        research_note,
                        strategy_output,
                        remaining_strategy_issues,
                        GEMINI_API_KEY,
                        notebook_context=notebook_contexts.ethics,
                    )
                    final_strategy_issues = telegram_team.strategy_warnings(
                        strategy_output
                    )
                    if final_strategy_issues:
                        await msg.reply_text(
                            "Останавливаюсь до написания поста: после двух "
                            "исправлений стратегия всё ещё держится на "
                            "недоказанном механизме ("
                            + "; ".join(final_strategy_issues) + ")."
                        )
                        return

        hook_brief = user_data.get("last_hook_brief", "") if reuse_previous else ""
        if hook_brief:
            await msg.reply_text(
                "Кирилл — сохраняю ранее выбранную механику хука для точечной правки."
            )
        else:
            await msg.reply_text(
                "Кирилл — создаю пять честных входов по SMM-09 и выбираю один хук..."
            )
            hook_brief = await _run_blocking(
                telegram_team.design_hook,
                topic,
                strategy_output,
                GEMINI_API_KEY,
                notebook_context=notebook_contexts.for_agents("hook_editor"),
            )

        await msg.reply_text("Маша — пишу три действительно разных варианта...")
        variants = await _run_blocking(
            telegram_team.write, topic, research_note, strategy_output, GEMINI_API_KEY,
            feedback=feedback,
            previous_text=user_data.get("last_final_tg") if feedback else None,
            voice_samples=voice_samples,
            notebook_context=(
                notebook_contexts.for_agents("writer")
                + (
                    "\n\nКОММЕРЧЕСКИЙ КАРКАС ВИКТОРА:\n"
                    + commercial_blueprint
                    if commercial_blueprint
                    else ""
                )
            ),
            hook_brief=hook_brief,
        )

        await msg.reply_text("Игорь — выбираю лучший вариант и проверяю смысл...")
        editorial = await _run_blocking(
            telegram_team.review, topic, strategy_output, variants, GEMINI_API_KEY,
            notebook_context=notebook_contexts.for_agents("editor"),
            hook_brief=hook_brief,
        )
        selected = telegram_team.extract_variant(variants, editorial["variant"])
        draft_warnings = list(dict.fromkeys(
            telegram_team.quality_warnings(selected)
            + telegram_team.structural_warnings(topic, selected)
        ))
        if draft_warnings:
            editorial["review"] += (
                "\n\nАвтоматические замечания к выбранному варианту:\n- "
                + "\n- ".join(draft_warnings)
            )

        if not editorial["accepted"] or draft_warnings:
            await msg.reply_text(
                "Игорь выбрал один вариант и передал Маше только обязательные "
                "содержательные правки."
            )

        await msg.reply_text(
            "Даша — даю Маше короткие настройки голоса, не переписывая текст..."
        )
        voice_notes = await _run_blocking(
            telegram_team.advise_voice, topic, selected, GEMINI_API_KEY,
            voice_samples=voice_samples,
            notebook_context=notebook_contexts.for_agents("voice"),
        )

        await msg.reply_text(
            "Маша — один раз собираю окончательный текст из выбранного хука, "
            "варианта, правок Игоря и настроек Даши..."
        )
        # Dasha distils SMM-06 into bounded style notes above.  The final
        # writer receives those notes, not the raw voice-notebook answer, so
        # worldview or old subject matter cannot leak in as new content.
        final_context = notebook_contexts.for_agents("writer")
        polished = await _run_blocking(
            telegram_team.assemble_final,
            topic,
            strategy_output,
            selected,
            editorial["review"],
            voice_notes,
            GEMINI_API_KEY,
            hook_brief=hook_brief,
            voice_samples=voice_samples,
            issues=draft_warnings,
            notebook_context=final_context,
        )

        polished = telegram_team.clean_human_surface(topic, polished)
        await msg.reply_text(
            "Игорь — один раз проверяю, ведёт ли текст от момента к ясному выводу. "
            "Нового редакционного круга не будет..."
        )
        structure_audit = await _run_blocking(
            telegram_team.audit_final_structure,
            topic,
            polished,
            GEMINI_API_KEY,
            hook_brief=hook_brief,
            notebook_context=notebook_contexts.for_agents("editor"),
        )
        assembly_blockers = list(dict.fromkeys(
            telegram_team.validate_post(polished)
            + telegram_team.blocking_quality_warnings(polished)
            + telegram_team.structural_warnings(topic, polished)
        ))
        correction_issues = [
            issue for issue in assembly_blockers if "длиннее 1900" not in issue
        ]
        if not structure_audit["accepted"]:
            correction_issues.append(structure_audit["review"])

        if correction_issues:
            await msg.reply_text(
                "Финальный аудит нашёл конкретный дефект конструкции или смысла. "
                "Маша исправляет его один раз; новых авторов и вариантов не будет..."
            )
            polished = await _run_blocking(
                telegram_team.assemble_final,
                topic,
                strategy_output,
                polished,
                editorial["review"],
                voice_notes,
                GEMINI_API_KEY,
                hook_brief=hook_brief,
                voice_samples=voice_samples,
                issues=correction_issues,
                notebook_context=final_context,
            )
            polished = telegram_team.clean_human_surface(topic, polished)

        if len(polished.strip()) > 1900:
            await msg.reply_text(
                "Света — текст вышел за лимит. Сокращаю автоматически без смены "
                "темы и без нового редакционного круга..."
            )
            length_cleanup_issues = list(dict.fromkeys(
                telegram_team.blocking_quality_warnings(polished)
                + telegram_team.structural_warnings(topic, polished)
            ))
            fitted = await _run_blocking(
                telegram_team.fit_length,
                topic,
                polished,
                GEMINI_API_KEY,
                issues=length_cleanup_issues,
            )
            fitted = telegram_team.clean_human_surface(topic, fitted)
            if len(fitted.strip()) <= 1900:
                polished = fitted
            else:
                selected_surface = telegram_team.clean_human_surface(
                    topic, selected
                )
                selected_is_safe = not (
                    telegram_team.validate_post(selected_surface)
                    + telegram_team.blocking_quality_warnings(selected_surface)
                    + telegram_team.structural_warnings(topic, selected_surface)
                )
                polished = (
                    selected_surface
                    if selected_is_safe
                    else telegram_team.enforce_length(fitted)
                )

        polished = telegram_team.clean_human_surface(topic, polished)
        delivery_issues = list(dict.fromkeys(
            telegram_team.validate_post(polished)
            + telegram_team.blocking_quality_warnings(polished)
            + telegram_team.structural_warnings(topic, polished)
        ))
        if delivery_issues:
            await msg.reply_text(
                "Света — после сокращения остался формальный дефект. "
                "Выполняю одну техническую очистку без нового редакционного круга..."
            )
            polished = await _run_blocking(
                telegram_team.fit_length,
                topic,
                polished,
                GEMINI_API_KEY,
                issues=delivery_issues,
            )
            polished = telegram_team.clean_human_surface(topic, polished)
            if len(polished) > 1900:
                polished = telegram_team.enforce_length(polished)

        delivery_blockers = list(dict.fromkeys(
            telegram_team.validate_post(polished)
            + telegram_team.blocking_quality_warnings(polished)
            + telegram_team.blocking_structural_warnings(topic, polished)
        ))
        if delivery_blockers:
            await msg.reply_text(
                "Останавливаюсь только из-за смыслового, фактического или брендового "
                "риска — не из-за вкусовой редактуры: "
                + "; ".join(delivery_blockers) + "."
            )
            return

        style_notes = list(dict.fromkeys(
            telegram_team.quality_warnings(polished)
            + telegram_team.structural_warnings(topic, polished)
        ))
        if style_notes:
            logger.info(
                "Non-blocking style notes after bounded assembly: %s",
                "; ".join(style_notes),
            )

        memory_utils.register_published(
            topic,
            angle=strategy_output[:300],
            formats=["telegram_post"],
        )

        if feedback:
            for agent_id in ["analyst", "strategist", "copywriter", "editor", "humanizer"]:
                mem = memory_utils.load(agent_id)
                memory_utils.add_feedback(mem, "Дмитрий", feedback, topic)
                memory_utils.save(agent_id, mem)

        user_data["last_post_topic"] = topic
        user_data["last_analysis"] = research_note
        user_data["last_strategy"] = strategy_output
        user_data["last_hook_brief"] = hook_brief
        user_data["last_commercial_blueprint"] = commercial_blueprint
        user_data["last_final_tg"] = polished
        user_data["last_final_ig_post"] = ""
        user_data["last_pipeline_mode"] = "post"
        user_data["pending_ig_sections"] = {}
        user_data["waiting_feedback"] = False
        _persist_session(msg.chat_id, user_data)

        await msg.reply_text("━━━━━━━━━━━━━━━━━━━\nTelegram-пост готов\n━━━━━━━━━━━━━━━━━━━")
        await _send(msg, polished)
        await msg.reply_text(
            "Если нужна правка — нажми кнопку и напиши, что изменить. Смысловой угол сохранится.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Доработать пост", callback_data="revise")
            ]]),
        )
    except Exception as e:
        logger.exception("Ошибка в компактном Telegram pipeline")
        if "503" in str(e) or "UNAVAILABLE" in str(e) or "overloaded" in str(e).lower():
            await msg.reply_text("Gemini временно перегружен. Попробуй повторить тему через пару минут.")
        else:
            await msg.reply_text(f"Ошибка: {e}")


async def _run_pack(msg: Message, topic: str, user_data: dict, feedback: str = None):
    """Legacy full Telegram + Instagram content pack."""
    chat_id = msg.chat_id
    if chat_id in _active_pipelines:
        await msg.reply_text("Команда уже работает над предыдущим материалом. Дождись завершения.")
        return
    _active_pipelines.add(chat_id)
    try:
        await _run_pack_inner(msg, topic, user_data, feedback, "all")
    finally:
        _active_pipelines.discard(chat_id)


async def _run_pack_inner(msg: Message, topic: str, user_data: dict, feedback: str = None, delivery_filter: str = "all"):
    route = team_registry.route_for(topic)
    # Маршрутизация правок: тональная правка («теплее», «живее», «проще», «ближе», «меньше
    # пафоса») идёт сразу к Даше и на быструю проверку редактора — минуя Нину, Артёма, Машу
    # и Катю целиком. Раньше даже такая правка гоняла всю команду заново.
    tonal_revision = bool(
        feedback and _is_tonal_feedback(feedback)
        and user_data.get("last_post_topic") == topic
        and user_data.get("last_final_tg") and user_data.get("last_final_ig_post")
        and user_data.get("last_analysis") and user_data.get("last_strategy")
    )

    if tonal_revision:
        await msg.reply_text(
            f"Это похоже на правку тона, а не смысла — передаю сразу Даше, "
            f"минуя Нину, Артёма, Машу и Катю.\n\nПравка: {feedback}"
        )
        try:
            await msg.reply_text(f"{ROLES['Даша']} — тональная переработка текста...")
            new_tg = await _run_blocking(
                humanizer.deep_tonal_rework, user_data["last_final_tg"], topic, feedback, GEMINI_API_KEY
            )
            new_ig = await _run_blocking(
                humanizer.deep_tonal_rework, user_data["last_final_ig_post"], topic, feedback, GEMINI_API_KEY
            )

            found_tg = humanizer.find_denylisted(new_tg)
            if found_tg:
                new_tg = await _run_blocking(humanizer.force_remove_cliches, new_tg, found_tg, topic, GEMINI_API_KEY)
            found_ig = humanizer.find_denylisted(new_ig)
            if found_ig:
                new_ig = await _run_blocking(humanizer.force_remove_cliches, new_ig, found_ig, topic, GEMINI_API_KEY)

            if humanizer.has_forbidden_punctuation(new_tg):
                new_tg = await _run_blocking(humanizer.fix_punctuation_style, new_tg, topic, GEMINI_API_KEY)
            if humanizer.has_forbidden_punctuation(new_ig):
                new_ig = await _run_blocking(humanizer.fix_punctuation_style, new_ig, topic, GEMINI_API_KEY)

            brand_violations = (
                humanizer.find_brand_boundary_violations(new_tg)
                + humanizer.find_brand_boundary_violations(new_ig)
            )
            if brand_violations:
                await msg.reply_text(
                    "Останавливаюсь: тональная правка сохранила запрещённое терапевтическое позиционирование "
                    f"({', '.join(dict.fromkeys(brand_violations))}). Текст не отправлен."
                )
                return

            if not _looks_like_real_post(new_tg) or not _looks_like_real_post(new_ig):
                await msg.reply_text(
                    "Что-то пошло не так при тональной переработке — результат не похож на готовый "
                    "текст. Попробуй ещё раз или создай пост заново."
                )
                return

            await msg.reply_text(f"{ROLES['Игорь']} и {ROLES['Лена']} — проверяю после переработки...")
            r_check_tg = await _run_blocking(editor.quick_check, topic, user_data["last_strategy"], new_tg, GEMINI_API_KEY)
            r_check_ig = await _run_blocking(instagram_editor.quick_check, topic, user_data["last_strategy"], new_ig, GEMINI_API_KEY)

            if not r_check_tg["accepted"]:
                await _send(msg, f"{ROLES['Игорь']}: после переработки есть замечания:\n\n{r_check_tg['review']}")
            if not r_check_ig["accepted"]:
                await _send(msg, f"{ROLES['Лена']}: после переработки есть замечания:\n\n{r_check_ig['review']}")

            await msg.reply_text("━━━━━━━━━━━━━━━━━━━\nТональная переработка готова\n━━━━━━━━━━━━━━━━━━━")
            await _send(msg, f"TELEGRAM-ТЕКСТ (от {ROLES['Даша']}):\n\n{new_tg}")
            await _send(msg, f"INSTAGRAM — ПОСТ (от {ROLES['Даша']}):\n\n{new_ig}")

            user_data["last_final_tg"] = new_tg
            user_data["last_final_ig_post"] = new_ig
            user_data["waiting_feedback"] = False
            _persist_session(msg.chat_id, user_data)
        except Exception as e:
            logger.exception("Ошибка в тональной переработке")
            await msg.reply_text(f"Ошибка при тональной переработке: {e}")
        return

    if feedback:
        await msg.reply_text(
            f"Команда дорабатывает пост по теме:\n«{topic}»\n\nПравки: {feedback}\n\nЗаймёт 2–4 минуты..."
        )
    else:
        await msg.reply_text(
            f"Команда берётся за тему:\n«{topic}»\n\nАгенты работают последовательно, займёт 2–4 минуты..."
        )

    # Доработка по фидбеку от Дмитрия — это правка уже одобренного поста (тон, теплота,
    # конкретная формулировка), а не запрос на новую тему. Раньше фидбек всё равно гнал
    # Нину и Артёма с нуля — а поскольку они обязаны не повторять недавний аспект/образ/
    # схему, второй прогон на ту же тему уводил в совершенно другой угол вместо того чтобы
    # просто сделать текст теплее. Если это правка того же поста — переиспользуем уже
    # одобренные анализ и стратегию и правим только тексты.
    reuse_previous = bool(
        feedback and user_data.get("last_post_topic") == topic
        and user_data.get("last_analysis") and user_data.get("last_strategy")
    )

    try:
        await msg.reply_text(
            f"NotebookLM — собираю маршрут «{team_registry.MODE_LABELS[route.mode]}» "
            "для полного пакета..."
        )
        try:
            notebook_contexts = await _run_blocking(
                notebook_live.build_topic_context,
                topic,
                route.mode,
            )
        except notebook_live.NotebookLiveError as exc:
            await msg.reply_text(
                "Останавливаюсь до написания пакета: обязательный маршрут "
                f"NotebookLM не прошёл.\n\nПричина: {exc}"
            )
            return

        commercial_blueprint = (
            user_data.get("last_commercial_blueprint", "")
            if reuse_previous
            else ""
        )
        if reuse_previous:
            await msg.reply_text(
                "Переиспользую уже одобренные анализ Нины и стратегию Артёма — правлю сам текст, "
                "не меняю тему заново."
            )
            r_analyst = {"analysis": user_data["last_analysis"]}
            r_strategist = {"strategy": user_data["last_strategy"]}
        else:
            await msg.reply_text("Нина Соколова — анализирую аудиторию...")
            r_analyst = await _run_blocking(
                analyst.run,
                topic,
                GEMINI_API_KEY,
                notebook_context=notebook_contexts.for_agents("researcher"),
            )
            await _send(msg, f"{ROLES['Нина']}:\n\n{r_analyst['analysis']}")

            if route.mode == team_registry.COMMERCIAL:
                await msg.reply_text(
                    "Виктор Самойлов — строю коммерческий каркас до текстов..."
                )
                r_offer_blueprint = await _run_blocking(
                    offer_architect.run,
                    topic,
                    r_analyst["analysis"],
                    GEMINI_API_KEY,
                    notebook_context=notebook_contexts.for_agents(
                        "offer_architect"
                    ),
                )
                commercial_blueprint = r_offer_blueprint["offer"]

            await msg.reply_text("Артём Волков — строю стратегию...")
            strategist_notebooks = notebook_contexts.for_agents("strategist")
            if commercial_blueprint:
                strategist_notebooks += (
                    "\n\nКОММЕРЧЕСКИЙ КАРКАС ВИКТОРА:\n"
                    + commercial_blueprint
                )
            r_strategist = await _run_blocking(
                strategist.run,
                topic,
                r_analyst["analysis"],
                GEMINI_API_KEY,
                notebook_context=strategist_notebooks,
            )
            await _send(msg, f"{ROLES['Артём']}:\n\n{r_strategist['strategy']}")

            await msg.reply_text(f"{ROLES['Олег']} — ранняя проверка стратегии на повтор архитектуры, до того как Маша и Катя начнут писать...")
            r_early_marketer = await _run_blocking(
                marketer.run_early, topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY
            )
            if r_early_marketer.get("critical_repeat"):
                await _send(msg, f"{ROLES['Олег']} (ранняя проверка):\n\n{r_early_marketer['marketing']}")
                await msg.reply_text(
                    "Олег на раннем этапе нашёл критический повтор архитектуры/крючка/CTA относительно "
                    "уже проверенных материалов — останавливаюсь до того, как Маша и Катя начнут писать. "
                    "Нужно твоё решение: принять повтор осознанно или запросить у Артёма новую стратегию."
                )
                return

        if feedback:
            await msg.reply_text(
                f"Маша Лебедева — учитываю правки, переписываю Telegram...\n"
                f"Катя Миронова — переделываю Instagram с учётом замечаний..."
            )
        else:
            await msg.reply_text(
                "Маша Лебедева — пишу два варианта для Telegram...\n"
                "Катя Миронова — параллельно собираю Instagram-пакет..."
            )

        loop = asyncio.get_running_loop()
        try:
            r_copy, r_insta = await asyncio.wait_for(
                asyncio.gather(
                    loop.run_in_executor(None, lambda: copywriter.run(
                        topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                        editor_feedback=feedback, iteration=2 if feedback else 1,
                        notebook_context=notebook_contexts.for_agents("writer"),
                    )),
                    loop.run_in_executor(None, lambda: instagram_writer.run(
                        topic, r_analyst["analysis"], r_strategist["strategy"], "", GEMINI_API_KEY,
                        editor_feedback=feedback, iteration=2 if feedback else 1
                    ))
                ),
                timeout=180
            )
        except asyncio.TimeoutError:
            raise TimeoutError("Запрос к Gemini не ответил за 3 минуты (Маша/Катя) — вероятно, временный сбой сети. Попробуй ещё раз.")
        await msg.reply_text(
            f"{ROLES['Маша']} — готово, передаю Игорю на проверку.\n"
            f"{ROLES['Катя']} — пакет готов, Лена смотри."
        )

        strategy_output = r_strategist["strategy"]
        strategy_revised = False
        # Значения для реестра "используемое" пишутся в память ТОЛЬКО при подтверждённой
        # публикации (см. register_published в конце пайплайна) — здесь просто держим
        # актуальные на данный момент значения, обновляя при каждом реальном пересмотре.
        strategy_image = r_strategist.get("central_image", "")
        strategy_scheme = r_strategist.get("scheme", "")
        strategy_angle = r_strategist.get("angle", "")

        async def _revise_strategy(feedback_source: str, feedback_text: str):
            """Игорь или Лена отменили саму стратегию, а не текст — раньше пайплайн
            не умел на это реагировать и просто просил Машу/Катю переписать тем же
            (уже забракованным) ТЗ. Здесь Артём реально пересматривает угол, и обе
            платформы пересобираются заново под новый ТЗ, чтобы не разойтись."""
            nonlocal strategy_output, strategy_revised, strategy_image, strategy_scheme, strategy_angle
            await _send(msg, f"{feedback_source}: проблема не в тексте, а в самой стратегии:\n\n{feedback_text}")
            await msg.reply_text(f"{ROLES['Артём']}: пересматриваю угол по этому замечанию...")
            r_strategist2 = await _run_blocking(
                strategist.run,
                topic,
                r_analyst["analysis"],
                GEMINI_API_KEY,
                feedback=feedback_text,
                notebook_context=notebook_contexts.for_agents("strategist"),
            )
            strategy_output = r_strategist2["strategy"]
            strategy_image = r_strategist2.get("central_image", "")
            strategy_scheme = r_strategist2.get("scheme", "")
            strategy_angle = r_strategist2.get("angle", "")
            strategy_revised = True

            r_early_marketer2 = await _run_blocking(
                marketer.run_early, topic, r_analyst["analysis"], strategy_output, GEMINI_API_KEY
            )
            if r_early_marketer2.get("critical_repeat"):
                await _send(msg, f"{ROLES['Олег']} (ранняя проверка новой стратегии):\n\n{r_early_marketer2['marketing']}")
                await msg.reply_text(
                    "Даже пересмотренная стратегия критически повторяет архитектуру/крючок/CTA уже "
                    "проверенного материала — останавливаюсь до того, как Маша и Катя начнут писать заново. "
                    "Нужно твоё решение по теме."
                )
                raise _StopPipeline()

            await msg.reply_text(f"{ROLES['Маша']} — пишу заново по новой стратегии...\n{ROLES['Катя']} — тоже пересобираю пакет...")
            loop = asyncio.get_running_loop()
            new_copy, new_insta = await asyncio.gather(
                loop.run_in_executor(None, lambda: copywriter.run(
                    topic, r_analyst["analysis"], strategy_output, GEMINI_API_KEY,
                    iteration=2,
                    notebook_context=notebook_contexts.for_agents("writer"),
                )),
                loop.run_in_executor(None, lambda: instagram_writer.run(
                    topic, r_analyst["analysis"], strategy_output, "", GEMINI_API_KEY, iteration=2
                ))
            )
            return new_copy, new_insta

        await msg.reply_text("Игорь Орлов — читаю оба варианта Маши...")
        r_editor = await _run_blocking(
            editor.run, topic, r_analyst["analysis"], strategy_output,
            r_copy["texts"], GEMINI_API_KEY,
            notebook_context=notebook_contexts.for_agents("editor"),
        )

        # До двух автоматических пересмотров стратегии, не одного — новые более строгие
        # гейты (причинная цепочка, 2 небутафорских контрпримера, тест переноса вины) сами
        # по себе поднимают шанс, что первый пересмотр всё ещё формален. Раньше при провале
        # второй попытки (первая стратегия + одна ревизия) бот сразу останавливался и просил
        # решение у Дмитрия — теперь даём ещё один шанс до эскалации.
        MAX_STRATEGY_REVISIONS = 2
        went_through_strategy_revision = False
        strategy_revision_attempts = 0
        while r_editor.get("strategy_rejected") and strategy_revision_attempts < MAX_STRATEGY_REVISIONS:
            strategy_revision_attempts += 1
            went_through_strategy_revision = True
            r_copy, r_insta = await _revise_strategy(ROLES['Игорь'], r_editor["review"])
            r_editor = await _run_blocking(
                editor.run, topic, r_analyst["analysis"], strategy_output,
                r_copy["texts"], GEMINI_API_KEY,
                iteration=1 + strategy_revision_attempts,
                notebook_context=notebook_contexts.for_agents("editor"),
            )
            if not r_editor.get("strategy_rejected"):
                await msg.reply_text(
                    f"{ROLES['Игорь']}: с новой стратегией — принято." if r_editor["accepted"]
                    else f"{ROLES['Игорь']}: с новой стратегией текст ещё требует правки — прошу Машу доработать..."
                )

        if r_editor.get("strategy_rejected"):
            await _send(msg, f"{ROLES['Игорь']}: даже после {MAX_STRATEGY_REVISIONS} пересмотров стратегии не проходит:\n\n{r_editor['review']}")
            await msg.reply_text(
                f"Команда не смогла найти рабочую стратегию для Telegram-текста за {MAX_STRATEGY_REVISIONS + 1} попытки. "
                "Нужно твоё решение по теме."
            )
            return

        if not r_editor["accepted"]:
            await _send(msg, f"{ROLES['Игорь']}: Маша, не пойдёт. Вот что не так:\n\n{r_editor['review']}\n\nПеределай.")
            await msg.reply_text(f"{ROLES['Маша']}: Поняла, исправляю...")
            r_copy2 = await _run_blocking(
                copywriter.run, topic, r_analyst["analysis"], strategy_output, GEMINI_API_KEY,
                editor_feedback=r_editor["review"], iteration=2,
                notebook_context=notebook_contexts.for_agents("writer"),
            )
            r_editor2 = await _run_blocking(
                editor.run, topic, r_analyst["analysis"], strategy_output,
                r_copy2["texts"], GEMINI_API_KEY, iteration=2,
                notebook_context=notebook_contexts.for_agents("editor"),
            )
            r_copy = r_copy2
            r_editor = r_editor2
            if r_editor2["accepted"]:
                await msg.reply_text(f"{ROLES['Игорь']}: Теперь хорошо. Причина возврата устранена и подтверждена.")
            else:
                await _send(msg, f"{ROLES['Игорь']}: после повторной правки причина возврата по существу не устранена:\n\n{r_editor2['review']}")
                await msg.reply_text(
                    "Telegram-текст второй раз подряд не проходит проверку редактора. Нужно твоё решение — "
                    "уточнить тему или задать более конкретный тезис."
                )
                return
        elif not went_through_strategy_revision:
            await msg.reply_text(f"{ROLES['Игорь']}: С первого раза хорошо. Принято.")

        final_tg = _extract_variant(r_copy["texts"], r_editor.get("chosen_variant"))
        if r_editor.get("chosen_variant"):
            await msg.reply_text(f"Игорь выбрал вариант {r_editor['chosen_variant']} для публикации.")

        await msg.reply_text("Лена Волкова — проверяю Instagram-пакет Кати...")
        r_ig_ed = await _run_blocking(
            instagram_editor.run, topic, r_analyst["analysis"], strategy_output,
            r_insta["texts"], GEMINI_API_KEY
        )

        if r_ig_ed.get("strategy_rejected") and not strategy_revised:
            # Лена поймала то, что Игорь мог пропустить (или до него ещё не дошли) —
            # пересматриваем один раз, тем же путём, и синхронизируем обе платформы
            r_copy, r_insta = await _revise_strategy(ROLES['Лена'], r_ig_ed["review"])
            r_editor = await _run_blocking(
                editor.run, topic, r_analyst["analysis"], strategy_output,
                r_copy["texts"], GEMINI_API_KEY, iteration=3,
                notebook_context=notebook_contexts.for_agents("editor"),
            )
            if not r_editor["accepted"]:
                await _send(msg, f"{ROLES['Игорь']}: перепроверил Telegram под новую стратегию — есть замечания:\n\n{r_editor['review']}")
                await msg.reply_text(f"{ROLES['Маша']}: поняла, исправляю ещё раз...")
                r_copy2 = await _run_blocking(
                    copywriter.run, topic, r_analyst["analysis"], strategy_output, GEMINI_API_KEY,
                    editor_feedback=r_editor["review"], iteration=3,
                    notebook_context=notebook_contexts.for_agents("writer"),
                )
                r_editor2 = await _run_blocking(
                    editor.run, topic, r_analyst["analysis"], strategy_output,
                    r_copy2["texts"], GEMINI_API_KEY, iteration=3,
                    notebook_context=notebook_contexts.for_agents("editor"),
                )
                r_copy = r_copy2
                r_editor = r_editor2
                if r_editor2["accepted"]:
                    await msg.reply_text(f"{ROLES['Игорь']}: теперь хорошо. Причина возврата устранена и подтверждена.")
                else:
                    await _send(msg, f"{ROLES['Игорь']}: причина возврата по существу не устранена:\n\n{r_editor2['review']}")
                    await msg.reply_text(
                        "Telegram-текст не проходит проверку редактора после пересмотра стратегии. Нужно твоё решение."
                    )
                    return
            else:
                await msg.reply_text(f"{ROLES['Игорь']}: перепроверил Telegram под новую стратегию — принято.")

            final_tg = _extract_variant(r_copy["texts"], r_editor.get("chosen_variant"))
            r_ig_ed = await _run_blocking(
                instagram_editor.run, topic, r_analyst["analysis"], strategy_output,
                r_insta["texts"], GEMINI_API_KEY, iteration=2
            )

        final_ig = r_insta["texts"]

        if r_ig_ed.get("strategy_rejected"):
            # Уже пересматривали стратегию один раз и её всё ещё отклоняют — дальше
            # автоматика не пытается угадать сама, решение за человеком
            await _send(msg, f"{ROLES['Лена']}: даже после пересмотра стратегии пакет не проходит:\n\n{r_ig_ed['review']}")
            await msg.reply_text(
                "Команда не смогла найти рабочую стратегию для этой темы за две попытки. "
                "Нужно твоё решение — например, задать более конкретный аспект темы или тезис от себя."
            )
            return

        if not r_ig_ed["accepted"]:
            await _send(msg, f"{ROLES['Лена']}: Катя, нужно переделать.\n\n{r_ig_ed['review']}")
            await msg.reply_text(f"{ROLES['Катя']}: Хорошо, сейчас исправлю...")
            r_insta2 = await _run_blocking(
                instagram_writer.run, topic, r_analyst["analysis"], strategy_output,
                "", GEMINI_API_KEY,
                editor_feedback=r_ig_ed["review"], iteration=2
            )
            r_ig_ed2 = await _run_blocking(
                instagram_editor.run, topic, r_analyst["analysis"], strategy_output,
                r_insta2["texts"], GEMINI_API_KEY, iteration=2
            )
            final_ig = r_insta2["texts"]
            if r_ig_ed2.get("strategy_rejected"):
                await _send(msg, f"{ROLES['Лена']}: Катя не смогла переписать в рамках этого ТЗ:\n\n{r_ig_ed2['review']}")
                await msg.reply_text(
                    "Кате нужно новое ТЗ от Артёма, а не ещё одна попытка в рамках старого. Нужно твоё решение по теме."
                )
                return
            if not _looks_like_real_post(r_insta2["texts"]):
                snippet = r_insta2["texts"].strip()[:400]
                await msg.reply_text(
                    f"Что-то пошло не так у Кати на второй попытке — вот что реально вернулось "
                    f"(похоже не на пост, а на служебный ответ):\n\n{snippet}"
                )
                await msg.reply_text("Останавливаюсь, чтобы не отправить тебе брак. Попробуй запустить тему заново.")
                return
            if r_ig_ed2["accepted"]:
                await msg.reply_text(f"{ROLES['Лена']}: Теперь норм. Причина возврата устранена и подтверждена.")
            else:
                await _send(msg, f"{ROLES['Лена']}: после повторной правки причина возврата по существу не устранена:\n\n{r_ig_ed2['review']}")
                await msg.reply_text(
                    "Instagram-пакет второй раз подряд не проходит проверку редактора. Нужно твоё решение."
                )
                return
        else:
            await msg.reply_text(f"{ROLES['Лена']}: Всё отлично, без правок.")

        if not _looks_like_real_post(final_ig) or not _looks_like_real_post(final_tg):
            bad_label = "Instagram" if not _looks_like_real_post(final_ig) else "Telegram"
            bad_text = final_ig if not _looks_like_real_post(final_ig) else final_tg
            await msg.reply_text(
                f"Что-то пошло не так: финальный текст для {bad_label} выглядит как внутренняя переписка "
                f"команды, а не готовый пост. Вот что реально получилось:\n\n{bad_text.strip()[:400]}"
            )
            await msg.reply_text("Останавливаюсь, чтобы не отправить тебе брак. Попробуй запустить тему заново.")
            return

        await msg.reply_text("Даша Козлова — убираю AI-паттерны, добавляю живость...")
        final_ig_sections = dict(_split_instagram_sections(final_ig))
        ig_post_raw = final_ig_sections.pop("ПОСТ", final_ig)
        ig_other_sections_raw = final_ig_sections  # СТОРИС / КАРУСЕЛЬ / REELS
        r_human = await _run_blocking(
            humanizer.run,
            topic,
            final_tg,
            ig_post_raw,
            GEMINI_API_KEY,
            notebook_context=notebook_contexts.for_agents("voice"),
        )

        ig_other_sections = {}
        for label, content in ig_other_sections_raw.items():
            ig_other_sections[label] = await _run_blocking(
                humanizer.humanize_structured_section, label, content, topic, GEMINI_API_KEY
            )

        TG_MAX_LEN = 1800
        if len(r_human["telegram_humanized"]) > TG_MAX_LEN:
            await msg.reply_text(
                f"{ROLES['Даша']}: текст вышел за рамки длины ({len(r_human['telegram_humanized'])} символов) — сокращаю..."
            )
            r_human["telegram_humanized"] = await _run_blocking(
                humanizer.trim_to_length, r_human["telegram_humanized"], TG_MAX_LEN, topic, GEMINI_API_KEY
            )

        for key in ("telegram_humanized", "instagram_humanized"):
            found = humanizer.find_denylisted(r_human[key])
            if found:
                await msg.reply_text(
                    f"{ROLES['Даша']}: нашла запрещённые штампы ({', '.join(found)}) — переписываю эти места..."
                )
                r_human[key] = await _run_blocking(
                    humanizer.force_remove_cliches, r_human[key], found, topic, GEMINI_API_KEY
                )
            if humanizer.has_forbidden_punctuation(r_human[key]):
                r_human[key] = await _run_blocking(
                    humanizer.fix_punctuation_style, r_human[key], topic, GEMINI_API_KEY
                )

        ig_post_content = r_human["instagram_humanized"]
        full_ig_text = ig_post_content + "\n\n" + "\n\n".join(
            f"{label}:\n{content}" for label, content in ig_other_sections.items()
        )

        brand_violations = (
            humanizer.find_brand_boundary_violations(r_human["telegram_humanized"])
            + humanizer.find_brand_boundary_violations(full_ig_text)
        )
        if brand_violations:
            await msg.reply_text(
                "Останавливаюсь: после всех правок в пакете осталось запрещённое терапевтическое "
                f"позиционирование ({', '.join(dict.fromkeys(brand_violations))}). Пакет не отправлен."
            )
            return

        # Шлюз 6 — повторная смысловая проверка ПОСЛЕ очеловечивания. Даша могла случайно
        # вернуть категоричность, новую метафору или перенос вины, работая над живостью —
        # редакторы уже одобрили смысл ДО очеловечивания, но не после. Без этого шага
        # ошибочная мысль может выйти в публикацию более убедительной и эмоциональной,
        # чем была на входе к Даше.
        await msg.reply_text(f"{ROLES['Игорь']} и {ROLES['Лена']} — повторная смысловая проверка после очеловечивания Даши...")
        r_recheck_tg = await _run_blocking(
            editor.quick_check, topic, strategy_output, r_human["telegram_humanized"], GEMINI_API_KEY
        )
        r_recheck_ig = await _run_blocking(
            instagram_editor.quick_check, topic, strategy_output, ig_post_content, GEMINI_API_KEY
        )
        if not r_recheck_tg["accepted"] or not r_recheck_ig["accepted"]:
            if not r_recheck_tg["accepted"]:
                await _send(msg, f"{ROLES['Игорь']} (после очеловечивания):\n\n{r_recheck_tg['review']}")
            if not r_recheck_ig["accepted"]:
                await _send(msg, f"{ROLES['Лена']} (после очеловечивания):\n\n{r_recheck_ig['review']}")
            await msg.reply_text(
                "Очеловечивание Даши вернуло категоричность, новую метафору или перенос вины, которых "
                "не было в одобренном варианте — останавливаюсь перед публикацией. Нужно твоё решение."
            )
            return

        await msg.reply_text("Олег Савин — оцениваю виральный и коммерческий потенциал готового текста...")
        r_marketer = await _run_blocking(
            marketer.run, topic, r_analyst["analysis"], strategy_output, GEMINI_API_KEY,
            final_content=f"TELEGRAM:\n{r_human['telegram_humanized']}\n\nINSTAGRAM:\n{full_ig_text}"
        )
        await _send(msg, f"{ROLES['Олег']}:\n\n{r_marketer['marketing']}")

        if r_marketer.get("critical_repeat"):
            await msg.reply_text(
                "Олег обнаружил точное совпадение схемы сюжета/образа/CTA с уже проверенным "
                "материалом (см. его разбор выше) — публикация приостановлена. Нужно твоё решение: "
                "либо принять повтор осознанно, либо запросить у Артёма другую стратегию."
            )
            return

        await msg.reply_text("Света Громова — финальная проверка и подготовка к публикации...")
        r_pub = await _run_blocking(
            publisher.run, topic,
            r_human["telegram_humanized"],
            full_ig_text,
            GEMINI_API_KEY,
            strategy_output=strategy_output
        )

        remaining_sections = ig_other_sections

        # Единственное место во всём пайплайне, где угол/образ/схема/форматы/CTA реально
        # попадают в общий реестр "used_X" команды — материал только что прошёл все гейты
        # и уходит в публикацию. Черновики и отклонённые попытки этот реестр не трогают.
        memory_utils.register_published(
            topic,
            angle=r_analyst.get("chosen_aspect", "") or strategy_angle,
            central_image=strategy_image,
            scheme=strategy_scheme,
            formats=r_copy.get("formats", []),
            ctas=r_copy.get("ctas", []),
        )

        await msg.reply_text("━━━━━━━━━━━━━━━━━━━\nКоманда сдала работу\n━━━━━━━━━━━━━━━━━━━")
        await _send(msg, f"TELEGRAM-ТЕКСТ (от {ROLES['Даша']}):\n\n{r_human['telegram_humanized']}")
        await _send(msg, f"INSTAGRAM — ПОСТ (от {ROLES['Даша']}):\n\n{ig_post_content}")

        user_data["pending_ig_sections"] = remaining_sections

        if feedback:
            for agent_id in ["analyst", "strategist", "copywriter", "instagram_writer", "humanizer"]:
                mem = memory_utils.load(agent_id)
                memory_utils.add_feedback(mem, "Дмитрий", feedback, topic)
                memory_utils.save(agent_id, mem)

        user_data["last_post_topic"] = topic
        user_data["last_analysis"] = r_analyst["analysis"]
        user_data["last_strategy"] = strategy_output
        user_data["last_commercial_blueprint"] = commercial_blueprint
        user_data["last_final_tg"] = r_human["telegram_humanized"]
        user_data["last_final_ig_post"] = ig_post_content
        user_data["last_pipeline_mode"] = "pack"
        user_data["waiting_feedback"] = False
        _persist_session(msg.chat_id, user_data)

        keyboard = []
        extra_buttons = []
        if "СТОРИС" in remaining_sections:
            extra_buttons.append(InlineKeyboardButton("📖 Сторис", callback_data="igshow:СТОРИС"))
        if "КАРУСЕЛЬ" in remaining_sections:
            extra_buttons.append(InlineKeyboardButton("🖼 Карусель", callback_data="igshow:КАРУСЕЛЬ"))
        if "REELS" in remaining_sections:
            extra_buttons.append(InlineKeyboardButton("🎬 Reels", callback_data="igshow:REELS"))
        if extra_buttons:
            keyboard.append(extra_buttons)
        keyboard.append([InlineKeyboardButton("Доработать пост", callback_data="revise")])

        extra_note = " Карусель, сторис и Reels уже готовы — показать их кнопкой ниже." if extra_buttons else ""
        await msg.reply_text(
            f"Telegram и Instagram-пост готовы.{extra_note}\n"
            "Если что-то не так — нажми «Доработать пост» и отправь голосовое или текст с правками.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except _StopPipeline:
        pass
    except Exception as e:
        logger.exception("Ошибка в _run_post")
        if "503" in str(e) or "UNAVAILABLE" in str(e) or "overloaded" in str(e).lower():
            await msg.reply_text(
                "Gemini сейчас перегружен и не отвечает (это на стороне Google, не у нас). "
                "Подожди пару минут и пришли тему ещё раз — обычно само проходит."
            )
        else:
            await msg.reply_text(f"Ошибка: {e}")


async def _run_offer(msg: Message, product: str):
    await msg.reply_text(
        f"Коммерческий маршрут: Нина → Виктор → этический контроль:\n"
        f"«{product}»\n\nСначала запрашиваю профильные NotebookLM-блокноты."
    )
    try:
        try:
            notebook_contexts = await _run_blocking(
                notebook_live.build_topic_context,
                product,
                team_registry.COMMERCIAL,
            )
        except notebook_live.NotebookLiveError as exc:
            await msg.reply_text(
                "Останавливаюсь до оффера: обязательный коммерческий маршрут "
                f"NotebookLM не прошёл.\n\nПричина: {exc}"
            )
            return

        await msg.reply_text(
            "NotebookLM — коммерческий маршрут собран: "
            + ", ".join(notebook_contexts.selected_notebooks)
        )
        await msg.reply_text("Нина Соколова — анализирую аудиторию под этот продукт...")
        r_analyst = await _run_blocking(
            analyst.run,
            product,
            GEMINI_API_KEY,
            notebook_context=notebook_contexts.for_agents("researcher"),
        )
        await msg.reply_text(f"{ROLES['Нина']}: Готово. Виктор, передаю анализ.")

        await msg.reply_text("Виктор Самойлов — строю оффер по Хормози...")
        r_offer = await _run_blocking(
            offer_architect.run,
            product,
            r_analyst["analysis"],
            GEMINI_API_KEY,
            notebook_context=notebook_contexts.for_agents("offer_architect"),
        )

        await msg.reply_text(f"━━━━━━━━━━━━━━━━━━━\n{ROLES['Виктор']} — сдал оффер\n━━━━━━━━━━━━━━━━━━━")
        await _send(msg, f"ОФФЕР — {product.upper()}\n\n{r_offer['offer']}")

    except Exception as e:
        logger.exception("Ошибка в _run_offer")
        await msg.reply_text(f"Ошибка: {e}")


async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() if context.args else ""
    if not topic:
        await update.message.reply_text("Укажи тему после команды.\nПример: /post практика Танец Души")
        return
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return
    await _run_post(update.message, topic, context.user_data)


async def cmd_pack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() if context.args else ""
    if not topic:
        await update.message.reply_text("Укажи тему после команды.\nПример: /pack практика Танец Души")
        return
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return
    await _run_pack(update.message, topic, context.user_data)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("last_pipeline_mode") or "ещё не запускался"
    busy = "да" if update.effective_chat.id in _active_pipelines else "нет"
    await update.message.reply_text(
        "Состояние SMM-команды:\n"
        f"• Gemini: {'подключён' if GEMINI_API_KEY else 'не настроен'}\n"
        f"• Gemini Notebook: {notebook_live.status_line()}\n"
        f"• единый реестр: {team_registry.registry_status()}\n"
        f"• Instagram Direct: {instagram_messaging.status_line()}\n"
        "• /post: один автор финала, только Telegram\n"
        "• /pack: полный Telegram + Instagram\n"
        f"• последний режим: {mode}\n"
        f"• команда сейчас занята: {busy}"
    )


async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send(update.message, team_registry.team_manifest())


async def cmd_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request_text = " ".join(context.args).strip() if context.args else ""
    if not request_text:
        await update.message.reply_text(
            "Напиши задачу после команды.\n"
            "Пример: /route пост о страхе важного разговора\n"
            "Пример: /route оффер на групповую программу"
        )
        return
    await update.message.reply_text(team_registry.route_summary(request_text))


async def cmd_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = " ".join(context.args).strip() if context.args else ""
    if not product:
        await update.message.reply_text("Укажи продукт: /offer Личная сессия с Дмитрием")
        return
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return
    await _run_offer(update.message, product)


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    mode = "week"
    events = None
    if args:
        first = args[0].lower()
        if first in ("month", "месяц", "месячный"):
            mode = "month"
            events = " ".join(args[1:]).strip() or None
        elif first in ("campaign", "кампания"):
            mode = "campaign"
            events = " ".join(args[1:]).strip() or None
        else:
            events = " ".join(args).strip() or None

    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    mode_label = {"week": "недельный", "month": "месячный", "campaign": "под кампанию"}.get(mode, "недельный")
    await update.message.reply_text(
        f"Соня Белова — составляю {mode_label} контент-план"
        + (f".\nСобытия: {events}" if events else "") + "\n\nЗаймёт ~1 минуту..."
    )
    try:
        r = await _run_blocking(content_planner.run, GEMINI_API_KEY, mode=mode, events=events)
        await update.message.reply_text(f"━━━━━━━━━━━━━━━━━━━\n{ROLES['Соня']} — Контент-план\n━━━━━━━━━━━━━━━━━━━")
        await _send(update.message, r["plan"])
    except Exception as e:
        logger.exception("Ошибка в /plan")
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_community(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Миша Захаров — Менеджер комьюнити\n\n"
            "Использование:\n"
            "/community <публикация> | <комментарии>\n"
            "/community report <публикация> | <комментарии>\n"
            "/community direct <контекст> | <сообщение>\n"
            "/community help <контекст> | <комментарий для Дмитрия>"
        )
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    mode = "comments"
    raw = " ".join(args)

    if raw.startswith("report "):
        mode = "report"
        raw = raw[7:]
    elif raw.startswith("direct "):
        mode = "direct"
        raw = raw[7:]
    elif raw.startswith("help "):
        mode = "help_dmitry"
        raw = raw[5:]

    parts = raw.split("|", 1)
    task = parts[0].strip()
    extra = parts[1].strip() if len(parts) > 1 else None

    mode_labels = {
        "comments": "обрабатываю комментарии",
        "report": "составляю отчёт по реакциям",
        "direct": "готовлю ответ в директ",
        "help_dmitry": "готовлю варианты ответа для Дмитрия",
    }
    await update.message.reply_text(f"Миша — {mode_labels.get(mode, mode)}...")

    try:
        r = await _run_blocking(
            community_manager.run,
            GEMINI_API_KEY,
            task=task,
            comments=extra if mode in ("comments", "report") else None,
            direct_message=extra if mode in ("direct", "help_dmitry") else None,
            mode=mode,
        )
        await update.message.reply_text(f"━━━━━━━━━━━━━━━━━━━\n{ROLES['Миша']} — Комьюнити\n━━━━━━━━━━━━━━━━━━━")
        await _send(update.message, r["result"])
    except Exception as e:
        logger.exception("Ошибка в /community")
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Таня Серова — Аналитик комментариев и репутации\n\n"
            "Использование:\n"
            "/analytics <публикация> | <комментарии> — анализ после публикации\n"
            "/analytics weekly | <данные> — еженедельный репутационный срез\n"
            "/analytics kb | <данные> — обновление базы знаний аудитории\n"
            "/analytics alert | <описание сигнала> — разбор репутационного сигнала"
        )
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    raw = " ".join(args)
    mode = "post_report"

    if raw.startswith("weekly"):
        mode = "weekly_rep"
        raw = raw[6:].lstrip(" |").strip()
    elif raw.startswith("kb"):
        mode = "knowledge_base"
        raw = raw[2:].lstrip(" |").strip()
    elif raw.startswith("alert"):
        mode = "reputation_alert"
        raw = raw[5:].lstrip(" |").strip()

    parts = raw.split("|", 1)
    publication = parts[0].strip()
    comments = parts[1].strip() if len(parts) > 1 else None

    mode_labels = {
        "post_report": "анализирую комментарии после публикации",
        "weekly_rep": "составляю еженедельный репутационный срез",
        "knowledge_base": "обновляю базу знаний аудитории",
        "reputation_alert": "разбираю репутационный сигнал",
    }
    await update.message.reply_text(f"Таня — {mode_labels.get(mode, mode)}...")

    try:
        r = await _run_blocking(
            comment_analyst.run,
            GEMINI_API_KEY,
            mode=mode,
            publication=publication if mode == "post_report" else None,
            comments_data=comments or (raw if mode != "post_report" else None),
            reputation_data=raw if mode in ("weekly_rep", "reputation_alert") else None,
        )
        await update.message.reply_text(f"━━━━━━━━━━━━━━━━━━━\n{ROLES['Таня']} — Аналитика\n━━━━━━━━━━━━━━━━━━━")
        await _send(update.message, r["report"])
    except Exception as e:
        logger.exception("Ошибка в /analytics")
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_architect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    focus = " ".join(context.args).strip() if context.args else ""
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    await update.message.reply_text(
        f"Алекс Громов — аудит команды{f' с фокусом: «{focus}»' if focus else ''}..."
    )
    try:
        r = await _run_blocking(team_architect.run, GEMINI_API_KEY, focus=focus or None)
        await update.message.reply_text(f"━━━━━━━━━━━━━━━━━━━\n{ROLES['Алекс']} — Аудит команды\n━━━━━━━━━━━━━━━━━━━")
        await _send(update.message, r["audit"])
    except Exception as e:
        logger.exception("Ошибка в /architect")
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "SMM-команда Дмитрия Сучкова\n\n"
        "Команды:\n\n"
        "/post тема — новый компактный конвейер Telegram-поста\n"
        "Пример: /post практика Танец Души\n\n"
        "/pack тема — полный пакет Telegram + Instagram\n\n"
        "/status — состояние команды и режимов\n\n"
        "/team — кто за что отвечает и какие блокноты подключены\n"
        "/route задача — показать режим, агентов и блокноты до запуска\n\n"
        "/offer продукт — создать продающий оффер\n"
        "Пример: /offer Личная сессия с Дмитрием\n\n"
        "/architect — аудит команды\n"
        "/architect вопрос — аудит с фокусом\n\n"
        "Или просто напиши текстом или голосовым что нужно сделать.\n"
        "После готового поста нажми «Доработать пост» и отправь правки."
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан")
        return

    chat_id = update.effective_chat.id
    if _already_processed(chat_id, update.message.message_id):
        return
    _hydrate_session(chat_id, context.user_data)

    if context.user_data.get("waiting_feedback"):
        await update.message.reply_text("Получил правки голосом. Расшифровываю...")
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name
        try:
            feedback = await _transcribe_voice(tmp_path)
            context.user_data["waiting_feedback"] = False
            context.user_data["pending_feedback"] = feedback
            _persist_session(chat_id, context.user_data)
            topic = context.user_data.get("last_post_topic", "")
            keyboard = [[InlineKeyboardButton("Доработать пост", callback_data="confirm_revise")]]
            await update.message.reply_text(
                f"Твои правки:\n\n{feedback}\n\nТема: «{topic}»",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        return

    await update.message.reply_text("Получил голосовое. Расшифровываю...")
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    try:
        transcript = await _transcribe_voice(tmp_path)
        await update.message.reply_text(f"Расшифровка:\n\n{transcript}")

        if context.user_data.get("last_post_topic") and _looks_like_feedback(transcript):
            topic = context.user_data["last_post_topic"]
            context.user_data["ambiguous_feedback_text"] = transcript
            _persist_session(chat_id, context.user_data)
            keyboard = [
                [InlineKeyboardButton("✅ Это правка к посту", callback_data="fbconfirm:yes")],
                [InlineKeyboardButton("🆕 Нет, это новая тема", callback_data="fbconfirm:no")],
            ]
            await update.message.reply_text(
                f"Это правка к посту «{topic}» или новая тема?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        voice_intent = _detect_intent(transcript)
        if voice_intent == "channelstats":
            await _run_channelstats(update.message)
            return
        if voice_intent == "promptcheck":
            await _run_promptcheck(update.message)
            return

        # Сохраняем очищенную от служебной обёртки и слов-паразитов тему — полную расшифровку
        # пользователь уже увидел выше, а в пайплайн должна уйти только содержательная часть
        cleaned_topic = _clean_voice_topic(transcript)
        _store_topic(context.user_data, "voice_post", cleaned_topic)
        _store_topic(context.user_data, "voice_offer", cleaned_topic)
        keyboard = [
            [InlineKeyboardButton("Создать пост", callback_data="post:voice")],
            [InlineKeyboardButton("Создать оффер", callback_data="ofr:voice")],
        ]
        await update.message.reply_text("Что делать с этим текстом?", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.exception("Ошибка при обработке голосового")
        await update.message.reply_text(f"Не удалось расшифровать: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _detect_intent(text: str) -> str:
    """Определяет намерение пользователя: 'post', 'offer', 'channelstats', 'promptcheck' или 'unknown'."""
    t = text.lower()
    promptcheck_keywords = [
        "промпт", "проверь команду", "проверь агентов", "аудит промпт", "обнови промпт",
        "проверь, как пишут агенты", "сверь данные с тем что выдают",
    ]
    channelstats_keywords = [
        "статистик", "канал", "подписчик", "просмотр", "отчёт по кана", "отчет по кана",
    ]
    offer_keywords = ["оффер", "продающ", "предложени", "продай", "продаж"]
    post_keywords = ["пост", "текст", "напиши", "создай", "сделай", "статью", "контент"]
    if any(k in t for k in promptcheck_keywords):
        return "promptcheck"
    if any(k in t for k in channelstats_keywords):
        return "channelstats"
    if any(k in t for k in offer_keywords):
        return "offer"
    if any(k in t for k in post_keywords):
        return "post"
    return "unknown"


FEEDBACK_KEYWORDS = [
    "полегче", "посложнее", "сложн", "бомбит", "переделай", "не то", "не нравится", "плохо",
    "слишком", "убери", "поправь", "измени", "не пойдёт", "не пойдет", "не годится", "тяжело",
    "лучше бы", "хочется", "не цепляет", "скучно", "длинно", "коротко",
]
_FEEDBACK_PATTERNS = [re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)", re.IGNORECASE) for k in FEEDBACK_KEYWORDS]

NEW_TOPIC_MARKERS = [
    "давай создадим пост", "давай напишем пост", "новая тема", "другая тема", "другую тему",
    "новый пост на тему", "напиши пост про", "напиши пост о ", "создай пост про", "создай пост о ",
]
_NEW_TOPIC_PATTERNS = [re.compile(re.escape(k), re.IGNORECASE) for k in NEW_TOPIC_MARKERS]


def _looks_like_feedback(text: str) -> bool:
    """Грубая проверка: похоже ли сообщение на правку к только что сданному посту,
    а не на запрос новой темы (иначе бот по словам "пост"/"сделай" запускал новый прогон
    вместо доработки того, что уже есть). Использует границы слов, чтобы не путать
    "измени" с обычным словом "изменить" в произвольном тексте."""
    if any(p.search(text) for p in _NEW_TOPIC_PATTERNS):
        return False
    return any(p.search(text) for p in _FEEDBACK_PATTERNS)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает любое текстовое сообщение — правки или свободный запрос."""
    text = update.message.text.strip()
    if not text:
        return

    chat_id = update.effective_chat.id
    if _already_processed(chat_id, update.message.message_id):
        return
    _hydrate_session(chat_id, context.user_data)

    if (not context.user_data.get("waiting_feedback")
            and context.user_data.get("last_post_topic")
            and _looks_like_feedback(text)):
        topic = context.user_data["last_post_topic"]
        context.user_data["ambiguous_feedback_text"] = text
        _persist_session(chat_id, context.user_data)
        keyboard = [
            [InlineKeyboardButton("✅ Это правка к посту", callback_data="fbconfirm:yes")],
            [InlineKeyboardButton("🆕 Нет, это новая тема", callback_data="fbconfirm:no")],
        ]
        await update.message.reply_text(
            f"Это правка к посту «{topic}» или новая тема?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Режим ожидания правок
    if context.user_data.get("waiting_feedback"):
        topic = context.user_data.get("last_post_topic", "")
        if not topic:
            await update.message.reply_text(
                "Нет сохранённого поста для доработки. Сначала создай пост через /post или текстом."
            )
            return
        context.user_data["waiting_feedback"] = False
        context.user_data["pending_feedback"] = text
        _persist_session(chat_id, context.user_data)
        keyboard = [[InlineKeyboardButton("Доработать пост", callback_data="confirm_revise")]]
        await update.message.reply_text(
            f"Твои правки:\n\n{text}\n\nТема: «{topic}»",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Свободный запрос — определяем намерение
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    intent = _detect_intent(text)

    if intent == "promptcheck":
        await _run_promptcheck(update.message)

    elif intent == "channelstats":
        await _run_channelstats(update.message)

    elif intent == "post":
        # Убираем ключевые слова-команды из темы если они в начале
        topic = text
        for prefix in ["напиши пост на тему: ", "создай пост на тему: ", "пост на тему: ",
                        "напиши пост на тему ", "создай пост на тему ", "пост на тему ",
                        "напиши пост про ", "напиши пост о ", "создай пост про ", "создай пост о ",
                        "напиши пост ", "создай пост ", "пост про ", "пост о ", "пост "]:
            if topic.lower().startswith(prefix):
                topic = topic[len(prefix):]
                topic = topic.lstrip(" :—–-\t")
                break
        _store_topic(context.user_data, "text_post", topic)
        await update.message.reply_text(f"Запускаю пост по теме:\n«{topic}»")
        await _run_post(update.message, topic, context.user_data)

    elif intent == "offer":
        product = text
        for prefix in ["создай оффер для ", "создай оффер на ", "оффер для ", "оффер на ", "оффер "]:
            if product.lower().startswith(prefix):
                product = product[len(prefix):]
                break
        await _run_offer(update.message, product)

    else:
        # Намерение неясно — сохраняем текст и предлагаем выбор
        _store_topic(context.user_data, "text_post", text)
        _store_topic(context.user_data, "text_offer", text)
        keyboard = [
            [InlineKeyboardButton("Создать пост", callback_data="post:text")],
            [InlineKeyboardButton("Создать оффер", callback_data="ofr:text")],
        ]
        await update.message.reply_text(
            f"Понял: «{text}»\n\nЧто сделать?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    chat_id = update.effective_chat.id
    _hydrate_session(chat_id, context.user_data)

    if data.startswith("fbconfirm:"):
        choice = data[len("fbconfirm:"):]
        pending_text = context.user_data.get("ambiguous_feedback_text", "")
        if not pending_text:
            await query.edit_message_text("Не нашёл текст для обработки. Попробуй отправить сообщение ещё раз.")
            return
        context.user_data["ambiguous_feedback_text"] = ""
        if choice == "yes":
            topic = context.user_data.get("last_post_topic", "")
            await query.edit_message_text(f"Запускаю доработку поста «{topic}»...")
            if context.user_data.get("last_pipeline_mode") == "pack":
                await _run_pack(query.message, topic, context.user_data, feedback=pending_text)
            else:
                await _run_post(query.message, topic, context.user_data, feedback=pending_text)
        else:
            await query.edit_message_text(f"Запускаю пост по теме:\n«{pending_text}»")
            await _run_post(query.message, pending_text, context.user_data)
        return

    if data.startswith("post_accept:") or data.startswith("post_reject:"):
        action, draft_id = data.split(":", 1)
        target_status = "accepted" if action == "post_accept" else "rejected"
        try:
            result, record = editorial_history.decide(draft_id, chat_id, target_status)
        except editorial_history.EditorialStorageError:
            logger.exception("editorial_callback_failed action=%s draft_id=%s chat_id=%s", action, draft_id, chat_id)
            await query.edit_message_text("Хранилище временно недоступно. Нажми кнопку ещё раз позднее.")
            return
        if result == "not_found":
            logger.warning("editorial_callback_unknown action=%s draft_id=%s chat_id=%s", action, draft_id, chat_id)
            await query.edit_message_text(
                "Этот черновик не найден или был создан в старой версии. Создай новый пост командой /post."
            )
            return
        if result == "already_decided":
            await query.edit_message_text("Решение по этому тексту уже сохранено.")
            return
        context.user_data["post_revision_count"] = 0
        _persist_session(chat_id, context.user_data)
        if result == "updated" and target_status == "accepted":
            topic = record["topic"]
            try:
                memory_utils.register_published(
                    topic,
                    angle=(record.get("actual_fingerprint") or {}).get("entrance", ""),
                    formats=["telegram_post"],
                )
            except Exception:
                logger.exception(
                    "editorial_antirepeat_registry_failed draft_id=%s chat_id=%s topic=%s action=%s",
                    draft_id,
                    chat_id,
                    topic,
                    action,
                )
            else:
                logger.info(
                    "editorial_antirepeat_registry_updated draft_id=%s chat_id=%s topic=%s",
                    draft_id,
                    chat_id,
                    topic,
                )
            await query.edit_message_text(
                "✅ Текст принят и добавлен в редакционную историю. Следующий пост учтёт его форму и финал."
            )
        else:
            await query.edit_message_text("🗑 Текст отклонён. В историю принятых публикаций он не попадёт.")
        return

    if data.startswith("post_revise:"):
        draft_id = data.split(":", 1)[1]
        try:
            record = editorial_history.get_draft(draft_id, chat_id)
        except editorial_history.EditorialStorageError:
            await query.edit_message_text("Хранилище временно недоступно. Попробуй позднее.")
            return
        if not record:
            await query.edit_message_text(
                "Этот черновик не найден или был создан в старой версии. Создай новый пост командой /post."
            )
            return
        if record.get("status") != "generated" or int(record.get("revision_count", 0)) != 0:
            await query.edit_message_text("Правка для этого текста уже недоступна. Прими или отклони актуальную версию.")
            return
        revision_context = record.get("revision_context") or {}
        context.user_data["last_post_topic"] = record.get("topic", "")
        context.user_data["last_final_tg"] = record.get("text", "")
        context.user_data["last_editorial_profile"] = record.get("planned_profile") or {}
        context.user_data["last_analysis"] = revision_context.get("editorial_context", "")
        context.user_data["last_history_brief"] = revision_context.get("history_brief", "")
        context.user_data["revise_target_draft_id"] = draft_id
        context.user_data["waiting_feedback"] = True
        _persist_session(chat_id, context.user_data)
        await query.edit_message_text(
            f"Доработка поста по теме «{record.get('topic', '')}»\n\n"
            "Отправь голосовое или напиши текстом, что именно изменить."
        )
        return

    # Compatibility for non-editorial legacy modes that still show a generic revise button.
    if data == "revise":
        topic = context.user_data.get("last_post_topic", "")
        if not topic:
            await query.edit_message_text("Нет сохранённого поста. Сначала создай пост.")
            return
        context.user_data["waiting_feedback"] = True
        _persist_session(chat_id, context.user_data)
        await query.edit_message_text(
            f"Доработка поста по теме «{topic}»\n\n"
            "Отправь голосовое или напиши текстом — что именно изменить."
        )
        return

    elif data == "confirm_revise":
        topic = context.user_data.get("last_post_topic", "")
        feedback = context.user_data.get("pending_feedback", "")
        if not topic or not feedback:
            await query.edit_message_text("Что-то пошло не так. Нажми «Доработать пост» ещё раз.")
            return
        context.user_data["pending_feedback"] = ""
        await query.edit_message_text(f"Запускаю доработку.\nПравки: {feedback}")
        if context.user_data.get("last_pipeline_mode") == "pack":
            await _run_pack(query.message, topic, context.user_data, feedback=feedback)
        else:
            await _run_post(query.message, topic, context.user_data, feedback=feedback)

    elif data.startswith("igshow:"):
        label = data[len("igshow:"):]
        sections = context.user_data.get("pending_ig_sections", {})
        content = sections.get(label)
        if not content:
            await query.answer("Не найдено — попробуй создать пост заново.", show_alert=True)
            return
        await _send(query.message, f"INSTAGRAM — {label} (от {ROLES['Даша']}):\n\n{content}")

    elif data.startswith("post:"):
        key = data[5:]  # "voice" или "text"
        topic = _get_topic(context.user_data, f"{key}_post") or _get_topic(context.user_data, key)
        if not topic:
            await query.edit_message_text("Тема не найдена. Попробуй ещё раз.")
            return
        await query.edit_message_text(f"Запускаю пост по теме:\n«{topic}»")
        await _run_post(query.message, topic, context.user_data)

    elif data.startswith("ofr:"):
        key = data[4:]  # "voice" или "text"
        product = _get_topic(context.user_data, f"{key}_offer") or _get_topic(context.user_data, key)
        if not product:
            await query.edit_message_text("Продукт не найден. Попробуй ещё раз.")
            return
        await query.edit_message_text(f"Запускаю оффер для:\n«{product}»")
        await _run_offer(query.message, product)


async def _run_channelstats(message: Message):
    if not GEMINI_API_KEY:
        await message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    await message.reply_text("Анализирую реальную статистику канала...")
    try:
        r = await _run_blocking(channel_analyst.run, CHANNEL_CHAT_ID, GEMINI_API_KEY)
        header = f"━━━━━━━━━━━━━━━━━━━\nАналитик канала (по {r['posts_count']} постам, {r['subscriber_points']} точкам подписчиков)\n━━━━━━━━━━━━━━━━━━━"
        await message.reply_text(header)
        await _send(message, r["analysis"])
    except Exception as e:
        logger.exception("Ошибка в анализе канала")
        await message.reply_text(f"Ошибка: {e}")


async def cmd_channelstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_channelstats(update.message)


async def cmd_syncinsights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    await update.message.reply_text("Обновляю выводы команды по реальной статистике канала...")
    try:
        r = await _run_blocking(channel_analyst.sync_to_team_memory, CHANNEL_CHAT_ID, GEMINI_API_KEY)
        if r["status"] == "not_enough_data":
            await update.message.reply_text(
                f"Данных мало для обновления (постов: {r['posts_count']}, нужно минимум 5)."
            )
            return
        lines = [f"Обновлено на основе {r['posts_count']} постов.\n"]
        if r["successful"]:
            lines.append("РАБОТАЕТ:")
            lines += [f"• {s}" for s in r["successful"]]
        if r["failed"]:
            lines.append("\nНЕ РАБОТАЕТ:")
            lines += [f"• {s}" for s in r["failed"]]
        if r.get("audience_profile"):
            lines.append("\nОБНОВЛЁННЫЙ ПРОФИЛЬ АУДИТОРИИ (у Нины):")
            lines.append(r["audience_profile"])
        lines.append("\nЭти выводы теперь учитываются Артёмом, Ниной, Машей и Катей при создании новых постов.")
        await _send(update.message, "\n".join(lines))
    except Exception as e:
        logger.exception("Ошибка в /syncinsights")
        await update.message.reply_text(f"Ошибка: {e}")


async def _run_promptcheck(message: Message):
    if not GEMINI_API_KEY:
        await message.reply_text("GEMINI_API_KEY не задан в .env")
        return
    await message.reply_text("Сравниваю реальные данные канала с тем, что выдают агенты...")
    try:
        r = await _run_blocking(channel_analyst.propose_prompt_improvements, CHANNEL_CHAT_ID, GEMINI_API_KEY)
        if r["status"] == "not_enough_data":
            await message.reply_text(f"Данных мало для аудита (постов: {r['posts_count']}, нужно минимум 5).")
            return
        await _send(message, f"Аудит промптов (на основе {r['posts_count']} постов):\n\n{r['report']}")
    except Exception as e:
        logger.exception("Ошибка в /promptcheck")
        await message.reply_text(f"Ошибка: {e}")


async def cmd_promptcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_promptcheck(update.message)


async def cmd_clearrepeats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разовая ремонтная команда: раньше углы/образы/схемы/форматы/CTA писались в общий
    реестр 'уже использовано' на каждом черновике агентов, включая отклонённые попытки —
    из-за этого отклонённые темы навсегда блокировали сами себя как "критичный повтор".
    Это исправлено (реестр теперь пишется только при подтверждённой публикации), но
    накопленный до фикса ложный реестр нужно один раз очистить вручную."""
    cleared = memory_utils.clear_used_registries()
    lines = ["Очистил реестр «уже использовано» команды:"]
    labels = {
        "used_images": "образы", "used_formats": "форматы", "used_ctas": "CTA",
        "used_angles": "углы/аспекты", "used_schemes": "схемы сюжета",
    }
    for key, label in labels.items():
        lines.append(f"• {label}: удалено {cleared.get(key, 0)}")
    lines.append(
        "\nЭто не удаляет темы или тексты — только снимает ложные пометки \"уже было\", "
        "накопленные багом (черновики и отклонённые попытки писались в реестр как опубликованные)."
    )
    await update.message.reply_text("\n".join(lines))


async def job_weekly_promptcheck(context: ContextTypes.DEFAULT_TYPE):
    owner_chat_id = os.getenv("OWNER_CHAT_ID", "").strip()
    if not owner_chat_id:
        return
    try:
        r = await _run_blocking(channel_analyst.propose_prompt_improvements, CHANNEL_CHAT_ID, GEMINI_API_KEY)
        if r["status"] == "not_enough_data":
            return
        text = f"Еженедельный аудит промптов (на основе {r['posts_count']} постов):\n\n{r['report']}"
        for i in range(0, len(text), 4000):
            await context.bot.send_message(chat_id=owner_chat_id, text=text[i:i + 4000])
    except Exception:
        logger.exception("Ошибка в еженедельном аудите промптов")


async def _run_igstats(message: Message):
    if not GEMINI_API_KEY:
        await message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    await message.reply_text("Анализирую реальную статистику Instagram...")
    try:
        r = await _run_blocking(instagram_analyst.run, GEMINI_API_KEY)
        if r["status"] == "not_configured":
            await message.reply_text(r["message"])
            return
        header = (f"━━━━━━━━━━━━━━━━━━━\nАналитик Instagram (по {r['posts_count']} постам, "
                  f"{r['follower_points']} точкам подписчиков)\n━━━━━━━━━━━━━━━━━━━")
        await message.reply_text(header)
        await _send(message, r["analysis"])
    except Exception as e:
        logger.exception("Ошибка в анализе Instagram")
        await message.reply_text(f"Ошибка: {e}")


async def cmd_igstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_igstats(update.message)


async def cmd_igsync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY:
        await update.message.reply_text("GEMINI_API_KEY не задан в .env")
        return

    await update.message.reply_text("Обновляю выводы команды по реальной статистике Instagram...")
    try:
        r = await _run_blocking(instagram_analyst.sync_to_team_memory, GEMINI_API_KEY)
        if r["status"] == "not_configured":
            await update.message.reply_text(
                "IG_BUSINESS_ACCOUNT_ID / IG_ACCESS_TOKEN не заданы в .env."
            )
            return
        if r["status"] == "not_enough_data":
            await update.message.reply_text(
                f"Данных мало для обновления (постов: {r['posts_count']}, нужно минимум 5)."
            )
            return
        lines = [f"Обновлено на основе {r['posts_count']} постов Instagram.\n"]
        if r["successful"]:
            lines.append("РАБОТАЕТ:")
            lines += [f"• {s}" for s in r["successful"]]
        if r["failed"]:
            lines.append("\nНЕ РАБОТАЕТ:")
            lines += [f"• {s}" for s in r["failed"]]
        lines.append("\nЭти выводы теперь учитываются Артёмом, Ниной, Катей и Леной при создании новых постов.")
        await _send(update.message, "\n".join(lines))
    except Exception as e:
        logger.exception("Ошибка в /igsync")
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда не распознана. Напиши /help для списка команд.")


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post or update.edited_channel_post
    if not post or post.chat_id != CHANNEL_CHAT_ID:
        return

    reactions = {}
    if post.reactions:
        for r in post.reactions:
            emoji = getattr(r, "emoji", None) or getattr(r, "custom_emoji_id", "?")
            reactions[emoji] = r.total_count

    channel_stats.save_post(
        chat_id=post.chat_id,
        message_id=post.message_id,
        date=post.date,
        text=post.text or post.caption or "",
        views=post.views,
        forwards=post.forward_origin and 1 or None,
        reactions=reactions,
    )


async def job_snapshot_subscribers(context: ContextTypes.DEFAULT_TYPE):
    try:
        count = await context.bot.get_chat_member_count(CHANNEL_CHAT_ID)
        channel_stats.snapshot_subscribers(CHANNEL_CHAT_ID, count)
        logger.info(f"Снимок подписчиков сохранён: {count}")
    except Exception:
        logger.exception("Не удалось сохранить снимок подписчиков")


def main():
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_BOT_TOKEN не задан в .env")
        sys.exit(1)

    print("SMM-бот запускается...")
    print(f"Gemini API: {'настроен' if GEMINI_API_KEY else 'не задан'}")
    print(f"NotebookLM: {notebook_live.status_line()}")
    print(f"Маршрутизатор: {team_registry.registry_status()}")
    print(f"Instagram Direct: {instagram_messaging.status_line()}")

    persistence = PicklePersistence(filepath=os.path.join(os.path.dirname(__file__), "bot_state.pkl"))
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .concurrent_updates(True)
        .persistence(persistence)
        .build()
    )

    app.add_handler(CommandHandler(["help", "start"], cmd_help))
    app.add_handler(CommandHandler("post", cmd_post))
    app.add_handler(CommandHandler("pack", cmd_pack))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("team", cmd_team))
    app.add_handler(CommandHandler("route", cmd_route))
    app.add_handler(CommandHandler("offer", cmd_offer))
    app.add_handler(CommandHandler("architect", cmd_architect))
    app.add_handler(CommandHandler("plan", cmd_plan))
    # /community и /analytics временно отключены — Миша и Таня спроектированы под
    # автоматическое чтение комментариев из Telegram, которого в коде нет (комментарии
    # нужно вставлять вручную текстом, что на практике не происходит). Включить обратно:
    # app.add_handler(CommandHandler("community", cmd_community))
    # app.add_handler(CommandHandler("analytics", cmd_analytics))
    app.add_handler(CommandHandler("channelstats", cmd_channelstats))
    app.add_handler(CommandHandler("syncinsights", cmd_syncinsights))
    app.add_handler(CommandHandler("promptcheck", cmd_promptcheck))
    app.add_handler(CommandHandler("clearrepeats", cmd_clearrepeats))
    app.add_handler(CommandHandler("igstats", cmd_igstats))
    app.add_handler(CommandHandler("igsync", cmd_igsync))
    app.add_handler(CallbackQueryHandler(handle_tts, pattern="^tts$"))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(
        filters.UpdateType.CHANNEL_POST | filters.UpdateType.EDITED_CHANNEL_POST,
        handle_channel_post
    ))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    app.job_queue.run_repeating(job_snapshot_subscribers, interval=24 * 60 * 60, first=30)
    app.job_queue.run_repeating(job_weekly_promptcheck, interval=7 * 24 * 60 * 60, first=60)

    instagram_messaging.start_webhook_server()
    print("Бот запущен.")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        instagram_messaging.stop_webhook_server()


if __name__ == "__main__":
    main()
