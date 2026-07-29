"""Compact Telegram-only editorial team.

The full legacy multi-platform pipeline remains available in telegram_bot.py.
This module deliberately keeps five responsibilities separate and prompts short.
"""
import os
import re

from agents.gemini_utils import gemini_call
from agents import memory_utils, notebook_playbooks


MODEL = "gemini-2.5-flash"


def _notebook_context(role: str, live_context: str = "") -> str:
    """Use live Notebook guidance, with a strictly opt-in static fallback."""
    if live_context.strip():
        return (
            "\n\n═══ ЖИВОЙ ОТВЕТ GEMINI NOTEBOOK ДЛЯ ЭТОЙ ТЕМЫ ═══\n"
            + live_context.strip()
            + "\n═══ КОНЕЦ ЖИВОГО ОТВЕТА ═══\n"
        )
    if os.environ.get("NOTEBOOK_FALLBACK_ENABLED", "0") == "1":
        return notebook_playbooks.context_for(role)
    return ""

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
3. Что установить невозможно по имеющимся данным. Не перечисляй гипотезы
   возможных причин: просто обозначь границу знания.
4. Какие банальные трактовки темы лучше не использовать.

Не ставь диагнозов, не назначай читателю возраст, пол, профессию или внутреннюю проблему без данных.
Не придумывай исследования и не объясняй работу мозга, тела или нервной системы по общим представлениям.
Не предлагай объяснений внутреннего ощущения без отдельного источника. Работа
Нины — очистить материал от домыслов, а не составить меню возможных домыслов.
Если тема сформулирована как вопрос «почему», но фактов для ответа нет, не назначай одну причину даже в итоговом
фокусе. Сильный пост может не объяснять механизм, а научить различать наблюдение и поспешный вывод.
Не называй реакцию «естественной», «необходимой», «сигналом» или «потребностью психики», если это не подтверждено.
Маркетинговые и копирайтинговые блокноты не являются источником фактов о мозге,
теле или психике. Если отдельного научного источника во входных данных нет,
не предлагай даже как «возможные объяснения» переработку впечатлений, восстановление
ресурса, интеграцию опыта, гормональный спад, работу нервной системы или скрытые
ожидания. В таком случае честный результат исследования: наблюдение есть, причина
не установлена; дальше можно строить только пост-различение без объяснения механизма.
Формат ответа — строго четыре раздела: НАБЛЮДАЕМОЕ, ЯЗЫК ЧИТАТЕЛЯ,
НЕИЗВЕСТНО, БАНАЛЬНЫЕ ЛОВУШКИ. Не добавляй «возможные объяснения», «ключевую
мысль», готовый угол или рекомендации обратиться к ощущениям тела.
Дай короткую рабочую записку до 350 слов. Только материал, который поможет создать пост."""

STRATEGIST_PROMPT = """Ты — Артём, креативный стратег Telegram-канала Дмитрия Сучкова.
Твоя задача — найти не первую красивую мысль, а сильный и свежий смысловой угол.

Создай пять действительно разных углов. Они должны различаться конфликтом, точкой зрения и движением мысли,
а не только заголовками. Для каждого укажи: тезис, узнаваемую сцену, неожиданный поворот и риск банальности.
Сравни варианты с памятью недавних тем и образов. Затем выбери один.

Сцена может быть только наблюдением общего типа, если Дмитрий не передал реальный случай. Не придумывай имена,
диалоги, клиентов и биографические эпизоды. Не строй стратегию на утверждении, что ты точно знаешь скрытый мотив
читателя. Если причинность не подтверждена, формулируй её как одну из возможностей и сохраняй альтернативы.
Для одного наблюдения назови минимум две альтернативные причины и один факт, который мог бы опровергнуть выбранную
гипотезу. Если такого факта нет, не выбирай причинный угол: выбери угол-различение без объяснения механизма.

Без источника запрещено выдавать за факт, что психика «калибруется», «интегрирует», «просит», «защищает» или
«перерабатывает» опыт; что тело «протестует»; что тишина является сигналом глубины, подлинности или перегрузки.
Не используй компьютерную перезагрузку, карту и территорию, внутренний компас/голос/защитника как центральный образ.

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
АЛЬТЕРНАТИВЫ И ГРАНИЦА УВЕРЕННОСТИ
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

Каждый вариант: 900–1600 знаков, цельный текст без служебных комментариев, подзаголовков и хэштегов.
Начала, композиция и финалы должны реально отличаться. Не используй штампы вроде «это не про..., это про...»,
«важно понимать», «позволь себе», «в современном мире», а также рубленую псевдоглубину.

Не выдумывай именованных персонажей, цитаты, совещания, клиентов и случаи из жизни Дмитрия. Если нужен пример,
опиши его условно и коротко: «например, бывает...», не выдавая за реальное событие. Не объясняй за читателя,
что он «на самом деле» чувствует, выбирает или маскирует. Не делай нейробиологических заявлений без источника.
Слова «мозг», «нервная система», «гормоны» используй только для подтверждённого факта из исследования.
Если исходных данных нет, не разыгрывай длинную сцену от второго лица («вы входите... вы садитесь... вы думаете...»).
Не называй непроверенную реакцию калибровкой, интеграцией, ассимиляцией, защитой, сигналом или внутренней работой.
Не доказывай качество встречи самим желанием тишины. Оставляй альтернативы там, где их сохранила стратегия.
Одна мысль не должна пересказываться разными метафорами. Каждый абзац обязан добавлять новый шаг.

Иерархия входных данных: этический контроль и исправленная стратегия выше
исследовательской записки. Если в записке Нины остались «возможные причины» без
источника, полностью игнорируй их. Нельзя превращать осторожное «может быть» в
центральное объяснение поста. При отсутствии фактов пиши о различении:
наблюдение само по себе ещё не доказывает вывод.

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
- наблюдение не превращено в единственную причину без данных; альтернативные объяснения не исчезли;
- начало удерживает внимание, середина развивает мысль, финал не поучает;
- голос звучит как живой человек;
- вариант отличается от недавних постов по сцене, углу и ходу мысли.

Обязательно отправь на доработку, если есть хотя бы одно:
- выдуманный именованный герой, цитата или случай, которых не было в исходных данных;
- уверенное чтение мотивов читателя: «вы на самом деле...», «истинная причина...», «вы маскируете...»;
- псевдонаучное объяснение мозга, тела, гормонов или нервной системы без фактической опоры;
- слова «психика калибруется/интегрирует/просит», «тело протестует», «это сигнал глубины» или аналогичная
  неподтверждённая причинность;
- одна мысль повторена в трёх и более абзацах;
- набор AI-штампов и декоративных метафор вместо авторского наблюдения;
- объём выше 2200 знаков, который можно сократить без потери мысли.

Если вариант можно довести одной правкой, выбери его и дай конкретное задание автору. Не советуй заменять дефект
штампом «позвольте себе», «дайте себе пространство» или ещё одним обращением «вы». Не требуй идеальности.
Первая строка строго одна из:
РЕШЕНИЕ: ПРИНЯТО; ВАРИАНТ: А
РЕШЕНИЕ: ДОРАБОТАТЬ; ВАРИАНТ: А
(буква А, Б или В).
Далее не более пяти коротких пунктов: почему выбран и что исправить."""

VOICE_PROMPT = """Ты — Даша, хранитель голоса Дмитрия Сучкова.
Текст уже выбран редактором. Сделай только точечную стилистическую правку: убери канцелярит, AI-штампы,
неестественную гладкость и фразы, которые трудно произнести вслух. Сохрани тезис, факты, сцену, композицию,
длину и финальный смысл. Не добавляй новых метафор, диагнозов и утверждений. Верни только готовый пост."""

VOICE_NOTES_PROMPT = """Ты — Даша, консультант по голосу Дмитрия Сучкова.
Ты не переписываешь текст и не добавляешь новые идеи. Твоя задача — передать автору
не более трёх точных стилистических настроек: где фраза звучит неестественно,
слишком гладко, назидательно или не похожа на живую речь Дмитрия.

Каждая настройка должна указывать конкретный фрагмент или свойство текста.
Не обсуждай стратегию, факты, этику и композицию — за них отвечают другие роли.
Если серьёзных стилевых проблем нет, напиши одной строкой:
ГОЛОС: СОХРАНИТЬ КАК ЕСТЬ
"""

FINAL_ASSEMBLY_PROMPT = """Ты — Маша, единственный владелец окончательного текста.
Игорь уже выбрал черновик и указал содержательные правки. Даша дала только
стилистические настройки. Собери один окончательный Telegram-пост и больше не
передавай его другим авторам на переписывание.

Приоритеты:
1. Сохрани выбранный тезис и устрани замечания Игоря по существу.
2. Примени настройки Даши только к языку и ритму; не меняй ими смысл.
3. Не добавляй факты, причины, сцены, метафоры и личный опыт, которых нет во входе.
4. Один тезис, поступательное развитие, финал без диагноза и поучения.
5. 900–1550 знаков с пробелами; абсолютный максимум — 1750.

Верни только готовый пост без заголовка, отчёта, вариантов и комментариев."""

LENGTH_EDITOR_PROMPT = """Ты — технический редактор. Сожми готовый Telegram-пост
до 1100–1650 знаков с пробелами, сохранив центральный тезис, ход мысли и финал.
Убирай повторы, вводные слова и второстепенные примеры. Не добавляй новых фактов,
причин, метафор, советов или служебных комментариев. Верни только готовый пост."""

REPAIR_PROMPT = """Ты — Маша, автор, который исправляет один уже выбранный Telegram-пост по замечаниям редактора.
Верни один цельный готовый пост без заголовка «Вариант», комментариев и объяснений.

Исправь каждое замечание по существу. Сохрани тему и сильную часть угла, но понизь уверенность или убери причинное
объяснение, если оно не подтверждено. Не заменяй один штамп другим. Не добавляй сцен, цитат, личного опыта,
психологических механизмов и метафор, которых не было в достоверных входных данных.

Цель: 900–1600 знаков. Один тезис, короткое узнаваемое наблюдение, поступательное развитие, честная граница знания
и финал без поучения. Текст должен выдерживать чтение вслух и не обращаться к читателю в каждом абзаце."""

CLEAN_REWRITE_PROMPT = """Ты — старший автор Telegram-канала Дмитрия Сучкова.
Предыдущий текст провалил финальную проверку. Не латай его и не сохраняй его
метафоры. Напиши новый пост с чистого листа.

Жёсткие условия:
- 900–1400 знаков с пробелами;
- только готовый пост, 5–8 коротких абзацев;
- одно наблюдение само по себе ещё не доказывает одну интерпретацию;
- не объясняй причин желанием мозга, тела, психики, нервной системы, гормонов,
  интеграцией, переработкой, восстановлением ресурса или «внутренней работой»;
- не используй сосуд, инкубатор, лабораторию, склад, компьютер, файл, поток,
  калейдоскоп, компас, защитника, сигнал, маску и «энергию»;
- максимум две короткие фразы условной сцены; не выдумывай личный случай Дмитрия;
- не читай мысли читателя и не доказывай качество события его реакцией;
- вместо готовой причины предложи 2–3 конкретных различающих вопроса;
- без «давай честно», «позволь себе», «это не про X, это про Y» и поучения;
- финал — ясное различение, а не совет и не обещание.

Пиши просто, спокойно и разговорно. Верни только пост."""

STRATEGY_REPAIR_PROMPT = """Ты — Артём, стратег, который исправляет выбранную стратегию до написания текста.
Верни всю стратегию заново, но без недоказанных механизмов мозга, тела, психики,
гормонов, нервной системы, «интеграции опыта», «переработки впечатлений» и
компьютерных метафор.

Если фактов о причине нет, замени причинный тезис на честное различение:
одно и то же желание тишины не позволяет автоматически заключить, что встреча
разочаровала. Сохрани альтернативы и не выбирай одну скрытую причину.

В этой ситуации запрещено заменять одну недоказанную причину другой. Не пиши,
что реакция «естественна», «необходима», «часто встречается», является
«следствием», «признаком», «сигналом», «потребностью», «завершением глубокого
контакта» или доказывает насыщение/подлинность встречи.

Построй тезис в эпистемической форме:
«Само наблюдение X ещё не доказывает вывод Y».
Дальше дай читателю 2–3 проверяемых вопроса к ситуации: что конкретно понравилось,
что не понравилось, хотелось ли тишины ещё до встречи, изменилось ли отношение к
человеку после паузы. Никакого готового ответа за читателя.

Формат:
ВЫБОР
...
ТЕЗИС
...
СЦЕНА
...
ДВИЖЕНИЕ МЫСЛИ
...
АЛЬТЕРНАТИВЫ И ГРАНИЦА УВЕРЕННОСТИ
...
ФИНАЛ
...
"""

FINAL_REVIEW_PROMPT = """Ты — Света, финальный контролёр Telegram-канала Дмитрия Сучкова.
Проверь один готовый текст после редактора и стилистической правки. Не переписывай его.

Обязательно верни на доработку, если:
- текст утверждает одну скрытую психологическую причину без фактической опоры;
- наблюдение названо «калибровкой», «интеграцией», «сигналом», «защитой», «потребностью психики» как факт;
- придуманы сцена, диалог, биография, клиент или личный опыт;
- автор читает мысли читателя или диктует ему чувства;
- одна мысль повторяется, текст длиннее 1900 знаков, финал поучает;
- остались AI-штампы, повторяемые семейства образов или терапевтическое позиционирование;
- замечание предыдущего редактора не устранено по существу.

Первая строка строго:
ФИНАЛ: ПРИНЯТО
или
ФИНАЛ: ДОРАБОТАТЬ
Далее — до пяти коротких конкретных замечаний. Не предлагай новые факты или психологические объяснения."""


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


def research(topic: str, api_key: str, notebook_context: str = "") -> str:
    memory = memory_utils.load("analyst")
    context = memory_utils.build_context(memory, topic)
    system = (
        RESEARCHER_PROMPT + BRAND_BOUNDARY
        + _notebook_context("researcher", notebook_context) + context
    )
    return gemini_call(api_key, MODEL, system,
                       f"Тема поста: «{topic}»", max_tokens=1800, temperature=0.45,
                       disable_thinking=True)


def strategize(
    topic: str, research_note: str, api_key: str, notebook_context: str = ""
) -> str:
    memory = memory_utils.load("strategist")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nИсследовательская записка Нины:\n{research_note}"
    system = (
        STRATEGIST_PROMPT + BRAND_BOUNDARY
        + _notebook_context("strategist", notebook_context) + context
    )
    return gemini_call(api_key, MODEL, system, user_msg,
                       max_tokens=2600, temperature=0.8, disable_thinking=True)


def repair_strategy(
    topic: str, research_note: str, strategy: str, feedback: list[str],
    api_key: str, notebook_context: str = "",
) -> str:
    memory = memory_utils.load("strategist")
    context = memory_utils.build_context(memory, topic)
    user_msg = (
        f"Тема: «{topic}»\n\nИсследовательская записка:\n{research_note}\n\n"
        f"Стратегия с дефектами:\n{strategy}\n\n"
        "Обязательные исправления:\n- " + "\n- ".join(feedback)
    )
    system = (
        STRATEGY_REPAIR_PROMPT + BRAND_BOUNDARY
        + _notebook_context("strategist", notebook_context) + context
    )
    return gemini_call(
        api_key, MODEL, system, user_msg,
        max_tokens=2200, temperature=0.35, disable_thinking=True,
    ).strip()


def write(topic: str, research_note: str, strategy: str, api_key: str,
          feedback: str = None, previous_text: str = None, voice_samples: str = "",
          notebook_context: str = "") -> str:
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
    system = (
        WRITER_PROMPT + BRAND_BOUNDARY
        + _notebook_context("writer", notebook_context) + context
    )
    return gemini_call(api_key, MODEL, system, user_msg,
                       max_tokens=3500, temperature=0.85, disable_thinking=True)


def review(
    topic: str, strategy: str, variants: str, api_key: str,
    notebook_context: str = "",
) -> dict:
    memory = memory_utils.load("editor")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nСтратегия:\n{strategy}\n\nТри варианта:\n{variants}"
    system = (
        EDITOR_PROMPT + BRAND_BOUNDARY
        + _notebook_context("editor", notebook_context) + context
    )
    text = gemini_call(api_key, MODEL, system, user_msg,
                       max_tokens=1200, temperature=0.25, disable_thinking=True)
    first = text.strip().splitlines()[0].upper() if text.strip() else ""
    letter_match = re.search(r"ВАРИАНТ\s*:\s*([АБВ])", first)
    return {
        "accepted": "ПРИНЯТО" in first,
        "variant": letter_match.group(1) if letter_match else "А",
        "review": text,
    }


def advise_voice(
    topic: str, text: str, api_key: str, voice_samples: str = "",
    notebook_context: str = "",
) -> str:
    """Return bounded style notes; the voice role never rewrites the post."""
    memory = memory_utils.load("humanizer")
    context = memory_utils.build_context(memory, topic)
    user_msg = f"Тема: «{topic}»\n\nВыбранный черновик:\n{text}"
    if voice_samples:
        user_msg += (
            "\n\nОбразцы реальной речи Дмитрия — сравни только ритм, лексику и "
            "степень прямоты, ничего не копируй:\n" + voice_samples
        )
    system = (
        VOICE_NOTES_PROMPT + BRAND_BOUNDARY
        + _notebook_context("voice", notebook_context) + context
    )
    return gemini_call(
        api_key, MODEL, system, user_msg,
        max_tokens=500, temperature=0.2, disable_thinking=True,
    ).strip()


def assemble_final(
    topic: str,
    strategy: str,
    selected_draft: str,
    editor_notes: str,
    voice_notes: str,
    api_key: str,
    voice_samples: str = "",
    issues: list[str] | None = None,
    notebook_context: str = "",
) -> str:
    """One author owns the final text; critics supply notes but never rewrite."""
    memory = memory_utils.load("copywriter")
    context = memory_utils.build_context(memory, topic)
    user_msg = (
        f"Тема: «{topic}»\n\nУтверждённая стратегия:\n{strategy}\n\n"
        f"Выбранный черновик:\n{selected_draft}\n\n"
        f"Решение и правки Игоря:\n{editor_notes}\n\n"
        f"Настройки голоса Даши:\n{voice_notes}"
    )
    if issues:
        user_msg += (
            "\n\nАвтоматическая проверка нашла конкретные дефекты. Устрани их, "
            "не меняя владельца текста и не создавая новый смысл:\n- "
            + "\n- ".join(issues)
        )
    if voice_samples:
        user_msg += (
            "\n\nОбразцы реальной речи — используй только ритм и естественность, "
            "не копируй содержание:\n" + voice_samples
        )
    system = (
        FINAL_ASSEMBLY_PROMPT + BRAND_BOUNDARY
        + _notebook_context("writer", notebook_context) + context
    )
    return gemini_call(
        api_key, MODEL, system, user_msg,
        max_tokens=1700, temperature=0.4, disable_thinking=True,
    ).strip()


def fit_length(topic: str, text: str, api_key: str) -> str:
    """Mechanical one-shot compression; length alone must never kill a run."""
    return gemini_call(
        api_key,
        MODEL,
        LENGTH_EDITOR_PROMPT + BRAND_BOUNDARY,
        f"Тема: «{topic}»\n\nТекст для сокращения:\n{text}",
        max_tokens=1200,
        temperature=0.1,
        disable_thinking=True,
    ).strip()


def enforce_length(text: str, max_chars: int = 1850) -> str:
    """Last-resort deterministic fit that keeps the opening and conclusion."""
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean
    sentences = re.findall(
        r".+?[.!?…](?:[»\")]+)?(?=\s|$)",
        clean,
        flags=re.DOTALL,
    )
    if len(sentences) >= 2:
        conclusion = sentences[-1].strip()
        budget = max_chars - len(conclusion) - 2
        kept: list[str] = []
        used = 0
        for sentence in sentences[:-1]:
            normalized = " ".join(sentence.split())
            addition = len(normalized) + (1 if kept else 0)
            if used + addition > budget:
                break
            kept.append(normalized)
            used += addition
        candidate = " ".join(kept + [conclusion]).strip()
        if 350 <= len(candidate) <= max_chars:
            return candidate
    prefix = clean[:max_chars]
    boundary = max(
        prefix.rfind("."),
        prefix.rfind("!"),
        prefix.rfind("?"),
        prefix.rfind("…"),
    )
    return prefix[: boundary + 1].strip() if boundary >= 350 else prefix.rstrip() + "…"


def repair(topic: str, strategy: str, text: str, feedback: str, api_key: str,
           voice_samples: str = "", notebook_context: str = "") -> str:
    """Repair one selected draft instead of generating three more variants."""
    memory = memory_utils.load("copywriter")
    context = memory_utils.build_context(memory, topic)
    user_msg = (
        f"Тема: «{topic}»\n\nСтратегия:\n{strategy}\n\n"
        f"Выбранный текст:\n{text}\n\nЗамечания, которые нужно устранить:\n{feedback}"
    )
    if voice_samples:
        user_msg += (
            "\n\nРеальные публикации канала — используй только ритм и степень разговорности, "
            "не копируй фразы, сюжеты и выводы:\n" + voice_samples
        )
    system = (
        REPAIR_PROMPT + BRAND_BOUNDARY
        + _notebook_context("writer", notebook_context) + context
    )
    return gemini_call(
        api_key, MODEL, system, user_msg,
        max_tokens=2200, temperature=0.45, disable_thinking=True,
    ).strip()


def clean_rewrite(
    topic: str, strategy: str, rejected_text: str, feedback: str, api_key: str,
    voice_samples: str = "", notebook_context: str = "",
) -> str:
    """One clean-room rewrite after the final gate rejects patching."""
    memory = memory_utils.load("copywriter")
    context = memory_utils.build_context(memory, topic)
    user_msg = (
        f"Тема: «{topic}»\n\nСтратегия — возьми только безопасное различение, "
        f"не причинные объяснения:\n{strategy}\n\n"
        f"Почему предыдущий текст отклонён:\n{feedback}\n\n"
        f"Отклонённый текст — не копируй его образы и композицию:\n{rejected_text}"
    )
    if voice_samples:
        user_msg += (
            "\n\nОбразцы реальной речи — используй только естественность и ритм, "
            "не копируй содержание:\n" + voice_samples
        )
    system = (
        CLEAN_REWRITE_PROMPT + BRAND_BOUNDARY
        + _notebook_context("writer", notebook_context) + context
    )
    return gemini_call(
        api_key, MODEL, system, user_msg,
        max_tokens=1200, temperature=0.45, disable_thinking=True,
    ).strip()


def final_review(topic: str, strategy: str, text: str, api_key: str,
                 previous_review: str = "", notebook_context: str = "") -> dict:
    """Independent final gate after editing and voice polish."""
    memory = memory_utils.load("editor")
    context = memory_utils.build_context(memory, topic)
    deterministic = validate_post(text) + quality_warnings(text)
    user_msg = (
        f"Тема: «{topic}»\n\nСтратегия:\n{strategy}\n\n"
        f"Финальный текст:\n{text}"
    )
    if previous_review:
        user_msg += f"\n\nПредыдущее замечание редактора:\n{previous_review}"
    if deterministic:
        user_msg += "\n\nАвтоматические замечания:\n- " + "\n- ".join(deterministic)
    system = (
        FINAL_REVIEW_PROMPT + BRAND_BOUNDARY
        + _notebook_context("editor", notebook_context) + context
    )
    review_text = gemini_call(
        api_key, MODEL, system, user_msg,
        max_tokens=1000, temperature=0.1, disable_thinking=True,
    ).strip()
    first = review_text.splitlines()[0].upper() if review_text else ""
    if deterministic:
        review_text += (
            "\n\nАВТОМАТИЧЕСКИЙ ВОЗВРАТ:\n- "
            + "\n- ".join(deterministic)
        )
    return {
        "accepted": "ФИНАЛ: ПРИНЯТО" in first and not deterministic,
        "review": review_text,
    }


def polish(
    topic: str, text: str, api_key: str, voice_samples: str = "",
    issues: list = None, notebook_context: str = "",
) -> str:
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
    system = (
        VOICE_PROMPT + BRAND_BOUNDARY
        + _notebook_context("voice", notebook_context) + context
    )
    return gemini_call(api_key, MODEL, system, user_msg,
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
    # The author requested compact Telegram posts; this is a delivery gate.
    if len(clean) > 1900:
        errors.append("текст длиннее 1900 знаков")
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
        "убери шаблон «давай честно»": r"\bдавай(?:те)?\s+честно\b",
        "убери шаблон «вот в чём штука/засада»": r"\bвот\s+в\s+ч[её]м\s+(?:штука|засада)\b",
        "убери шаблон «если узнаёшь себя»": r"\bесли\s+узна[её]шь\s+себя\b",
        "не утверждай скрытый мотив читателя как факт": r"\b(?:вы|ты)\s+(?:на самом деле|просто маскиру|в действительности)",
        "убери формулу об «истинной причине»": r"\bистинн(?:ая|ую|ой)\s+причин",
        "убери штамп «важно понимать»": r"\bважно\s+понимать\b",
        "убери штамп «позволь себе»": r"\bпозволь(?:те)?\s+себе\b",
        "убери штамп «в современном мире»": r"\bв\s+современном\s+мире\b",
        "убери неподтверждённый механизм «психика калибруется/интегрирует/просит»": r"\bпсихик\w*\b.{0,60}\b(?:калибр|интегр|ассимил|просит|перерабат)\w*",
        "не называй телесную реакцию протестом без источника": r"\bтел[оа]\b.{0,50}\bпротест\w*",
        "не объявляй наблюдение естественным и необходимым этапом": r"\bестественн\w*\s+(?:и\s+)?необходим\w*\s+(?:этап|фаз|процесс)\w*",
        "не доказывай глубину встречи желанием тишины": r"\bтишин\w*\b.{0,100}\bсигнал\w*.{0,80}\b(?:глуб|подлин|насыщ)\w*",
        "не используй метафору мозга-стратега или мозга-тактика как факт": r"\bмозг\b.{0,100}\b(?:стратег|тактик)\w*",
        "не приписывай мозгу недоказанную обработку и сортировку впечатлений": r"\bмозг\w*\b.{0,180}\b(?:обработ|сортир|интегр|встраив|архив|индекс|перерабат|созда[её]т\s+нов\w*\s+связ)\w*",
        "убери недоказанную «переработку/интеграцию» впечатлений или опыта": r"\b(?:переработ|интегр|встраив|ассимил)\w*.{0,100}\b(?:впечатлен|опыт|информац|памят)\w*",
        "убери компьютерно-логистическую метафору внутренней работы": r"\b(?:обмен\s+данн|распак|архивир|индексир|сохран\w*\s+файл|внутренн\w*\s+склад|разлож\w*\s+по\s+папк)\w*",
        "не объявляй реакцию естественной потребностью без источника": r"\bестественн\w*.{0,80}\bпотребност\w*",
        "не называй желание тишины сигналом установленного механизма": r"\b(?:тишин|желани\w*\s+тишин|опустошени)\w*.{0,120}\bсигнал\w*|\bсигнал\w*.{0,120}\b(?:тишин|опустошени)\w*",
        "замени повторяемый образ внутреннего защитника/компаса/голоса": r"\bвнутренн\w*\s+(?:защитник|страж|охранник|компас|голос|будильник|датчик)\w*\b",
        "убери телесный штамп про броню, панцирь или камень в груди": r"\b(?:мышечн\w*\s+панцир|брон[яеию]|камень\s+в\s+груди)\b",
        "не позиционируй Дмитрия как соматического терапевта": r"\b(?:соматическ\w*\s+терапевт\w*|соматотерапевт\w*|somatic\s+therapist)\b",
    }
    lowered = clean.lower()
    for message, pattern in patterns.items():
        if re.search(pattern, lowered, re.DOTALL):
            warnings.append(message)
    if len(clean) > 1900:
        warnings.append("сократи до 1200–1800 знаков без потери центральной мысли")
    second_person_openings = len(re.findall(r"(?m)^\s*(?:вы|ты)\b", lowered))
    if second_person_openings >= 4:
        warnings.append("не начинай четыре и более абзаца с обращения «вы/ты»")
    if len(re.findall(r"\b(?:вы|ты)\b", lowered)) >= 8:
        warnings.append("убери длинную выдуманную сцену от второго лица и оставь одно короткое наблюдение")
    if len(re.findall(r"\bвнутренн\w*\b", lowered)) >= 5:
        warnings.append("убери навязчивый повтор слова «внутренний» и оставь одно точное наблюдение")
    return warnings


def blocking_quality_warnings(text: str) -> list[str]:
    """Separate safety/brand defects from subjective style preferences.

    Style warnings are useful input to the single final author, but must not
    start an endless rewrite loop. Only claims that can mislead or violate the
    brand boundary remain delivery blockers.
    """
    blocking_markers = (
        "скрытый мотив",
        "истинной причине",
        "неподтверждённый механизм",
        "без источника",
        "недоказанную",
        "не приписывай мозгу",
        "метафору мозга-стратега",
        "телесную реакцию",
        "не объявляй наблюдение",
        "не объявляй реакцию",
        "не доказывай глубину встречи",
        "сигналом установленного механизма",
        "не позиционируй Дмитрия",
    )
    return [
        warning
        for warning in quality_warnings(text)
        if any(marker in warning for marker in blocking_markers)
    ]


def strategy_warnings(text: str) -> list[str]:
    """Hard signals that make a strategy unsafe before drafting starts."""
    lowered = text.lower()
    patterns = {
        "убрать гормоны и нейромедиаторы без научного источника": r"\b(?:гормон|дофамин|серотонин|кортизол)\w*",
        "убрать эволюционный механизм без научного источника": r"\bэволюционн\w*.{0,60}\bмеханизм\w*",
        "убрать интеграцию и переработку опыта как установленную причину": r"\b(?:интегр|перерабат|обработ|встраив|архивир|индексир)\w*.{0,120}\b(?:опыт|впечатлен|информац|событ)\w*",
        "не приписывать мозгу сортировку, сохранение или создание связей": r"\bмозг\w*.{0,160}\b(?:сортир|сохран|созда[её]т|обработ|уклад|встраив|интегр)\w*",
        "убрать компьютерную метафору психики": r"\b(?:перезагруз|сохран\w*\s+файл|архивир|индексир|обмен\s+данн|инсталляц|процессор)\w*",
        "не объявлять желание тишины естественной необходимой реакцией": r"\b(?:естественн|необходим)\w*.{0,100}\b(?:реакц|процесс|потребност|фаз)\w*",
    }
    return [
        message
        for message, pattern in patterns.items()
        if re.search(pattern, lowered, re.DOTALL)
    ]
