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
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
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
        await update.message.reply_text("Укажи тему: /post выгорание у женщин-руководителей")
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return

    await update.message.reply_text(f"🚀 Запускаю команду для темы:\n«{topic}»\n\nЭто займёт 2-4 минуты...")

    try:
        # 1. Нина — анализ ЦА
        await update.message.reply_text("🔍 Нина анализирует целевую аудиторию...")
        r_analyst = analyst.run(topic, GEMINI_API_KEY)
        await update.message.reply_text(f"✅ *Нина готова*\n\n{_short(r_analyst['analysis'], 1500)}", parse_mode=ParseMode.MARKDOWN)

        # 2. Артём — стратегия
        await update.message.reply_text("📐 Артём строит стратегию...")
        r_strategist = strategist.run(topic, r_analyst["analysis"], GEMINI_API_KEY)
        await update.message.reply_text(f"✅ *Артём готов*\n\n{_short(r_strategist['strategy'], 1500)}", parse_mode=ParseMode.MARKDOWN)

        # 3. Олег — маркетинг
        await update.message.reply_text("💰 Олег даёт маркетинговую оценку...")
        r_marketer = marketer.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY)
        await update.message.reply_text(f"✅ *Олег готов*\n\n{_short(r_marketer['marketing'], 800)}", parse_mode=ParseMode.MARKDOWN)

        # 4. Маша — Telegram + Катя — Instagram (параллельно через asyncio)
        await update.message.reply_text("✍️ Маша и Катя пишут тексты...")
        loop = asyncio.get_event_loop()

        r_copy, r_insta = await asyncio.gather(
            loop.run_in_executor(None, lambda: copywriter.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY
            )),
            loop.run_in_executor(None, lambda: instagram_writer.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], r_marketer["marketing"], GEMINI_API_KEY
            ))
        )

        # 5. Игорь — редактор Telegram (до 2 итераций)
        await update.message.reply_text("👁 Игорь редактирует Telegram-тексты...")
        r_editor = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy["texts"], GEMINI_API_KEY)
        final_tg = r_copy["texts"]

        if not r_editor["accepted"]:
            await update.message.reply_text(f"🔄 Игорь отклонил — Маша переписывает...\n_{_short(r_editor['review'], 500)}_", parse_mode=ParseMode.MARKDOWN)
            r_copy2 = copywriter.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                                     editor_feedback=r_editor["review"], iteration=2)
            r_editor2 = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy2["texts"],
                                   GEMINI_API_KEY, iteration=2)
            final_tg = r_copy2["texts"]
            status = "✅ ПРИНЯТО" if r_editor2["accepted"] else "⚠️ Принято после 2 итераций"
        else:
            status = "✅ ПРИНЯТО с первого раза"

        await update.message.reply_text(f"👁 *Игорь:* {status}", parse_mode=ParseMode.MARKDOWN)

        # 6. Лена — редактор Instagram (до 2 итераций)
        await update.message.reply_text("👁 Лена проверяет Instagram-контент...")
        r_ig_ed = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_insta["texts"], GEMINI_API_KEY)
        final_ig = r_insta["texts"]

        if not r_ig_ed["accepted"]:
            await update.message.reply_text(f"🔄 Лена отклонила — Катя переписывает...", parse_mode=ParseMode.MARKDOWN)
            r_insta2 = instagram_writer.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_marketer["marketing"], GEMINI_API_KEY,
                                             editor_feedback=r_ig_ed["review"], iteration=2)
            r_ig_ed2 = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_insta2["texts"], GEMINI_API_KEY, iteration=2)
            final_ig = r_insta2["texts"]
            ig_status = "✅ ПРИНЯТО" if r_ig_ed2["accepted"] else "⚠️ Принято после 2 итераций"
        else:
            ig_status = "✅ ПРИНЯТО с первого раза"

        await update.message.reply_text(f"👁 *Лена:* {ig_status}", parse_mode=ParseMode.MARKDOWN)

        # 7. Даша — очеловечиватель
        await update.message.reply_text("🧬 Даша очеловечивает тексты...")
        r_human = humanizer.run(topic, final_tg, final_ig, GEMINI_API_KEY)

        # 8. Рита — публикатор
        await update.message.reply_text("📦 Рита упаковывает для публикации...")
        combined = r_human["telegram_humanized"] + "\n\n---\n\n" + r_human["instagram_humanized"]
        r_pub = publisher.run(topic, combined, r_strategist["strategy"], GEMINI_API_KEY)

        # Финал — отправляем весь контент
        await update.message.reply_text("━━━━━━━━━━━━━━━━━━━\n✅ КОМАНДА ЗАВЕРШИЛА РАБОТУ\n━━━━━━━━━━━━━━━━━━━")

        await send(update, f"📱 *TELEGRAM-ТЕКСТ:*\n\n{r_human['telegram_humanized']}")
        await send(update, f"📸 *INSTAGRAM-КОНТЕНТ:*\n\n{r_human['instagram_humanized']}")
        await send(update, f"📋 *УПАКОВКА ОТ РИТЫ:*\n\n{r_pub['final_content']}")

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

    await update.message.reply_text(f"🏆 Виктор строит оффер для:\n«{product}»\n\nЭто займёт ~1 минуту...")

    try:
        await update.message.reply_text("🔍 Сначала Нина анализирует ЦА...")
        r_analyst = analyst.run(product, GEMINI_API_KEY)

        await update.message.reply_text("🏆 Виктор строит оффер по Hormozi...")
        r_offer = offer_architect.run(product, r_analyst["analysis"], GEMINI_API_KEY)

        await update.message.reply_text("━━━━━━━━━━━━━━━━━━━\n✅ ОФФЕР ГОТОВ\n━━━━━━━━━━━━━━━━━━━")
        await send(update, f"🏆 *ОФФЕР — {product.upper()}*\n\n{r_offer['offer']}")

    except Exception as e:
        logger.exception("Ошибка в /оффер")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def cmd_architect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    focus = " ".join(context.args).strip() or None

    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ GEMINI_API_KEY не задан в .env")
        return

    msg = "🔧 Алекс проводит аудит команды..."
    if focus:
        msg += f"\nФокус: «{focus}»"
    await update.message.reply_text(msg)

    try:
        r = team_architect.run(GEMINI_API_KEY, focus=focus)
        await update.message.reply_text("━━━━━━━━━━━━━━━━━━━\n🔧 АУДИТ КОМАНДЫ\n━━━━━━━━━━━━━━━━━━━")
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
                "Расшифруй это голосовое сообщение дословно на русском языке. Только текст, без комментариев."
            ]
        )
        transcript = response.text.strip()

        await update.message.reply_text(f"📝 *Расшифровка:*\n\n{transcript}", parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text(
            "Что делать с этим текстом?\n\n"
            f"/post {transcript[:100]}... — создать пост\n"
            f"/offer {transcript[:100]}... — создать оффер\n\n"
            "Или скопируй нужную команду и замени текст на свой."
        )

    except Exception as e:
        logger.exception("Ошибка при обработке голосового")
        await update.message.reply_text(f"❌ Не удалось расшифровать: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


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
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("✅ Бот запущен. Нажми Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
