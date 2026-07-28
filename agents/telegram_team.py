"""Compact Telegram-only editorial team.

The full legacy multi-platform pipeline remains available in telegram_bot.py.
This module deliberately keeps five responsibilities separate and prompts short.
"""
import re

from agents.gemini_utils import gemini_call
from agents import memory_utils


MODEL = "gemini-2.5-flash"

# This is a hard brand boundary, not a stylistic preference. Keep it in the
# shared context so every editorial role sees the same positioning rule.
BRAND_BOUNDARY = """ЖЁСТКОЕ БРЕНДОВОЕ ОГРАНИЧЕНИЕ:
Не позиционируй Дмитрия как «соматического терапевта» или «соматотерапевта».
Не строй пост вокруг терапевтической или диагностической роли, лечения,
исцеления или клинической услуги. Если исходный материал использует такую
рамку, перенеси только наблюдение или смысл, а роль замени на авторский
подход Дмитрия, практику, движение, внимание или опыт — без ложного обещания.
Не маскируй запрещённую роль синонимами. Если тема держится только на ней,
верни предупреждение редактору и предложи заменить смысловой угол.
"""

RESEARCHER_PROMPT = """Ты — Нина, исследователь аудитории Telegram-канала Дмитрия Сучкова.
Твоя работа — дать автору фактическую опору, а не придумать психологический портрет читателя.

Разделяй:
1. Что точно следует из темы и переданных данных.
2. Какие формулировки и жизненные ситуации могут быть узнаваемы читателю.
3. Что является только гипотезой и требует осторожной подачи.
4. Какие банальные трактовки темы лучше не использовать.

Не ставь диагнозов, не назначай читателю возраст, пол, профессию или внутреннюю проблему без данных.
Не придумывай исследования и не объясняй работу мозга, тела или нервной системы по общим представлениям.
Для любого внутреннего ощущения дай несколько возможных объяснений и не выбирай одно без основания.
Дай короткую рабочую записку до 500 слов. Только материал, который поможет создать пост."""

STRATEGIST_PROMPT = """Ты — Артём, креативный стратег Telegram-канала Дмитрия Сучкова.
Твоя задача — найти не первую красивую мысль, а сильный и свежий смысловой угол.

Создай пять действительно разных углов. Они должны различаться конфликтом, точкой зрения и движением мысли,
а не только заголовками. Для каждого укажи: тезис, узнаваемую сцену, неожиданный поворот и риск банальности.
Сравни варианты с памятью недавних тем и образов. Затем выбери один.

Сцена может быть только наблюдением общего типа, если Дмитрий не передал реальный случай. Не придумывай имена,
диалоги, клиентов и биографические эпизоды. Не строй стратегию на утверждении, что ты точно знаешь скрытый мотив
читателя. Если причинность не подтверждена, формулируй её как одну из возможностей и сохраняй альтернативы.

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

Не выдумывай именованных персонажей, цитаты, совещания, клиентов и случаи из жизни Дмитрия. Если нужен пример,
опиши его условно и коротко: «например, бывает...», не выдавая за реальное событие. Не объясняй за читателя,
что он «на самом деле» чувствует, выбирает или маскирует. Не делай нейробиологических заявлений без источника.
Слова «мозг», «нервная система», «гормоны» используй только для подтверждённого факта из исследования.
Одна мысль не должна пересказываться разными метафорами. Каждый абзац обязан добавлять новый шаг.

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

Обязательно отправь на доработку, если есть хотя бы одно:
- выдуманный именованный герой, цитата или случай, которых не было в исходных данных;
- уверенное чтение мотивов читателя: «вы на самом деле...», «истинная причина...», «вы маскируете...»;
- псевдонаучное объяснение мозга, тела, гормонов или нервной системы без фактической опоры;
- одна мысль повторена в трёх и более абзацах;
- набор AI-штампов и декоративных метафор вместо авторского наблюдения;
- объём выше 2200 знаков, который можно сократить без потери мысли.

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


def build_voice_samples(posts: list, limit: int = 5) -> str:
    """Build a compact style-only reference from real channel publications."""
    samples = []
    for post in posts or []:
        text = (post.get("text") or "").strip()
        if len(text) < 120:
            continue
        excerpt = text[:500]
        if len(text) > 500:
            boundary = max(excerpt.rfind("."), excerpt.rfind("!"), excerpt.rfind("?"), excerpt.rfind("…"))
            if boundary >= 250:
                excerpt = excerpt[:boundary + 1]
        samples.append(excerpt)
        if len(samples) >= limit:
            break
    if not samples:
        return ""
    return "\n\n--- РЕАЛЬНЫЙ ПОСТ ---\n".join(samples)


def research(topic: str, api_key: str) -> str:
    memory = memory_utils.load("analyst")
    context = memory_utils.build_context(memory, topic)
    return gemini_call(api_key, MODEL, RESEARCHER_PROMPT + BRAND_BOUNDARY + context,
                       f"Тема поста: «{topic}»", max_tokens=1800, temperature=0.45,
                       disable_thinking=True)


def strategize(topic: str, research_note: str, api_key: str) -> str:
    memory = memory_utils.load("strategist")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nИсследовательская записка Нины:\n{research_note}"
    return gemini_call(api_key, MODEL, STRATEGIST_PROMPT + BRAND_BOUNDARY + context, user_msg,
                       max_tokens=2600, temperature=0.8, disable_thinking=True)


def write(topic: str, research_note: str, strategy: str, api_key: str,
          feedback: str = None, previous_text: str = None, voice_samples: str = "") -> str:
    memory = memory_utils.load("copywriter")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nИсследование:\n{research_note}\n\nСтратегия:\n{strategy}"
    if feedback:
        user_msg += f"\n\nПравка редактора или Дмитрия:\n{feedback}"
    if previous_text:
        user_msg += f"\n\nПредыдущий текст для точечной доработки:\n{previous_text}"
    if voice_samples:
        user_msg += (
            "\n\nОБРАЗЦЫ РЕАЛЬНЫХ ПУБЛИКАЦИЙ КАНАЛА — используй только ритм, степень разговорности "
            "и способ обращения. Не копируй фразы, сюжеты, утверждения и ошибки:\n" + voice_samples
        )
    return gemini_call(api_key, MODEL, WRITER_PROMPT + BRAND_BOUNDARY + context, user_msg,
                       max_tokens=3500, temperature=0.85, disable_thinking=True)


def review(topic: str, strategy: str, variants: str, api_key: str) -> dict:
    memory = memory_utils.load("editor")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nСтратегия:\n{strategy}\n\nТри варианта:\n{variants}"
    text = gemini_call(api_key, MODEL, EDITOR_PROMPT + BRAND_BOUNDARY + context, user_msg,
                       max_tokens=1200, temperature=0.25, disable_thinking=True)
    first = text.strip().splitlines()[0].upper() if text.strip() else ""
    letter_match = re.search(r"ВАРИАНТ\s*:\s*([АБВ])", first)
    return {
        "accepted": "ПРИНЯТО" in first,
        "variant": letter_match.group(1) if letter_match else "А",
        "review": text,
    }


def polish(topic: str, text: str, api_key: str, voice_samples: str = "", issues: list = None) -> str:
    memory = memory_utils.load("humanizer")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nОдобренный текст:\n{text}"
    if voice_samples:
        user_msg += (
            "\n\nРЕАЛЬНЫЕ ПУБЛИКАЦИИ КАНАЛА — сравни ритм и естественность, но ничего не копируй:\n"
            + voice_samples
        )
    if issues:
        user_msg += "\n\nОБЯЗАТЕЛЬНО УСТРАНИ:\n- " + "\n- ".join(issues)
    return gemini_call(api_key, MODEL, VOICE_PROMPT + BRAND_BOUNDARY + context, user_msg,
                       max_tokens=2200, temperature=0.35, disable_thinking=True).strip()


def extract_variant(variants: str, letter: str) -> str:
    """Extract one draft despite Markdown headings or descriptive suffixes.

    Never return all three drafts when recognizable variant headings are present.
    """
    letters = "АБВ"
    letter = letter if letter in letters else "А"
    header = re.compile(
        r"(?:^|\n)\s*(?:#{1,6}\s*)?(?:\*{1,2}|_{1,2})?\s*"
        r"ВАРИАНТ\s+([АБВ])\s*(?:\*{1,2}|_{1,2})?\s*"
        r"(?:(?:[:—-])[^\n]*)?\n",
        re.IGNORECASE,
    )
    matches = list(header.finditer(variants))
    sections = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(variants)
        sections[match.group(1).upper()] = variants[start:end].strip()
    if sections:
        return sections.get(letter) or next(iter(sections.values()))
    return variants.strip()


def validate_post(text: str) -> list[str]:
    errors = []
    clean = text.strip()
    if len(clean) < 350:
        errors.append("текст короче 350 знаков")
    # 900–1800 is the editorial target; 3800 is the hard delivery guardrail.
    if len(clean) > 3800:
        errors.append("текст длиннее 3800 знаков")
    if re.search(r"\bсоматическ\w*\s+терапевт\w*\b|\bсоматотерапевт\w*\b|\bsomatic\s+therapist\b", clean, re.IGNORECASE):
        errors.append("нарушена брендовая граница: позиционирование как соматического терапевта")
    if re.search(r"(?:^|\n)\s*(ВАРИАНТ|РЕШЕНИЕ|КОММЕНТАРИЙ)\b", clean, re.IGNORECASE):
        errors.append("в тексте осталась служебная разметка")
    if clean and clean[-1] not in ".!?…»\")":
        errors.append("последнее предложение выглядит оборванным")
    return errors


def quality_warnings(text: str) -> list[str]:
    """Cheap deterministic signals for patterns the editorial pass must revisit."""
    clean = text.strip()
    warnings = []
    patterns = {
        "убери конструкцию «это не про..., это про...»": r"это\s+не\s+про.{0,80}это\s+про",
        "не утверждай скрытый мотив читателя как факт": r"\b(?:вы|ты)\s+(?:на самом деле|просто маскиру|в действительности)",
        "убери формулу об «истинной причине»": r"\bистинн(?:ая|ую|ой)\s+причин",
        "убери штамп «важно понимать»": r"\bважно\s+понимать\b",
        "убери штамп «позволь себе»": r"\bпозволь(?:те)?\s+себе\b",
        "убери штамп «в современном мире»": r"\bв\s+современном\s+мире\b",
        "не используй метафору мозга-стратега или мозга-тактика как факт": r"\bмозг\b.{0,100}\b(?:стратег|тактик)\w*",
        "не позиционируй Дмитрия как соматического терапевта": r"\b(?:соматическ\w*\s+терапевт\w*|соматотерапевт\w*|somatic\s+therapist)\b",
    }
    lowered = clean.lower()
    for message, pattern in patterns.items():
        if re.search(pattern, lowered, re.DOTALL):
            warnings.append(message)
    if len(clean) > 2200:
        warnings.append("сократи до 1800–2200 знаков без потери центральной мысли")
    return warnings
