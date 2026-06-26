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

sys.path.insert(0, os.path.dirname(__file__))

from agents import (
    analyst, strategist, marketer, copywriter,
    instagram_writer, editor, instagram_editor,
    humanizer, publisher, offer_architect, team_architect, content_planner,
    community_manager, comment_analyst, channel_stats, channel_analyst
)
from agents import memory_utils

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
    "ambiguous_feedback_text",
]


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
            await msg.reply_text(chunk)
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
    text = _strip_label_header(query.message.text or "")
    if not text.strip():
        await query.message.reply_text("Нечего озвучивать — сообщение пустое.")
        return
    audio_path = None
    await query.message.reply_text("🔊 Озвучиваю — может занять до пары минут...")
    try:
        loop = asyncio.get_running_loop()
        audio_path = await asyncio.wait_for(
            loop.run_in_executor(None, _text_to_speech, text), timeout=150
        )
        preview = text.strip().splitlines()[0][:60]
        with open(audio_path, "rb") as f:
            await query.message.reply_audio(f, title="Озвучка сообщения", caption=f"🔊 {preview}…")
    except Exception as e:
        logger.exception("Ошибка озвучки")
        await query.message.reply_text(f"Не удалось озвучить (сервис озвучки не ответил). Попробуй ещё раз через минуту.\n\nТехническая причина: {e}")
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except Exception:
                pass


def _text_to_speech(text: str) -> str:
    """Озвучивает текст через Gemini TTS (надёжнее на облачных серверах, чем gTTS,
    который ходит на неофициальный эндпоинт Google Translate и часто блокирует datacenter IP)."""
    client = google_genai.Client(api_key=GEMINI_API_KEY, http_options=genai_types.HttpOptions(timeout=120_000))
    last_error = None
    for attempt in range(3):
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
        raise TimeoutError(f"Gemini TTS не ответил за 3 попытки: {last_error}")
    pcm_data = response.candidates[0].content.parts[0].inline_data.data

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_data)
    return path


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
    дальше по цепочке передавался только выбранный вариант, а не оба сразу."""
    if not letter:
        return text
    pattern = rf"ВАРИАНТ\s+{letter}\b.*?(?=ВАРИАНТ\s+[АБ]\b|ПОЧЕМУ\s+ЭТИ\s+ДВА\s+ВАРИАНТА|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return text
    chunk = match.group(0).strip()
    lines = chunk.split("\n", 1)
    return lines[1].strip() if len(lines) > 1 else chunk


async def _run_blocking(fn, *args, **kwargs):
    """Выполняет блокирующий (синхронный) вызов агента в отдельном потоке,
    чтобы не замораживать цикл обработки событий бота (и его опрос Telegram)
    на те секунды-минуты, которые требует вызов Gemini. Таймаут — страховка
    на случай, если сетевой вызов внутри повиснет без собственной ошибки."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, lambda: fn(*args, **kwargs)), timeout=180)
    except asyncio.TimeoutError:
        raise TimeoutError("Запрос к Gemini не ответил за 3 минуты — вероятно, временный сбой сети. Попробуй ещё раз.")


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
        await _run_post_inner(msg, topic, user_data, feedback, delivery_filter)
    finally:
        _active_pipelines.discard(chat_id)


async def _run_post_inner(msg: Message, topic: str, user_data: dict, feedback: str = None, delivery_filter: str = "all"):
    if feedback:
        await msg.reply_text(
            f"Команда дорабатывает пост по теме:\n«{topic}»\n\nПравки: {feedback}\n\nЗаймёт 2–4 минуты..."
        )
    else:
        await msg.reply_text(
            f"Команда берётся за тему:\n«{topic}»\n\nАгенты работают последовательно, займёт 2–4 минуты..."
        )

    try:
        await msg.reply_text("Нина Соколова — анализирую аудиторию...")
        r_analyst = await _run_blocking(analyst.run, topic, GEMINI_API_KEY)
        await _send(msg, f"{ROLES['Нина']}:\n\n{r_analyst['analysis']}")

        await msg.reply_text("Артём Волков — строю стратегию...")
        r_strategist = await _run_blocking(strategist.run, topic, r_analyst["analysis"], GEMINI_API_KEY)
        await _send(msg, f"{ROLES['Артём']}:\n\n{r_strategist['strategy']}")

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
        r_copy, r_insta = await asyncio.gather(
            loop.run_in_executor(None, lambda: copywriter.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                editor_feedback=feedback, iteration=2 if feedback else 1
            )),
            loop.run_in_executor(None, lambda: instagram_writer.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], "", GEMINI_API_KEY,
                editor_feedback=feedback, iteration=2 if feedback else 1
            ))
        )
        await msg.reply_text(
            f"{ROLES['Маша']} — готово, передаю Игорю на проверку.\n"
            f"{ROLES['Катя']} — пакет готов, Лена смотри."
        )

        await msg.reply_text("Игорь Орлов — читаю оба варианта Маши...")
        r_editor = await _run_blocking(
            editor.run, topic, r_analyst["analysis"], r_strategist["strategy"],
            r_copy["texts"], GEMINI_API_KEY
        )
        final_tg = _extract_variant(r_copy["texts"], r_editor.get("chosen_variant"))

        if not r_editor["accepted"]:
            await _send(msg, f"{ROLES['Игорь']}: Маша, не пойдёт. Вот что не так:\n\n{r_editor['review']}\n\nПеределай.")
            await msg.reply_text(f"{ROLES['Маша']}: Поняла, исправляю...")
            r_copy2 = await _run_blocking(
                copywriter.run, topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                editor_feedback=r_editor["review"], iteration=2
            )
            r_editor2 = await _run_blocking(
                editor.run, topic, r_analyst["analysis"], r_strategist["strategy"],
                r_copy2["texts"], GEMINI_API_KEY, iteration=2
            )
            final_tg = _extract_variant(r_copy2["texts"], r_editor2.get("chosen_variant"))
            await msg.reply_text(
                f"{ROLES['Игорь']}: Теперь хорошо. Принято." if r_editor2["accepted"]
                else f"{ROLES['Игорь']}: Не идеально, но принимаю."
            )
            if r_editor2.get("chosen_variant"):
                await msg.reply_text(f"Игорь выбрал вариант {r_editor2['chosen_variant']} для публикации.")
        else:
            await msg.reply_text(f"{ROLES['Игорь']}: С первого раза хорошо. Принято.")
            if r_editor.get("chosen_variant"):
                await msg.reply_text(f"Игорь выбрал вариант {r_editor['chosen_variant']} для публикации.")

        await msg.reply_text("Лена Волкова — проверяю Instagram-пакет Кати...")
        r_ig_ed = await _run_blocking(
            instagram_editor.run, topic, r_analyst["analysis"], r_strategist["strategy"],
            r_insta["texts"], GEMINI_API_KEY
        )
        final_ig = r_insta["texts"]

        if not r_ig_ed["accepted"]:
            await _send(msg, f"{ROLES['Лена']}: Катя, нужно переделать.\n\n{r_ig_ed['review']}")
            await msg.reply_text(f"{ROLES['Катя']}: Хорошо, сейчас исправлю...")
            r_insta2 = await _run_blocking(
                instagram_writer.run, topic, r_analyst["analysis"], r_strategist["strategy"],
                "", GEMINI_API_KEY,
                editor_feedback=r_ig_ed["review"], iteration=2
            )
            r_ig_ed2 = await _run_blocking(
                instagram_editor.run, topic, r_analyst["analysis"], r_strategist["strategy"],
                r_insta2["texts"], GEMINI_API_KEY, iteration=2
            )
            final_ig = r_insta2["texts"]
            await msg.reply_text(
                f"{ROLES['Лена']}: Теперь норм. Принято." if r_ig_ed2["accepted"]
                else f"{ROLES['Лена']}: Принимаю как есть."
            )
        else:
            await msg.reply_text(f"{ROLES['Лена']}: Всё отлично, без правок.")

        await msg.reply_text("Даша Козлова — убираю AI-паттерны, добавляю живость...")
        final_ig_sections = dict(_split_instagram_sections(final_ig))
        ig_post_raw = final_ig_sections.pop("ПОСТ", final_ig)
        ig_other_sections_raw = final_ig_sections  # СТОРИС / КАРУСЕЛЬ / REELS
        r_human = await _run_blocking(humanizer.run, topic, final_tg, ig_post_raw, GEMINI_API_KEY)

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

        ig_post_content = r_human["instagram_humanized"]
        full_ig_text = ig_post_content + "\n\n" + "\n\n".join(
            f"{label}:\n{content}" for label, content in ig_other_sections.items()
        )

        await msg.reply_text("Олег Савин — оцениваю виральный и коммерческий потенциал готового текста...")
        r_marketer = await _run_blocking(
            marketer.run, topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
            final_content=f"TELEGRAM:\n{r_human['telegram_humanized']}\n\nINSTAGRAM:\n{full_ig_text}"
        )
        await _send(msg, f"{ROLES['Олег']}:\n\n{r_marketer['marketing']}")

        await msg.reply_text("Света Громова — финальная проверка и подготовка к публикации...")
        r_pub = await _run_blocking(
            publisher.run, topic,
            r_human["telegram_humanized"],
            full_ig_text,
            GEMINI_API_KEY
        )

        remaining_sections = ig_other_sections

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

    except Exception as e:
        logger.exception("Ошибка в _run_post")
        await msg.reply_text(f"Ошибка: {e}")


async def _run_offer(msg: Message, product: str):
    await msg.reply_text(f"Нина и Виктор берутся за оффер:\n«{product}»\n\nЗаймёт ~1 минуту...")
    try:
        await msg.reply_text("Нина Соколова — анализирую аудиторию под этот продукт...")
        r_analyst = await _run_blocking(analyst.run, product, GEMINI_API_KEY)
        await msg.reply_text(f"{ROLES['Нина']}: Готово. Виктор, передаю анализ.")

        await msg.reply_text("Виктор Самойлов — строю оффер по Хормози...")
        r_offer = await _run_blocking(offer_architect.run, product, r_analyst["analysis"], GEMINI_API_KEY)

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
        "/post тема — полный цикл создания контента\n"
        "Пример: /post практика Танец Души\n\n"
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

        # Сохраняем полный текст в user_data — без обрезки
        _store_topic(context.user_data, "voice_post", transcript)
        _store_topic(context.user_data, "voice_offer", transcript)
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
        for prefix in ["напиши пост про ", "напиши пост о ", "создай пост про ", "создай пост о ",
                        "напиши пост ", "создай пост ", "пост про ", "пост о ", "пост "]:
            if topic.lower().startswith(prefix):
                topic = topic[len(prefix):]
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
            await _run_post(query.message, topic, context.user_data, feedback=pending_text)
        else:
            await query.edit_message_text(f"Запускаю пост по теме:\n«{pending_text}»")
            await _run_post(query.message, pending_text, context.user_data)
        return

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

    elif data == "confirm_revise":
        topic = context.user_data.get("last_post_topic", "")
        feedback = context.user_data.get("pending_feedback", "")
        if not topic or not feedback:
            await query.edit_message_text("Что-то пошло не так. Нажми «Доработать пост» ещё раз.")
            return
        context.user_data["pending_feedback"] = ""
        await query.edit_message_text(f"Запускаю доработку.\nПравки: {feedback}")
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

    print("Бот запущен.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
