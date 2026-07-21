"""Compact Telegram-only editorial team.

The full legacy multi-platform pipeline remains available in telegram_bot.py.
This module deliberately keeps five responsibilities separate and prompts short.
"""
import re

from agents.gemini_utils import gemini_call
from agents import memory_utils


MODEL = "gemini-2.5-flash"

RESEARCHER_PROMPT = """Ты — Нина, исследователь аудитории Telegram-канала Дмитрия Сучкова.
Твоя работа — дать автору фактическую опору, а не придумать психологический портрет читателя.

Разделяй:
1. Что точно следует из темы и переданных данных.
2. Какие формулировки и жизненные ситуации могут быть узнаваемы читателю.
3. Что является только гипотезой и требует осторожной подачи.
4. Какие банальные трактовки темы лучше не использовать.

Не ставь диагнозов, не назначай читателю возраст, пол, профессию или внутреннюю проблему без данных.
Дай короткую рабочую записку до 500 слов. Только материал, который поможет создать пост."""

STRATEGIST_PROMPT = """Ты — Артём, креативный стратег Telegram-канала Дмитрия Сучкова.
Твоя задача — найти не первую красивую мысль, а сильный и свежий смысловой угол.

Создай пять действительно разных углов. Они должны различаться конфликтом, точкой зрения и движением мысли,
а не только заголовками. Для каждого укажи: тезис, узнаваемую сцену, неожиданный поворот и риск банальности.
Сравни варианты с памятью недавних тем и образов. Затем выбери один.

Выбранная стратегия обязана содержать:
- одну центральную мысль;
- что читатель сначала думает и что увидит к финалу;
- одну конкретную сцену или наблюдение;
- допустимый уровень уверенности, без психологических диагнозов;
- направление финала и мягкого действия читателя.

Не пиши сам пост и не превращай стратегию в перечень запретов. Формат ответа:
УГЛЫ
1. ...
...
ВЫБОР
...
ТЕЗИС
...
СЦЕНА
...
ДВИЖЕНИЕ МЫСЛИ
...
ФИНАЛ
..."""

WRITER_PROMPT = """Ты — Маша, автор Telegram-канала Дмитрия Сучкова.
Пиши живо, точно и по-человечески. Не изображай терапевта, не диагностируй читателя и не объясняй ему,
что он якобы чувствует. Опирайся на конкретные сцены, наблюдения и одну выбранную мысль.

Создай три самостоятельных варианта одного поста:
А — прямой разговорный;
Б — образный, но без тумана и красивости ради красивости;
В — сюжетный, через конкретную сцену.

Каждый вариант: 900–1800 знаков, цельный текст без служебных комментариев, подзаголовков и хэштегов.
Начала, композиция и финалы должны реально отличаться. Не используй штампы вроде «это не про..., это про...»,
«важно понимать», «позволь себе», «в современном мире», а также рубленую псевдоглубину.

Формат строго:
ВАРИАНТ А
<текст>

ВАРИАНТ Б
<текст>

ВАРИАНТ В
<текст>"""

EDITOR_PROMPT = """Ты — Игорь, выпускающий редактор Telegram-канала Дмитрия Сучкова.
Выбери лучший из трёх вариантов. Не переписывай стратегию и не отклоняй всю тему.

Проверь только существенное:
- текст отвечает исходной теме и держит один тезис;
- есть конкретика, а не абстрактная психологическая речь;
- нет диагнозов, переноса вины на читателя и ложной причинности;
- начало удерживает внимание, середина развивает мысль, финал не поучает;
- голос звучит как живой человек;
- вариант отличается от недавних постов по сцене, углу и ходу мысли.

Если вариант можно довести одной правкой, выбери его и дай конкретное задание автору. Не требуй идеальности.
Первая строка строго одна из:
РЕШЕНИЕ: ПРИНЯТО; ВАРИАНТ: А
РЕШЕНИЕ: ДОРАБОТАТЬ; ВАРИАНТ: А
(буква А, Б или В).
Далее не более пяти коротких пунктов: почему выбран и что исправить."""

VOICE_PROMPT = """Ты — Даша, хранитель голоса Дмитрия Сучкова.
Текст уже выбран редактором. Сделай только точечную стилистическую правку: убери канцелярит, AI-штампы,
неестественную гладкость и фразы, которые трудно произнести вслух. Сохрани тезис, факты, сцену, композицию,
длину и финальный смысл. Не добавляй новых метафор, диагнозов и утверждений. Верни только готовый пост."""


def research(topic: str, api_key: str) -> str:
    memory = memory_utils.load("analyst")
    context = memory_utils.build_context(memory, topic)
    return gemini_call(api_key, MODEL, RESEARCHER_PROMPT + context,
                       f"Тема поста: «{topic}»", max_tokens=1800, temperature=0.45,
                       disable_thinking=True)


def strategize(topic: str, research_note: str, api_key: str) -> str:
    memory = memory_utils.load("strategist")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nИсследовательская записка Нины:\n{research_note}"
    return gemini_call(api_key, MODEL, STRATEGIST_PROMPT + context, user_msg,
                       max_tokens=2600, temperature=0.8, disable_thinking=True)


def write(topic: str, research_note: str, strategy: str, api_key: str,
          feedback: str = None, previous_text: str = None) -> str:
    memory = memory_utils.load("copywriter")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nИсследование:\n{research_note}\n\nСтратегия:\n{strategy}"
    if feedback:
        user_msg += f"\n\nПравка редактора или Дмитрия:\n{feedback}"
    if previous_text:
        user_msg += f"\n\nПредыдущий текст для точечной доработки:\n{previous_text}"
    return gemini_call(api_key, MODEL, WRITER_PROMPT + context, user_msg,
                       max_tokens=3500, temperature=0.85, disable_thinking=True)


def review(topic: str, strategy: str, variants: str, api_key: str) -> dict:
    memory = memory_utils.load("editor")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nСтратегия:\n{strategy}\n\nТри варианта:\n{variants}"
    text = gemini_call(api_key, MODEL, EDITOR_PROMPT + context, user_msg,
                       max_tokens=1200, temperature=0.25, disable_thinking=True)
    first = text.strip().splitlines()[0].upper() if text.strip() else ""
    letter_match = re.search(r"ВАРИАНТ\s*:\s*([АБВ])", first)
    return {
        "accepted": "ПРИНЯТО" in first,
        "variant": letter_match.group(1) if letter_match else "А",
        "review": text,
    }


def polish(topic: str, text: str, api_key: str) -> str:
    memory = memory_utils.load("humanizer")
    context = memory_utils.build_context(memory, topic)
    return gemini_call(api_key, MODEL, VOICE_PROMPT + context,
                       f"Тема: «{topic}»\n\nОдобренный текст:\n{text}",
                       max_tokens=2200, temperature=0.35, disable_thinking=True).strip()


def extract_variant(variants: str, letter: str) -> str:
    letters = "АБВ"
    letter = letter if letter in letters else "А"
    pattern = rf"(?:^|\n)\s*ВАРИАНТ\s+{letter}\s*\n(.*?)(?=\n\s*ВАРИАНТ\s+[АБВ]\s*\n|\Z)"
    match = re.search(pattern, variants, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return variants.strip()


def validate_post(text: str) -> list[str]:
    errors = []
    clean = text.strip()
    if len(clean) < 350:
        errors.append("текст короче 350 знаков")
    if len(clean) > 2200:
        errors.append("текст длиннее 2200 знаков")
    if re.search(r"(?:^|\n)\s*(ВАРИАНТ|РЕШЕНИЕ|КОММЕНТАРИЙ)\b", clean, re.IGNORECASE):
        errors.append("в тексте осталась служебная разметка")
    if clean and clean[-1] not in ".!?…»\")":
        errors.append("последнее предложение выглядит оборванным")
    return errors
