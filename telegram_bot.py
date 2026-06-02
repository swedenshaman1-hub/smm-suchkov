"""
Telegram-бот SMM-команды Дмитрия Сучкова.

Команды:
  /пост <тема>        — полный цикл: анализ → стратегия → тексты → редактура → публикация
  /оффер <продукт>    — создать оффер по Hormozi для продукта
  /архитектор         — аудит команды и план улучшений
  /архитектор <фокус> — аудит с конкретным вопросом
  /помощь             — список команд

Запуск: python telegram_bot.py
Нужны переменные окружения: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
"""

import asyncio
import logging
import os
import sys
import tempfile
import time

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Добавляем путь к агентам
sys.path.insert(0, os.path.dirname(__file__))

from agents import (
    analyst, strategist, marketer, copywriter,
    instagram_writer, editor, instagram_editor,
    humanizer, publisher, offer_architect, team_architect
)


def _short(text: str, n: int = 3500) -> str:
    """Обрезает текст до лимита Telegram (4096 символов)."""
    return text[:n] + "\n\n_[текст обрезан]_" if len(text) > n else text


async def send(update: Update, text: str):
    """Отправляет сообщение, разбивая если > 4096 символов."""
    limit = 4000
    for i in range(0, len(text), limit):
        await update.message.reply_text(text[i:i + limit])


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """👥 *SMM-команда Дмитрия Сучкова*

*Команды:*

`/post <тема>` — полный цикл создания контента
_Пример: /post выгорание у женщин-руководителей_

`/offer <продукт>` — создать продающий оффер
_Пример: /offer Личная сессия с Дмитрием_

`/architect` — аудит команды и план улучшений
`/architect <вопрос>` — аудит с фокусом на конкретную проблему

*Команда (11 агентов):*
🔍 Нина — анализ ЦА
📐 Артём — стратегия
💰 Олег — маркетинг
✍️ Маша — Telegram-тексты
📸 Катя — Instagram-тексты
👁 Игорь — редактор TG
👁 Лена — редактор IG
🧬 Даша — очеловечиватель
📦 Рита — публикатор
🏆 Виктор — архитектор оффера
🔧 Алекс — архитектор команды"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("Укажи тему после команды.\nПример: /post практика танец души")
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return

    await update.message.reply_text(
        f"👥 *Команда берётся за тему:*\n«{topic}»\n\n_Агенты работают последовательно, это займёт 2–4 минуты..._",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        # 1. Нина — анализ ЦА
        await update.message.reply_text("🔍 *Нина Соколова* — анализирую аудиторию, дайте минуту...", parse_mode=ParseMode.MARKDOWN)
        r_analyst = analyst.run(topic, GEMINI_API_KEY)
        await send(update, f"🔍 *Нина:*\n\n{_short(r_analyst['analysis'], 2000)}")

        # 2. Артём — стратегия
        await update.message.reply_text("📐 *Артём Волков* — Нина, понял тебя. Строю стратегию под эту боль...", parse_mode=ParseMode.MARKDOWN)
        r_strategist = strategist.run(topic, r_analyst["analysis"], GEMINI_API_KEY)
        await send(update, f"📐 *Артём:*\n\n{_short(r_strategist['strategy'], 2000)}")

        # 3. Олег — маркетинг
        await update.message.reply_text("💰 *Олег Петров* — смотрю на это с точки зрения денег и конверсии...", parse_mode=ParseMode.MARKDOWN)
        r_marketer = marketer.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY)
        await send(update, f"💰 *Олег:*\n\n{_short(r_marketer['marketing'], 1200)}")

        # 4. Маша + Катя — параллельно
        await update.message.reply_text(
            "✍️ *Маша Иванова* — беру бриф от Артёма и Олега, пишу для Telegram...\n"
            "📸 *Катя Смирнова* — я параллельно делаю Instagram-версию...",
            parse_mode=ParseMode.MARKDOWN
        )
        loop = asyncio.get_event_loop()
        r_copy, r_insta = await asyncio.gather(
            loop.run_in_executor(None, lambda: copywriter.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY
            )),
            loop.run_in_executor(None, lambda: instagram_writer.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], r_marketer["marketing"], GEMINI_API_KEY
            ))
        )
        await update.message.reply_text("✍️ *Маша* — готово, передаю Игорю на проверку.\n📸 *Катя* — моя версия тоже готова, Лена смотри.", parse_mode=ParseMode.MARKDOWN)

        # 5. Игорь — редактор TG
        await update.message.reply_text("👁 *Игорь Сидоров* — читаю Машин текст внимательно...", parse_mode=ParseMode.MARKDOWN)
        r_editor = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy["texts"], GEMINI_API_KEY)
        final_tg = r_copy["texts"]

        if not r_editor["accepted"]:
            await update.message.reply_text(
                f"👁 *Игорь:* Маша, не пойдёт. Вот что не так:\n\n_{_short(r_editor['review'], 600)}_\n\nПеределай.",
                parse_mode=ParseMode.MARKDOWN
            )
            await update.message.reply_text("✍️ *Маша:* Поняла, исправляю...", parse_mode=ParseMode.MARKDOWN)
            r_copy2 = copywriter.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                                     editor_feedback=r_editor["review"], iteration=2)
            r_editor2 = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy2["texts"],
                                   GEMINI_API_KEY, iteration=2)
            final_tg = r_copy2["texts"]
            if r_editor2["accepted"]:
                await update.message.reply_text("👁 *Игорь:* Теперь хорошо. Принято. ✅", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("👁 *Игорь:* Не идеально, но времени нет. Принимаю. ⚠️", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("👁 *Игорь:* С первого раза хорошо. Редко такое. Принято. ✅", parse_mode=ParseMode.MARKDOWN)

        # 6. Лена — редактор IG
        await update.message.reply_text("👁 *Лена Козлова* — проверяю Катин Instagram-контент...", parse_mode=ParseMode.MARKDOWN)
        r_ig_ed = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_insta["texts"], GEMINI_API_KEY)
        final_ig = r_insta["texts"]

        if not r_ig_ed["accepted"]:
            await update.message.reply_text(
                f"👁 *Лена:* Катя, нужно переделать.\n\n_{_short(r_ig_ed['review'], 400)}_",
                parse_mode=ParseMode.MARKDOWN
            )
            await update.message.reply_text("📸 *Катя:* Хорошо, сейчас исправлю...", parse_mode=ParseMode.MARKDOWN)
            r_insta2 = instagram_writer.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_marketer["marketing"], GEMINI_API_KEY,
                                             editor_feedback=r_ig_ed["review"], iteration=2)
            r_ig_ed2 = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_insta2["texts"], GEMINI_API_KEY, iteration=2)
            final_ig = r_insta2["texts"]
            if r_ig_ed2["accepted"]:
                await update.message.reply_text("👁 *Лена:* Теперь норм. Принято. ✅", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("👁 *Лена:* Принимаю как есть. ⚠️", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("👁 *Лена:* Всё отлично, без правок. ✅", parse_mode=ParseMode.MARKDOWN)

        # 7. Даша
        await update.message.reply_text("🧬 *Даша Новикова* — убираю роботизированность, добавляю живость...", parse_mode=ParseMode.MARKDOWN)
        r_human = humanizer.run(topic, final_tg, final_ig, GEMINI_API_KEY)

        # 8. Рита
        await update.message.reply_text("📦 *Рита Морозова* — упаковываю всё для публикации, финальная версия...", parse_mode=ParseMode.MARKDOWN)
        combined = r_human["telegram_humanized"] + "\n\n---\n\n" + r_human["instagram_humanized"]
        r_pub = publisher.run(topic, combined, r_strategist["strategy"], GEMINI_API_KEY)

        # Финал
        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━\n"
            "✅ *Команда сдала работу*\n"
            "━━━━━━━━━━━━━━━━━━━",
            parse_mode=ParseMode.MARKDOWN
        )
        await send(update, f"📱 *TELEGRAM-ТЕКСТ (от Даши):*\n\n{r_human['telegram_humanized']}")
        await send(update, f"📸 *INSTAGRAM-КОНТЕНТ (от Даши):*\n\n{r_human['instagram_humanized']}")
        await send(update, f"📋 *ФИНАЛЬНАЯ УПАКОВКА (от Риты):*\n\n{r_pub['final_content']}")

    except Exception as e:
        logger.exception("Ошибка в /пост")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = " ".join(context.args).strip()
    if not product:
        await update.message.reply_text("Укажи продукт: /offer Личная сессия с Дмитрием")
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return

    await update.message.reply_text(
        f"👥 *Нина и Виктор берутся за оффер:*\n«{product}»\n\n_Займёт ~1 минуту..._",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        await update.message.reply_text("🔍 *Нина Соколова* — сначала разберусь кто эти люди и что им реально нужно...", parse_mode=ParseMode.MARKDOWN)
        r_analyst = analyst.run(product, GEMINI_API_KEY)
        await update.message.reply_text(f"🔍 *Нина:* Готово. Виктор, передаю тебе анализ — смотри особенно на страхи и триггеры.", parse_mode=ParseMode.MARKDOWN)

        await update.message.reply_text("🏆 *Виктор Громов* — получил, Нина. Строю оффер по Hormozi...", parse_mode=ParseMode.MARKDOWN)
        r_offer = offer_architect.run(product, r_analyst["analysis"], GEMINI_API_KEY)

        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━\n✅ *Виктор сдал оффер*\n━━━━━━━━━━━━━━━━━━━",
            parse_mode=ParseMode.MARKDOWN
        )
        await send(update, f"🏆 *ОФФЕР — {product.upper()}*\n\n{r_offer['offer']}")

    except Exception as e:
        logger.exception("Ошибка в /оффер")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_architect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    focus = " ".join(context.args).strip() or None

    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return

    if focus:
        await update.message.reply_text(
            f"🔧 *Алекс Громов* — сейчас разберу команду с фокусом на:\n«{focus}»\n\n_Читаю память всех агентов..._",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "🔧 *Алекс Громов* — провожу полный аудит команды. Читаю память каждого агента, ищу слабые места...",
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        r = team_architect.run(GEMINI_API_KEY, focus=focus)
        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━\n🔧 *Алекс Громов — Аудит команды*\n━━━━━━━━━━━━━━━━━━━",
            parse_mode=ParseMode.MARKDOWN
        )
        await send(update, r["audit"])

    except Exception as e:
        logger.exception("Ошибка в /архитектор")
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

        await update.message.reply_text(f"📝 *Расшифровка:*\n\n{transcript}", parse_mode=ParseMode.MARKDOWN)

        short = transcript[:55]  # Telegram limit: 64 bytes total
        keyboard = [
            [InlineKeyboardButton("✍️ Создать пост", callback_data=f"post:{short}")],
            [InlineKeyboardButton("🏆 Создать оффер", callback_data=f"ofr:{short}")],
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
        context.args = topic.split()
        await query.edit_message_text(f"✅ Запускаю пост по теме:\n«{topic}»")
        update.message = query.message
        await cmd_post(update, context)
    elif data.startswith("ofr:"):
        product = data[4:]
        context.args = product.split()
        await query.edit_message_text(f"✅ Запускаю оффер для:\n«{product}»")
        update.message = query.message
        await cmd_offer(update, context)


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда не распознана. Напиши /help для списка команд.")


def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не задан в .env")
        print("Добавь строку: TELEGRAM_BOT_TOKEN=твой_токен_от_BotFather")
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
