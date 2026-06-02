"""
Telegram-Р±РѕС‚ SMM-РєРѕРјР°РЅРґС‹ Р”РјРёС‚СЂРёСЏ РЎСѓС‡РєРѕРІР°.

РљРѕРјР°РЅРґС‹:
  /РїРѕСЃС‚ <С‚РµРјР°>        вЂ” РїРѕР»РЅС‹Р№ С†РёРєР»: Р°РЅР°Р»РёР· в†’ СЃС‚СЂР°С‚РµРіРёСЏ в†’ С‚РµРєСЃС‚С‹ в†’ СЂРµРґР°РєС‚СѓСЂР° в†’ РїСѓР±Р»РёРєР°С†РёСЏ
  /РѕС„С„РµСЂ <РїСЂРѕРґСѓРєС‚>    вЂ” СЃРѕР·РґР°С‚СЊ РѕС„С„РµСЂ РїРѕ Hormozi РґР»СЏ РїСЂРѕРґСѓРєС‚Р°
  /Р°СЂС…РёС‚РµРєС‚РѕСЂ         вЂ” Р°СѓРґРёС‚ РєРѕРјР°РЅРґС‹ Рё РїР»Р°РЅ СѓР»СѓС‡С€РµРЅРёР№
  /Р°СЂС…РёС‚РµРєС‚РѕСЂ <С„РѕРєСѓСЃ> вЂ” Р°СѓРґРёС‚ СЃ РєРѕРЅРєСЂРµС‚РЅС‹Рј РІРѕРїСЂРѕСЃРѕРј
  /РїРѕРјРѕС‰СЊ             вЂ” СЃРїРёСЃРѕРє РєРѕРјР°РЅРґ

Р—Р°РїСѓСЃРє: python telegram_bot.py
РќСѓР¶РЅС‹ РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
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

# Р”РѕР±Р°РІР»СЏРµРј РїСѓС‚СЊ Рє Р°РіРµРЅС‚Р°Рј
sys.path.insert(0, os.path.dirname(__file__))

from agents import (
    analyst, strategist, marketer, copywriter,
    instagram_writer, editor, instagram_editor,
    humanizer, publisher, offer_architect, team_architect
)


def _short(text: str, n: int = 3500) -> str:
    """РћР±СЂРµР·Р°РµС‚ С‚РµРєСЃС‚ РґРѕ Р»РёРјРёС‚Р° Telegram (4096 СЃРёРјРІРѕР»РѕРІ)."""
    return text[:n] + "\n\n_[С‚РµРєСЃС‚ РѕР±СЂРµР·Р°РЅ]_" if len(text) > n else text


async def send(update: Update, text: str):
    """РћС‚РїСЂР°РІР»СЏРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ, СЂР°Р·Р±РёРІР°СЏ РµСЃР»Рё > 4096 СЃРёРјРІРѕР»РѕРІ."""
    limit = 4000
    for i in range(0, len(text), limit):
        await update.message.reply_text(text[i:i + limit])


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """рџ‘Ґ *SMM-РєРѕРјР°РЅРґР° Р”РјРёС‚СЂРёСЏ РЎСѓС‡РєРѕРІР°*

*РљРѕРјР°РЅРґС‹:*

`/post <С‚РµРјР°>` вЂ” РїРѕР»РЅС‹Р№ С†РёРєР» СЃРѕР·РґР°РЅРёСЏ РєРѕРЅС‚РµРЅС‚Р°
_РџСЂРёРјРµСЂ: /post РІС‹РіРѕСЂР°РЅРёРµ Сѓ Р¶РµРЅС‰РёРЅ-СЂСѓРєРѕРІРѕРґРёС‚РµР»РµР№_

`/offer <РїСЂРѕРґСѓРєС‚>` вЂ” СЃРѕР·РґР°С‚СЊ РїСЂРѕРґР°СЋС‰РёР№ РѕС„С„РµСЂ
_РџСЂРёРјРµСЂ: /offer Р›РёС‡РЅР°СЏ СЃРµСЃСЃРёСЏ СЃ Р”РјРёС‚СЂРёРµРј_

`/architect` вЂ” Р°СѓРґРёС‚ РєРѕРјР°РЅРґС‹ Рё РїР»Р°РЅ СѓР»СѓС‡С€РµРЅРёР№
`/architect <РІРѕРїСЂРѕСЃ>` вЂ” Р°СѓРґРёС‚ СЃ С„РѕРєСѓСЃРѕРј РЅР° РєРѕРЅРєСЂРµС‚РЅСѓСЋ РїСЂРѕР±Р»РµРјСѓ

*РљРѕРјР°РЅРґР° (11 Р°РіРµРЅС‚РѕРІ):*
рџ”Ќ РќРёРЅР° вЂ” Р°РЅР°Р»РёР· Р¦Рђ
рџ“ђ РђСЂС‚С‘Рј вЂ” СЃС‚СЂР°С‚РµРіРёСЏ
рџ’° РћР»РµРі вЂ” РјР°СЂРєРµС‚РёРЅРі
вњЌпёЏ РњР°С€Р° вЂ” Telegram-С‚РµРєСЃС‚С‹
рџ“ё РљР°С‚СЏ вЂ” Instagram-С‚РµРєСЃС‚С‹
рџ‘Ѓ РРіРѕСЂСЊ вЂ” СЂРµРґР°РєС‚РѕСЂ TG
рџ‘Ѓ Р›РµРЅР° вЂ” СЂРµРґР°РєС‚РѕСЂ IG
рџ§¬ Р”Р°С€Р° вЂ” РѕС‡РµР»РѕРІРµС‡РёРІР°С‚РµР»СЊ
рџ“¦ Р РёС‚Р° вЂ” РїСѓР±Р»РёРєР°С‚РѕСЂ
рџЏ† Р’РёРєС‚РѕСЂ вЂ” Р°СЂС…РёС‚РµРєС‚РѕСЂ РѕС„С„РµСЂР°
рџ”§ РђР»РµРєСЃ вЂ” Р°СЂС…РёС‚РµРєС‚РѕСЂ РєРѕРјР°РЅРґС‹"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("РЈРєР°Р¶Рё С‚РµРјСѓ: /post РІС‹РіРѕСЂР°РЅРёРµ Сѓ Р¶РµРЅС‰РёРЅ-СЂСѓРєРѕРІРѕРґРёС‚РµР»РµР№")
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("вќЊ GEMINI_API_KEY РЅРµ Р·Р°РґР°РЅ РІ .env")
        return

    await update.message.reply_text(f"рџљЂ Р—Р°РїСѓСЃРєР°СЋ РєРѕРјР°РЅРґСѓ РґР»СЏ С‚РµРјС‹:\nВ«{topic}В»\n\nР­С‚Рѕ Р·Р°Р№РјС‘С‚ 2-4 РјРёРЅСѓС‚С‹...")

    try:
        # 1. РќРёРЅР° вЂ” Р°РЅР°Р»РёР· Р¦Рђ
        await update.message.reply_text("рџ”Ќ РќРёРЅР° Р°РЅР°Р»РёР·РёСЂСѓРµС‚ С†РµР»РµРІСѓСЋ Р°СѓРґРёС‚РѕСЂРёСЋ...")
        r_analyst = analyst.run(topic, GEMINI_API_KEY)
        await update.message.reply_text(f"вњ… *РќРёРЅР° РіРѕС‚РѕРІР°*\n\n{_short(r_analyst['analysis'], 1500)}", parse_mode=ParseMode.MARKDOWN)

        # 2. РђСЂС‚С‘Рј вЂ” СЃС‚СЂР°С‚РµРіРёСЏ
        await update.message.reply_text("рџ“ђ РђСЂС‚С‘Рј СЃС‚СЂРѕРёС‚ СЃС‚СЂР°С‚РµРіРёСЋ...")
        r_strategist = strategist.run(topic, r_analyst["analysis"], GEMINI_API_KEY)
        await update.message.reply_text(f"вњ… *РђСЂС‚С‘Рј РіРѕС‚РѕРІ*\n\n{_short(r_strategist['strategy'], 1500)}", parse_mode=ParseMode.MARKDOWN)

        # 3. РћР»РµРі вЂ” РјР°СЂРєРµС‚РёРЅРі
        await update.message.reply_text("рџ’° РћР»РµРі РґР°С‘С‚ РјР°СЂРєРµС‚РёРЅРіРѕРІСѓСЋ РѕС†РµРЅРєСѓ...")
        r_marketer = marketer.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY)
        await update.message.reply_text(f"вњ… *РћР»РµРі РіРѕС‚РѕРІ*\n\n{_short(r_marketer['marketing'], 800)}", parse_mode=ParseMode.MARKDOWN)

        # 4. РњР°С€Р° вЂ” Telegram + РљР°С‚СЏ вЂ” Instagram (РїР°СЂР°Р»Р»РµР»СЊРЅРѕ С‡РµСЂРµР· asyncio)
        await update.message.reply_text("вњЌпёЏ РњР°С€Р° Рё РљР°С‚СЏ РїРёС€СѓС‚ С‚РµРєСЃС‚С‹...")
        loop = asyncio.get_event_loop()

        r_copy, r_insta = await asyncio.gather(
            loop.run_in_executor(None, lambda: copywriter.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY
            )),
            loop.run_in_executor(None, lambda: instagram_writer.run(
                topic, r_analyst["analysis"], r_strategist["strategy"], r_marketer["marketing"], GEMINI_API_KEY
            ))
        )

        # 5. РРіРѕСЂСЊ вЂ” СЂРµРґР°РєС‚РѕСЂ Telegram (РґРѕ 2 РёС‚РµСЂР°С†РёР№)
        await update.message.reply_text("рџ‘Ѓ РРіРѕСЂСЊ СЂРµРґР°РєС‚РёСЂСѓРµС‚ Telegram-С‚РµРєСЃС‚С‹...")
        r_editor = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy["texts"], GEMINI_API_KEY)
        final_tg = r_copy["texts"]

        if not r_editor["accepted"]:
            await update.message.reply_text(f"рџ”„ РРіРѕСЂСЊ РѕС‚РєР»РѕРЅРёР» вЂ” РњР°С€Р° РїРµСЂРµРїРёСЃС‹РІР°РµС‚...\n_{_short(r_editor['review'], 500)}_", parse_mode=ParseMode.MARKDOWN)
            r_copy2 = copywriter.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                                     editor_feedback=r_editor["review"], iteration=2)
            r_editor2 = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy2["texts"],
                                   GEMINI_API_KEY, iteration=2)
            final_tg = r_copy2["texts"]
            status = "вњ… РџР РРќРЇРўРћ" if r_editor2["accepted"] else "вљ пёЏ РџСЂРёРЅСЏС‚Рѕ РїРѕСЃР»Рµ 2 РёС‚РµСЂР°С†РёР№"
        else:
            status = "вњ… РџР РРќРЇРўРћ СЃ РїРµСЂРІРѕРіРѕ СЂР°Р·Р°"

        await update.message.reply_text(f"рџ‘Ѓ *РРіРѕСЂСЊ:* {status}", parse_mode=ParseMode.MARKDOWN)

        # 6. Р›РµРЅР° вЂ” СЂРµРґР°РєС‚РѕСЂ Instagram (РґРѕ 2 РёС‚РµСЂР°С†РёР№)
        await update.message.reply_text("рџ‘Ѓ Р›РµРЅР° РїСЂРѕРІРµСЂСЏРµС‚ Instagram-РєРѕРЅС‚РµРЅС‚...")
        r_ig_ed = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_insta["texts"], GEMINI_API_KEY)
        final_ig = r_insta["texts"]

        if not r_ig_ed["accepted"]:
            await update.message.reply_text(f"рџ”„ Р›РµРЅР° РѕС‚РєР»РѕРЅРёР»Р° вЂ” РљР°С‚СЏ РїРµСЂРµРїРёСЃС‹РІР°РµС‚...", parse_mode=ParseMode.MARKDOWN)
            r_insta2 = instagram_writer.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_marketer["marketing"], GEMINI_API_KEY,
                                             editor_feedback=r_ig_ed["review"], iteration=2)
            r_ig_ed2 = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"],
                                             r_insta2["texts"], GEMINI_API_KEY, iteration=2)
            final_ig = r_insta2["texts"]
            ig_status = "вњ… РџР РРќРЇРўРћ" if r_ig_ed2["accepted"] else "вљ пёЏ РџСЂРёРЅСЏС‚Рѕ РїРѕСЃР»Рµ 2 РёС‚РµСЂР°С†РёР№"
        else:
            ig_status = "вњ… РџР РРќРЇРўРћ СЃ РїРµСЂРІРѕРіРѕ СЂР°Р·Р°"

        await update.message.reply_text(f"рџ‘Ѓ *Р›РµРЅР°:* {ig_status}", parse_mode=ParseMode.MARKDOWN)

        # 7. Р”Р°С€Р° вЂ” РѕС‡РµР»РѕРІРµС‡РёРІР°С‚РµР»СЊ
        await update.message.reply_text("рџ§¬ Р”Р°С€Р° РѕС‡РµР»РѕРІРµС‡РёРІР°РµС‚ С‚РµРєСЃС‚С‹...")
        r_human = humanizer.run(topic, final_tg, final_ig, GEMINI_API_KEY)

        # 8. Р РёС‚Р° вЂ” РїСѓР±Р»РёРєР°С‚РѕСЂ
        await update.message.reply_text("рџ“¦ Р РёС‚Р° СѓРїР°РєРѕРІС‹РІР°РµС‚ РґР»СЏ РїСѓР±Р»РёРєР°С†РёРё...")
        combined = r_human["telegram_humanized"] + "\n\n---\n\n" + r_human["instagram_humanized"]
        r_pub = publisher.run(topic, combined, r_strategist["strategy"], GEMINI_API_KEY)

        # Р¤РёРЅР°Р» вЂ” РѕС‚РїСЂР°РІР»СЏРµРј РІРµСЃСЊ РєРѕРЅС‚РµРЅС‚
        await update.message.reply_text("в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ\nвњ… РљРћРњРђРќР”Рђ Р—РђР’Р•Р РЁРР›Рђ Р РђР‘РћРўРЈ\nв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ")

        await send(update, f"рџ“± *TELEGRAM-РўР•РљРЎРў:*\n\n{r_human['telegram_humanized']}")
        await send(update, f"рџ“ё *INSTAGRAM-РљРћРќРўР•РќРў:*\n\n{r_human['instagram_humanized']}")
        await send(update, f"рџ“‹ *РЈРџРђРљРћР’РљРђ РћРў Р РРўР«:*\n\n{r_pub['final_content']}")

    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ /РїРѕСЃС‚")
        await update.message.reply_text(f"вќЊ РћС€РёР±РєР°: {e}")


async def cmd_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = " ".join(context.args).strip()
    if not product:
        await update.message.reply_text("РЈРєР°Р¶Рё РїСЂРѕРґСѓРєС‚: /offer Р›РёС‡РЅР°СЏ СЃРµСЃСЃРёСЏ СЃ Р”РјРёС‚СЂРёРµРј")
        return

    if not GEMINI_API_KEY:
        await update.message.reply_text("вќЊ GEMINI_API_KEY РЅРµ Р·Р°РґР°РЅ РІ .env")
        return

    await update.message.reply_text(f"рџЏ† Р’РёРєС‚РѕСЂ СЃС‚СЂРѕРёС‚ РѕС„С„РµСЂ РґР»СЏ:\nВ«{product}В»\n\nР­С‚Рѕ Р·Р°Р№РјС‘С‚ ~1 РјРёРЅСѓС‚Сѓ...")

    try:
        await update.message.reply_text("рџ”Ќ РЎРЅР°С‡Р°Р»Р° РќРёРЅР° Р°РЅР°Р»РёР·РёСЂСѓРµС‚ Р¦Рђ...")
        r_analyst = analyst.run(product, GEMINI_API_KEY)

        await update.message.reply_text("рџЏ† Р’РёРєС‚РѕСЂ СЃС‚СЂРѕРёС‚ РѕС„С„РµСЂ РїРѕ Hormozi...")
        r_offer = offer_architect.run(product, r_analyst["analysis"], GEMINI_API_KEY)

        await update.message.reply_text("в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ\nвњ… РћР¤Р¤Р•Р  Р“РћРўРћР’\nв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ")
        await send(update, f"рџЏ† *РћР¤Р¤Р•Р  вЂ” {product.upper()}*\n\n{r_offer['offer']}")

    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ /РѕС„С„РµСЂ")
        await update.message.reply_text(f"вќЊ РћС€РёР±РєР°: {e}")


async def cmd_architect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    focus = " ".join(context.args).strip() or None

    if not GEMINI_API_KEY:
        await update.message.reply_text("вќЊ GEMINI_API_KEY РЅРµ Р·Р°РґР°РЅ РІ .env")
        return

    msg = "рџ”§ РђР»РµРєСЃ РїСЂРѕРІРѕРґРёС‚ Р°СѓРґРёС‚ РєРѕРјР°РЅРґС‹..."
    if focus:
        msg += f"\nР¤РѕРєСѓСЃ: В«{focus}В»"
    await update.message.reply_text(msg)

    try:
        r = team_architect.run(GEMINI_API_KEY, focus=focus)
        await update.message.reply_text("в”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ\nрџ”§ РђРЈР”РРў РљРћРњРђРќР”Р«\nв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓв”Ѓ")
        await send(update, r["audit"])

    except Exception as e:
        logger.exception("РћС€РёР±РєР° РІ /Р°СЂС…РёС‚РµРєС‚РѕСЂ")
        await update.message.reply_text(f"вќЊ РћС€РёР±РєР°: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY:
        await update.message.reply_text("вќЊ GEMINI_API_KEY РЅРµ Р·Р°РґР°РЅ")
        return

    await update.message.reply_text("рџЋ¤ РџРѕР»СѓС‡РёР» РіРѕР»РѕСЃРѕРІРѕРµ. Р Р°СЃС€РёС„СЂРѕРІС‹РІР°СЋ...")

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
                "Р Р°СЃС€РёС„СЂСѓР№ СЌС‚Рѕ РіРѕР»РѕСЃРѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РґРѕСЃР»РѕРІРЅРѕ РЅР° СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµ. РўРѕР»СЊРєРѕ С‚РµРєСЃС‚, Р±РµР· РєРѕРјРјРµРЅС‚Р°СЂРёРµРІ."
            ]
        )
        transcript = response.text.strip()

        await update.message.reply_text(f"рџ“ќ *Р Р°СЃС€РёС„СЂРѕРІРєР°:*\n\n{transcript}", parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text(
            "Р§С‚Рѕ РґРµР»Р°С‚СЊ СЃ СЌС‚РёРј С‚РµРєСЃС‚РѕРј?\n\n"
            f"/post {transcript[:100]}... вЂ” СЃРѕР·РґР°С‚СЊ РїРѕСЃС‚\n"
            f"/offer {transcript[:100]}... вЂ” СЃРѕР·РґР°С‚СЊ РѕС„С„РµСЂ\n\n"
            "РР»Рё СЃРєРѕРїРёСЂСѓР№ РЅСѓР¶РЅСѓСЋ РєРѕРјР°РЅРґСѓ Рё Р·Р°РјРµРЅРё С‚РµРєСЃС‚ РЅР° СЃРІРѕР№."
        )

    except Exception as e:
        logger.exception("РћС€РёР±РєР° РїСЂРё РѕР±СЂР°Р±РѕС‚РєРµ РіРѕР»РѕСЃРѕРІРѕРіРѕ")
        await update.message.reply_text(f"вќЊ РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°СЃС€РёС„СЂРѕРІР°С‚СЊ: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("РљРѕРјР°РЅРґР° РЅРµ СЂР°СЃРїРѕР·РЅР°РЅР°. РќР°РїРёС€Рё /help РґР»СЏ СЃРїРёСЃРєР° РєРѕРјР°РЅРґ.")


def main():
    if not TELEGRAM_TOKEN:
        print("вќЊ TELEGRAM_BOT_TOKEN РЅРµ Р·Р°РґР°РЅ РІ .env")
        print("Р”РѕР±Р°РІСЊ СЃС‚СЂРѕРєСѓ: TELEGRAM_BOT_TOKEN=С‚РІРѕР№_С‚РѕРєРµРЅ_РѕС‚_BotFather")
        sys.exit(1)

    print("рџљЂ SMM-Р±РѕС‚ Р·Р°РїСѓСЃРєР°РµС‚СЃСЏ...")
    print(f"Gemini API: {'вњ… РЅР°СЃС‚СЂРѕРµРЅ' if GEMINI_API_KEY else 'вќЊ РЅРµ Р·Р°РґР°РЅ'}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["help", "start"], cmd_help))
    app.add_handler(CommandHandler("post", cmd_post))
    app.add_handler(CommandHandler("offer", cmd_offer))
    app.add_handler(CommandHandler("architect", cmd_architect))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("вњ… Р‘РѕС‚ Р·Р°РїСѓС‰РµРЅ. РќР°Р¶РјРё Ctrl+C РґР»СЏ РѕСЃС‚Р°РЅРѕРІРєРё.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
