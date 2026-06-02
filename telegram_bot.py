"""
Telegram-бот SMM-команды Дмитрия Сучкова.
"""

import asyncio
import logging
import os
import sys
import tempfile
import time

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
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
    humanizer, publisher, offer_architect, team_architect
)


def _short(text: str, n: int = 3500) -> str:
    return text[:n] + "\n\n[текст обрезан]" if len(text) > n else text


def _fit_bytes(text: str, prefix: str, limit: int = 64) -> str:
    max_bytes = limit - len(prefix.encode("utf-8"))
    encoded = text.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")


async def _send(msg: Message, text: str):
    limit = 4000
    for i in range(0, len(text), limit):
        await msg.reply_text(text[i:i + limit])


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👥 SMM-команда Дмитрия Сучкова\n\n"
        "Команды:\n\n"
        "/post тема — полный цикл создания контента\n"
        "Пример: /post практика Танец Души\n\n"
        "/offer продукт — создать продающий оффер\n"
        "Пример: /offer Личная сессия с Дмитрием\n\n"
        "/architect — аудит команды и план улучшений\n"
        "/architect вопрос — аудит с фокусом на проблему\n\n"
        "Команда (11 агентов):\n"
        "🔍 Нина — анализ ЦА\n"
        "📐 Артём — стратегия\n"
        "💰 Олег — маркетинг\n"
        "✍️ Маша — Telegram-тексты\n"
        "📸 Катя — Instagram-тексты\n"
        "👁 Игорь — редактор TG\n"
        "👁 Лена — редактор IG\n"
        "🧬 Даша — очеловечиватель\n"
        "📦 Рита — публикатор\n"
        "🏆 Виктор — архитектор оффера\n"
        "🔧 Алекс — архитектор команды"
    )
    await update.message.reply_text(text)


async def _run_post(msg: Message, topic: str):
    await msg.reply_text(
        f"👥 Команда берётся за тему:\n«{topic}»\n\nАгенты работают последовательно, это займёт 2–4 минуты..."
    )

    try:
        await msg.reply_text("🔍 Нина Соколова — анализирую аудиторию, дайте минуту...")
        r_analyst = analyst.run(topic, GEMINI_API_KEY)
        await _send(msg, f"🔍 Нина:\n\n{_short(r_analyst['analysis'], 2000)}")

        await msg.reply_text("📐 Артём Волков — Нина, понял тебя. Строю стратегию под эту боль...")
        r_strategist = strategist.run(topic, r_analyst["analysis"], GEMINI_API_KEY)
        await _send(msg, f"📐 Артём:\n\n{_short(r_strategist['strategy'], 2000)}")

        await msg.reply_text("💰 Олег Петров — смотрю на это с точки зрения денег и конверсии...")
        r_marketer = marketer.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY)
        await _send(msg, f"💰 Олег:\n\n{_short(r_marketer['marketing'], 1200)}")

        await msg.reply_text(
            "✍️ Маша Иванова — беру бриф от Артёма и Олега, пишу для Telegram...\n"
            "📸 Катя Смирнова — я параллельно делаю Instagram-версию..."
        )
        loop = asyncio.get_running_loop()
        r_copy, r_insta = await asyncio.gather(
            loop.run_in_executor(None, lambda: copywriter.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY
            )),
            loop.run_in_executor(None, lambda: instagram_writer.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], r_marketer["marketing"], GEMINI_API_KEY
            ))
        )
        await msg.reply_text(
            "✍️ Маша — готово, передаю Игорю на проверку.\n"
            "📸 Катя — моя версия тоже готова, Лена смотри."
        )

        await msg.reply_text("👁 Игорь Сидоров — читаю Машин текст внимательно...")
        r_editor = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy["texts"], GEMINI_API_KEY)
        final_tg = r_copy["texts"]

        if not r_editor["accepted"]:
            await msg.reply_text(
                f"👁 Игорь: Маша, не пойдёт. Вот что не так:\n\n{_short(r_editor['review'], 600)}\n\nПеределай."
            )
            await msg.reply_text("✍️ Маша: Поняла, исправляю...")
            r_copy2 = copywriter.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                                     editor_feedback=r_editor["review"], iteration=2)
            r_editor2 = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy2["texts"],
                                   GEMINI_API_KEY, iteration=2)
            final_tg = r_copy2["texts"]
            if r_editor2["accepted"]:
                await msg.reply_text("👁 Игорь: Теперь хорошо. Принято. ✅")
            else:
                await msg.reply_text("👁 Игорь: Не идеально, но времени нет. Принимаю. ⚠️")
        else:
            await msg.reply_text("👁 Игорь: С первого раза хорошо. Редко такое. Принято. ✅")

        await msg.reply_text("👁 Лена Козлова — проверяю Катин Instagram-контент...")
        r_ig_ed = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_insta["texts"], GEMINI_API_KEY)
        final_ig = r_insta["texts"]

        if not r_ig_ed["accepted"]:
            await msg.reply_text(
                f"👁 Лена: Катя, нужно переделать.\n\n{_short(r_ig_ed['review'], 400)}"
            )
            await msg.reply_text("📸 Катя: Хорошо, сейчас исправлю...")
            r_insta2 = instagram_writer.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_marketer["marketing"], GEMINI_API_KEY,
                                             editor_feedback=r_ig_ed["review"], iteration=2)
            r_ig_ed2 = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_insta2["texts"], GEMINI_API_KEY, iteration=2)
            final_ig = r_insta2["texts"]
            if r_ig_ed2["accepted"]:
                await msg.reply_text("👁 Лена: Теперь норм. Принято. ✅")
            else:
                await msg.reply_text("👁 Лена: Принимаю как есть. ⚠️")
        else:
            await msg.reply_text("👁 Лена: Всё отлично, без правок. ✅")

        await msg.reply_text("🧬 Даша Новикова — убираю роботизированность, добавляю живость...")
        r_human = humanizer.run(topic, final_tg, final_ig, GEMINI_API_KEY)

        await msg.reply_text("📦 Рита Морозова — упаковываю всё для публикации, финальная версия...")
        combined = r_human["telegram_humanized"] + "\n\n---\n\n" + r_human["instagram_humanized"]
        r_pub = publisher.run(topic, combined, r_strategist["strategy"], GEMINI_API_KEY)

        await msg.reply_text("━━━━━━━━━━━━━━━━━━━\n✅ Команда сдала работу\n━━━━━━━━━━━━━━━━━━━")
        await _send(msg, f"📱 TELEGRAM-ТЕКСТ (от Даши):\n\n{r_human['telegram_humanized']}")
        await _send(msg, f"📸 INSTAGRAM-КОНТЕНТ (от Даши):\n\n{r_human['instagram_humanized']}")
        await _send(msg, f"📋 ФИНАЛЬНАЯ УПАКОВКА (от Риты):\n\n{r_pub['final_content']}")

    except Exception as e:
        logger.exception("Ошибка в _run_post")
        await msg.reply_text(f"❌ Ошибка: {e}")


async def _run_offer(msg: Message, product: str):
    await msg.reply_text(
        f"👥 Нина и Виктор берутся за оффер:\n«{product}»\n\nЗаймёт ~1 минуту..."
    )
    try:
        await msg.reply_text("🔍 Нина Соколова — сначала разберусь кто эти люди и что им реально нужно...")
        r_analyst = analyst.run(product, GEMINI_API_KEY)
        await msg.reply_text("🔍 Нина: Готово. Виктор, передаю тебе анализ — смотри особенно на страхи и триггеры.")

        await msg.reply_text("🏆 Виктор Громов — получил, Нина. Строю оффер по Hormozi...")
        r_offer = offer_architect.run(product, r_analyst["analysis"], GEMINI_API_KEY)

        await msg.reply_text("━━━━━━━━━━━━━━━━━━━\n✅ Виктор сдал оффер\n━━━━━━━━━━━━━━━━━━━")
        await _send(msg, f"🏆 ОФФЕР — {product.upper()}\n\n{r_offer['offer']}")

    except Exception as e:
        logger.exception("Ошибка в _run_offer")
        await msg.reply_text(f"❌ Ошибка: {e}")


async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip() if context.args else ""
    if not topic:
        await update.message.reply_text("Укажи тему после команды.\nПример: /post практика Танец Души")
        return
    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return
    await _run_post(update.message, topic)


async def cmd_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = " ".join(context.args).strip() if context.args else ""
    if not product:
        await update.message.reply_text("Укажи продукт: /offer Личная сессия с Дмитрием")
        return
    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return
    await _run_offer(update.message, product)


async def cmd_architect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    focus = " ".join(context.args).strip() if context.args else ""

    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return

    if focus:
        await update.message.reply_text(
            f"🔧 Алекс Громов — разберу команду с фокусом на:\n«{focus}»\n\nЧитаю память всех агентов..."
        )
    else:
        await update.message.reply_text(
            "🔧 Алекс Громов — провожу полный аудит команды. Читаю память каждого агента, ищу слабые места..."
        )

    try:
        r = team_architect.run(GEMINI_API_KEY, focus=focus or None)
        await update.message.reply_text("━━━━━━━━━━━━━━━━━━━\n🔧 Алекс Громов — Аудит команды\n━━━━━━━━━━━━━━━━━━━")
        await _send(update.message, r["audit"])

    except Exception as e:
        logger.exception("Ошибка в /architect")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан")
        return

    await update.message.reply_text("🎤 Получил голосовое. Расшифровываю...")

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()

        client = google_genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                genai_types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                """Расшифруй это голосовое сообщение на русском языке.

Контекст: говорит Дмитрий Сучков — психолог, автор метода GREM, ведёт практику «Танец Души». Работает с женщинами-лидерами и предпринимателями. Часто упоминает: GREM, Танец Души, сессии, выгорание, трансформация, осознанность, женское лидерство.

Правила:
- Пиши точно как сказано, без пересказа
- Правильно расставляй знаки препинания
- Имена собственные и названия практик пиши с заглавной буквы
- Только текст расшифровки, без комментариев и пояснений"""
            ]
        )
        transcript = response.text.strip()

        await update.message.reply_text(f"📝 Расшифровка:\n\n{transcript}")

        keyboard = [
            [InlineKeyboardButton("✍️ Создать пост", callback_data="post:" + _fit_bytes(transcript, "post:"))],
            [InlineKeyboardButton("🏆 Создать оффер", callback_data="ofr:" + _fit_bytes(transcript, "ofr:"))],
        ]
        await update.message.reply_text(
            "Что делать с этим текстом?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.exception("Ошибка при обработке голосового")
        await update.message.reply_text(f"❌ Не удалось расшифровать: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("post:"):
        topic = data[5:]
        await query.edit_message_text(f"✅ Запускаю пост по теме:\n«{topic}»")
        await _run_post(query.message, topic)
    elif data.startswith("ofr:"):
        product = data[4:]
        await query.edit_message_text(f"✅ Запускаю оффер для:\n«{product}»")
        await _run_offer(query.message, product)


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда не распознана. Напиши /help для списка команд.")


def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не задан в .env")
        sys.exit(1)

    print("🚀 SMM-бот запускается...")
    print(f"Gemini API: {'✅ настроен' if GEMINI_API_KEY else '❌ не задан'}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["help", "start"], cmd_help))
    app.add_handler(CommandHandler("post", cmd_post))
    app.add_handler(CommandHandler("offer", cmd_offer))
    app.add_handler(CommandHandler("architect", cmd_architect))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("✅ Бот запущен. Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
