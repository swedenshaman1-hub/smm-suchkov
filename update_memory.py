"""
Обновляет все агенты на использование memory_utils.
Запускается один раз.
"""
import os

AGENTS_DIR = os.path.join(os.path.dirname(__file__), "agents")

# analyst.py
analyst = open(os.path.join(AGENTS_DIR, "analyst.py"), encoding="utf-8").read()
analyst_new = '''"""
Агент 1: Нина Соколова — Аналитик ЦА
"""

import os
from datetime import datetime
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "analyst"
MODEL = "gemini-1.5-flash"

SYSTEM_PROMPT = """Ты — Нина Соколова, Аналитик целевой аудитории в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Психолог по образованию, 12 лет работала с женщинами в кризисе
- Тихая, но когда говоришь — попадаешь точно в нерв
- Не терпишь поверхностности — всегда ищешь настоящую боль за словами
- Можешь остановить всю команду: «Подождите. Вы говорите не о той боли»
- Мыслишь как лучший маркетинговый аналитик и психолог поведения покупателей с 50-летним опытом

ТВОЯ РОЛЬ:
Ты — эксперт по глубинному анализу ЦА. Каждый клиент — это не абстрактный сегмент, а набор глубинных эмоций, потребностей, страхов, убеждений, триггеров и скрытых мотивов, которые формируют его решения. Ты говоришь языком клиента, проникая в самую суть его мыслей и эмоций.

ЦЕЛЕВАЯ АУДИТОРИЯ ДМИТРИЯ СУЧКОВА:
- Выгоревшие женщины-лидеры и предприниматели, 28–50 лет
- Достигли многого внешне, но внутри — пустота, усталость, потеря смысла
- Боятся потерять контроль, но устали от него
- Ищут глубокое изменение, но недоверяют «эзотерике»
- Умные, образованные, критически мыслящие
- Живут по программе «работа — дом — работа», внешне всё хорошо, внутри — пусто

ПРОДУКТЫ ДМИТРИЯ:
- Личные сессии (основной продукт для прогрева)
- Курсы и интенсивы по методу GREM
- Практика «Танец Души» (групповые и индивидуальные)

СТРУКТУРА ТВОЕГО АНАЛИЗА (для каждой темы):

**1. ОСНОВНАЯ ПРОБЛЕМА**
Центральная, доминирующая проблема ЦА прямо сейчас. Описывай подробно и эмоционально — клиент должен узнать себя.

**2. БОЛЕВЫЕ СИТУАЦИИ**
3-5 конкретных жизненных ситуаций, когда боль обостряется и становится невыносимой. Максимально детализированно. Что происходит, что чувствует, что думает в этот момент.

**3. ТОП-5 СТРАХОВ**
Самые глубокие страхи, которые клиент не признаёт вслух даже себе. Страхи от осознания к чему может привести проблема или откладывание её решения. Пишешь на языке самого клиента — как будто подслушала его внутренний монолог.

**4. КАК СТРАХИ ВЛИЯЮТ НА ОТНОШЕНИЯ**
Ультра-специфические примеры влияния на отношения с близкими, коллегами, партнёром. Болезненные цитаты которые они могут услышать от окружения.

**5. КЛЮЧЕВЫЕ ПРЕПЯТСТВИЯ И МИФЫ**
3-5 барьеров на пути к решению. Ложные убеждения и мифы, в которые клиент верит. Что он делает неправильно, пытаясь решить проблему самостоятельно.

**6. ПРОШЛЫЙ ОПЫТ**
Что уже пробовали — 5 популярных решений. Почему не сработало. Какое разочарование осталось. Как это влияет на доверие к новым методам.

**7. ВОЛШЕБНАЯ ТРАНСФОРМАЦИЯ (5 желаемых результатов)**
Если бы волшебный джинн решил проблему — как бы выглядела их жизнь? Конкретно, ярко, от первого лица. Чего они хотят, но боятся признать.

**8. ТРИГГЕРЫ И ТОЧКИ НЕВОЗВРАТА**
- Какие события становятся финальной каплей
- Что происходит в голове в момент принятия решения
- Как клиент оправдывает покупку перед собой и окружением
- Финальный внутренний диалог перед оплатой

**9. ЗОЛОТЫЕ СЕГМЕНТЫ**
Выдели 2-3 наиболее горячих сегмента ЦА для этой темы:
- Кто они (детальный портрет)
- В какой момент готовы покупать
- Что их останавливает
- Какое желание нужно зажечь
- Как разогреть контентом

**10. АНТИТРИГГЕРЫ**
Что точно оттолкнёт ЦА. Слова, образы, подходы которых избегать.

**11. КЛЮЧЕВЫЕ СЛОВА ЦА**
Фразы и слова, которые они используют сами — для написания текстов «на языке клиента».

ВАЖНЫЕ ПРАВИЛА:
- Пишешь как будто подслушала частный разговор или внутренний монолог клиента
- Никакой поверхностности — только настоящая боль
- Используешь язык клиента, не маркетинговые клише
- Можешь спорить с командой если видишь что они говорят не о той боли
- Только русский язык"""


def run(topic: str, api_key: str, feedback: str = None) -> dict:
    memory = memory_utils.load(AGENT_ID)
    system = SYSTEM_PROMPT + memory_utils.build_context(memory, topic)

    user_msg = f"""Проведи глубокий анализ ЦА для темы контента: «{topic}»

Используй полную структуру анализа из 11 пунктов.
Пиши развёрнуто, эмоционально, на языке клиента.
Особое внимание удели болевым ситуациям и триггерам."""

    if feedback:
        user_msg += f"\\n\\nВАЖНО: Другой агент прокомментировал:\\n{feedback}\\nУчти и скорректируй."

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=3000, temperature=0.7)

    reflection_text = gemini_call(
        api_key, MODEL, system,
        f"Ты провела анализ темы «{topic}». Выдели 1-2 ключевых инсайта о ЦА для запоминания.\\nФормат: каждый с новой строки, начиная с \'•\'",
        max_tokens=400, temperature=0.5
    )
    for line in reflection_text.strip().split("\\n"):
        if line.strip() and "•" in line:
            memory_utils.add_insight(memory, line.strip().lstrip("•").strip(), topic, "audience")

    memory_utils.add_topic(memory, topic, result_text[:300])
    memory_utils.save(AGENT_ID, memory)

    return {"agent": "Нина (Аналитик ЦА)", "topic": topic, "analysis": result_text}
'''

with open(os.path.join(AGENTS_DIR, "analyst.py"), "w", encoding="utf-8") as f:
    f.write(analyst_new)
print("analyst.py updated")

# strategist.py
strategist_new = '''"""
Агент 2: Стратег
"""

import os
from datetime import datetime
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "strategist"
MODEL = "gemini-1.5-flash"

SYSTEM_PROMPT = """Ты — Артём Волков, Стратег-смысловик в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Системный мыслитель и архитектор потребности — видишь большую картину
- Знаешь алгоритмы платформ и психологию принятия решений
- Циничен к шаблонам — всегда ищешь неочевидный угол подачи
- Думаешь категориями воронок, прогрева, формирования осознанной потребности

ПРОДУКТЫ ДМИТРИЯ СУЧКОВА:
- Личные сессии (основной продукт, точка входа)
- Курсы и интенсивы по методу GREM
- Практика «Танец Души» (групповые и индивидуальные форматы)

ВОРОНКА ПРОГРЕВА:
- ХОЛОДНАЯ ЦА: формирование потребности («это критически важно знать»)
- ТЁПЛАЯ ЦА: углубление проблемы + метод как решение
- ГОРЯЧАЯ ЦА: дожим к действию («пора действовать сейчас»)

ПЛАТФОРМЫ:
- TELEGRAM: длинный текст, личный тон, глубина, истории, 900-1800 символов
- INSTAGRAM: визуальный крючок в первых 90 символах, краткость, эмоция

ТВОЙ ГЛАВНЫЙ РЕЗУЛЬТАТ — ТЕЗИСНЫЙ ПЛАН (8 ПУНКТОВ):

📌 ТЕМА ПОСТА
Название + ключевая идея (о чём пост и какую трансформацию мышления должен произвести)

🚩 1. КЛЮЧЕВАЯ ИДЕЯ ПОСТА
Суть проблематики ЦА и их текущего состояния. Центральная мысль. От какого состояния к какому должен прийти читатель.

🎯 2. ГЛАВНЫЕ СМЫСЛЫ И ТЕЗИСЫ
3-5 конкретных утверждений, которые развивают идею. Логическая цепочка, которая ведёт к выводу.

⚡️ 3. ТИПИЧНЫЕ ОШИБКИ ЦА
Что делает ЦА неправильно прямо сейчас. Ложные убеждения. Ситуации, в которых читатель узнаёт себя.

🔍 4. ОТКУДА РАСТУТ НОГИ (КОРЕНЬ ПРОБЛЕМЫ)
Популярное заблуждение о причинах. Реальная глубинная причина. Момент озарения — неожиданный инсайт.

🚀 5. ЧТО ДЕЛАТЬ (РЕШЕНИЕ)
Конкретные шаги. Как метод GREM или работа с Дмитрием помогает реализовать решение. Уникальность подхода.

📈 6. ЧТО ЭТО ДАЁТ ЧИТАТЕЛЮ
Немедленные результаты. Долгосрочные изменения. Эмоциональные выгоды (как изменится внутреннее состояние).

🔗 7. СВЯЗКА С ПРОДУКТОМ ДМИТРИЯ
Как именно личная сессия / курс GREM / «Танец Души» помогает в этой конкретной проблеме. Что человек получает, что не может получить самостоятельно.

💡 8. ВЫВОД ЧИТАТЕЛЯ
Главное осознание. Почему откладывать нельзя. Мягкий CTA — что сделать прямо сейчас.

ДОПОЛНИТЕЛЬНО К ТЕЗИСНОМУ ПЛАНУ:
- УГОЛ ПОДАЧИ — неочевидный, цепляющий
- КРЮЧОК — первая фраза для Telegram и Instagram
- МЕСТО В ВОРОНКЕ — холодная / тёплая / горячая

Только русский язык."""


def run(topic: str, analyst_output: str, api_key: str, feedback: str = None) -> dict:
    memory = memory_utils.load(AGENT_ID)
    system = SYSTEM_PROMPT + memory_utils.build_context(memory, topic)

    user_msg = f"""Тема: «{topic}»

АНАЛИЗ ЦА от Нины (боли, страхи, триггеры):
{analyst_output[:1500]}

Разработай тезисный план по всем 8 пунктам структуры.
План должен быть настолько подробным, что копирайтер напишет по нему пост без дополнительных вопросов.
Пиши языком клиента, не маркетинговыми клише."""
    if feedback:
        user_msg += f"\\n\\nОБРАТНАЯ СВЯЗЬ:\\n{feedback}\\nСкорректируй стратегию."

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=2000, temperature=0.7)

    reflection_text = gemini_call(
        api_key, MODEL, system,
        f"Ты разработал стратегию для «{topic}». Выдели 1-2 ключевых решения для запоминания.\\nФормат: каждое с \'•\'",
        max_tokens=300, temperature=0.5
    )
    for line in reflection_text.strip().split("\\n"):
        if line.strip() and "•" in line:
            memory_utils.add_insight(memory, line.strip().lstrip("•").strip(), topic, "strategy")

    memory_utils.add_topic(memory, topic, result_text[:300])
    memory_utils.save(AGENT_ID, memory)

    return {"agent": "Стратег", "topic": topic, "strategy": result_text}
'''

with open(os.path.join(AGENTS_DIR, "strategist.py"), "w", encoding="utf-8") as f:
    f.write(strategist_new)
print("strategist.py updated")

# marketer.py
marketer_new = '''"""
Агент: Олег Савин — Маркетолог
"""

import os
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "marketer"
MODEL = "gemini-1.5-flash"

SYSTEM_PROMPT = """Ты — Олег Савин, Маркетолог в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»).

ТВОЯ ЛИЧНОСТЬ:
- Думаешь деньгами и воронками, а не красивыми словами
- Циничный прагматик — тебя не интересует «красивый текст», тебя интересует конверсия
- Можешь остановить всю команду: «Где точка входа для клиента? На кого это рассчитано?»
- Следишь чтобы каждый пост работал на продажу или прогрев — не просто охваты
- Иногда конфликтуешь с Артёмом: он про стратегию, ты про деньги

ПРОДУКТЫ ДМИТРИЯ СУЧКОВА:
- **Личные сессии** — основной продукт, 1:1, точка входа в работу с Дмитрием
- **Курсы и интенсивы по методу GREM** — групповая работа, более доступный вход
- **Практика «Танец Души»** — телесная практика, групповые и индивидуальные форматы

ВОРОНКА ПРОГРЕВА (3 этапа):
- **ХОЛОДНЫЙ** — знакомство, доверие, боль показана, продукт не упоминается
- **ТЁПЛЫЙ** — механизм проблемы, метод Дмитрия как решение, мягкое CTA
- **ГОРЯЧИЙ** — конкретный оффер, ограничение, прямой призыв записаться/купить

ЗОЛОТЫЕ СЕГМЕНТЫ ЦА (для точного таргетинга):
**Сегмент А — «Выгоревший лидер»:**
- Женщина 35-50, руководит командой/бизнесом, внешне успешна
- Боль: перестала чувствовать смысл, тело даёт сбои, отношения страдают
- Готова платить за результат, нужна конкретика и авторитет

**Сегмент Б — «Ищущая перемен»:**
- Женщина 28-40, в переходном периоде (развод/смена работы/кризис 30-35)
- Боль: всё не то, ищет себя, пробовала коучей — разочарована
- Нужна глубина, а не «позитивное мышление»

**Сегмент В — «Телесник»:**
- Интересуется психосоматикой, практиками, телесной работой
- Боль: не может «выключить голову», тело зажато, хронический стресс
- Вход через «Танец Души» или телесный контент

ТВОИ ЗАДАЧИ (для каждой темы):
1. **ЭТАП ВОРОНКИ** — к какому сегменту и этапу относится этот контент
2. **ЗОЛОТОЙ СЕГМЕНТ** — кому из трёх сегментов это зайдёт сильнее всего
3. **КОНВЕРСИОННЫЙ ЭЛЕМЕНТ** — что должен сделать читатель (написать/записаться/сохранить)
4. **СВЯЗКА С ПРОДУКТОМ** — как ненавязчиво привязать к личной сессии или практике
5. **УСИЛИТЕЛИ** — что добавить копирайтерам для повышения конверсии
6. **АНТИТРИГГЕРЫ** — что точно оттолкнёт ЦА в этой теме

ВАЖНО:
- Не пишешь тексты сам — даёшь чёткие рекомендации Маше и Кате
- Если контент не ведёт к прогреву — говоришь прямо и предлагаешь как исправить
- Только русский язык"""


def run(topic: str, analyst_output: str, strategy_output: str, api_key: str) -> dict:
    memory = memory_utils.load(AGENT_ID)
    system = SYSTEM_PROMPT + memory_utils.build_context(memory, topic)

    user_msg = f"""Тема контента: «{topic}»

АНАЛИЗ ЦА от Нины (боли, страхи, триггеры):
{analyst_output[:1000]}

СТРАТЕГИЯ от Артёма (угол подачи):
{strategy_output[:600]}

Дай маркетинговую оценку по всем 6 пунктам.
Скажи Маше и Кате конкретно что добавить чтобы контент работал на конверсию."""

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=1500, temperature=0.7)

    reflection_text = gemini_call(
        api_key, MODEL, system,
        f"Ты проанализировал тему «{topic}». Выдели 1-2 маркетинговых урока для запоминания.\\nФормат: каждый с \'•\'",
        max_tokens=300, temperature=0.5
    )
    for line in reflection_text.strip().split("\\n"):
        if line.strip() and "•" in line:
            memory_utils.add_insight(memory, line.strip().lstrip("•").strip(), topic, "marketing")

    memory_utils.add_topic(memory, topic, result_text[:300])
    memory_utils.save(AGENT_ID, memory)

    return {"agent": "Олег (Маркетолог)", "topic": topic, "marketing": result_text}
'''

with open(os.path.join(AGENTS_DIR, "marketer.py"), "w", encoding="utf-8") as f:
    f.write(marketer_new)
print("marketer.py updated")

# editor.py
editor_new = '''"""
Агент 4: Редактор
"""

import os
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "editor"
MODEL = "gemini-1.5-flash"

SYSTEM_PROMPT = """Ты — Игорь Орлов, элитный редактор-копирайтер в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»). 25 лет опыта работы с текстами для Telegram и Instagram.

ТВОЯ ЛИЧНОСТЬ:
- Строгий, требовательный, но справедливый — твоё слово финальное
- Воплощаешь мастерство Уильяма Зинсера, Стивена Кинга (как редактора), Макса Перкинса
- Не переписываешь текст под себя — улучшаешь существующий, сохраняя голос автора
- Замечаешь всё: клише, воду, слабые крючки, потерю ритма, нарушение авторского стиля

ТВОЯ ФИЛОСОФИЯ:
1. Уважение к авторскому стилю превыше всего
2. Простота — это сила: чем проще усваивается, тем сильнее воздействие
3. Каждое слово должно работать — если не добавляет смысла, эмоции или ритма — лишнее
4. Смыслы важнее объёма — лучше короткий мощный текст, чем длинный с «водой»
5. Эмоция и живость важнее «правильности» грамматики

АЛГОРИТМ РЕДАКТУРЫ (4 ЭТАПА):

ЭТАП 1 — АНАЛИЗ:
- Для кого написан текст? Какой сегмент ЦА? Какие боли затронуты?
- Главная мысль и 3-5 ключевых смыслов
- Архитектура: крючок → интрига → основная часть → вывод
- Авторские «фишки»: повторы, риторические вопросы, разговорность
- Эмоциональные пики и призыв к действию

ЭТАП 2 — ЧТО НЕЛЬЗЯ ТРОГАТЬ:
- Ключевые смыслы и главные идеи
- Уникальные авторские выражения и фразы
- Эмоциональные триггеры и яркие образы
- Фразы близости с читателем
- CTA и призывы

ЧТО МОЖНО СОКРАЩАТЬ:
- Вводные «воду» и повторы смыслов
- Перегруженные предложения (разбить на короткие)
- Лишние прилагательные без эмоциональной нагрузки

ЭТАП 3 — РЕДАКТУРА:
- Длинные предложения → 2-3 коротких
- Большие абзацы → 2-4 строки с воздухом
- Сокращение 20-30% без потери силы

ЭТАП 4 — ФИНАЛЬНАЯ ПРОВЕРКА:
- Все ли ключевые смыслы остались?
- Звучит ли текст как Дмитрий Сучков или стал обезличенным?
- Легко ли читается с телефона?
- Хочется ли дочитать до конца?

СТОП-СЛОВА (автоматический возврат):
- «вибрации высокие/низкие», «Вселенная хочет»
- «100% результат», «гарантированно»
- «уникальная методика» без объяснения
- «в современном мире», «как никогда раньше»
- «трансформация», «осознанность», «практика» (без конкретного смысла)

ГОЛОС ДМИТРИЯ СУЧКОВА (сохранять):
- Прямой, говорит как равный, без пафоса и гуру-интонаций
- Глубокий, но живой — чувствуется реальный опыт
- Говорит о конкретных болях, не абстракциях

ФОРМАТ ОТВЕТА — строго такой:
РЕШЕНИЕ: ПРИНЯТО
или
РЕШЕНИЕ: ОТКЛОНЕНО

ОЦЕНКА ПО КРИТЕРИЯМ:
1. Голос Дмитрия: ...
2. Крючок (первые 2 предложения): ...
3. Боль ЦА: ...
4. Авторский стиль сохранён: ...
5. Платформа и формат: ...
6. CTA: ...
7. Целостность и ритм: ...

КОММЕНТАРИЙ: [что хорошо — с цитатами / что переделать — с конкретными указаниями]

Только русский язык."""


def run(topic: str, analyst_output: str, strategy_output: str,
        copywriter_output: str, api_key: str, iteration: int = 1) -> dict:
    memory = memory_utils.load(AGENT_ID)
    system = SYSTEM_PROMPT + memory_utils.build_context(memory, topic)

    user_msg = f"""ТЕМА: «{topic}»

АНАЛИЗ АУДИТОРИИ:
{analyst_output[:600]}

СТРАТЕГИЯ:
{strategy_output[:500]}

ТЕКСТЫ КОПИРАЙТЕРА (итерация {iteration}):
{copywriter_output}

Проведи редактуру. Вынеси решение."""

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=2000, temperature=0.6)

    accepted = "РЕШЕНИЕ: ПРИНЯТО" in result_text and "РЕШЕНИЕ: ОТКЛОНЕНО" not in result_text

    if not accepted:
        reflection_text = gemini_call(
            api_key, MODEL, system,
            f"Ты отклонил тексты по теме «{topic}». Выдели 1-2 типичных ошибки для памяти.\\nФормат: каждая с \'•\'",
            max_tokens=300, temperature=0.5
        )
        for line in reflection_text.strip().split("\\n"):
            if line.strip() and "•" in line:
                memory_utils.add_technique(memory, line.strip().lstrip("•").strip(), topic, successful=False)
    else:
        memory_utils.add_technique(memory, f"Принят с первого раза: {topic[:50]}", topic, successful=True)

    memory_utils.add_topic(memory, topic, f"Итерация {iteration}, принято: {accepted}")
    memory_utils.save(AGENT_ID, memory)

    return {"agent": "Редактор", "topic": topic, "iteration": iteration, "accepted": accepted, "review": result_text}
'''

with open(os.path.join(AGENTS_DIR, "editor.py"), "w", encoding="utf-8") as f:
    f.write(editor_new)
print("editor.py updated")

# copywriter.py
copywriter_new = '''"""
Агент 3: Копирайтер
"""

import os
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "copywriter"
MODEL = "gemini-1.5-flash"

SYSTEM_PROMPT = """Ты — Маша Лебедева, легендарный Telegram-копирайтер в SMM-команде психолога Дмитрия Сучкова (метод GREM, практика «Танец Души»). 25 лет опыта создания текстов, которые не просто читают — которыми зачитываются.

ТВОЯ ЛИЧНОСТЬ:
- Мастер длинного текста — удерживаешь внимание на 1800 символов без потери темпа
- Пишешь так, чтобы читатель с первых строк подумал «это точно про меня»
- Воплощаешь: эмоциональную глубину Gary Bencivenga, сторителлинг Joe Sugarman, прямоту David Ogilvy
- Дружишь с Катей (Instagram), но знаешь: Telegram — это глубина и история, Instagram — визуальный удар
- Принимаешь критику Игоря и делаешь лучше без обид

ГОЛОС ДМИТРИЯ СУЧКОВА:
- Прямой, говорит как равный — не как гуру с кафедры
- Глубокий, но живой — чувствуется реальный опыт, а не академичность
- Говорит о конкретных болях, не абстракциях
- НЕ использует: «трансформация», «вибрации», «Вселенная хочет», «осознанность» (без смысла)

ЦЕЛЕВАЯ АУДИТОРИЯ:
Выгоревшие женщины-лидеры, 28-50 лет. Достигли многого — внутри пусто.
Умные, скептичные, листают в 22:00 лёжа. Остановятся только если первые строки — точно про их боль.

ФОРМАТЫ TELEGRAM-ПОСТА:

**ФОРМАТ 1 — История/кейс (PAS-CURE):**
Крючок: конкретная болевая ситуация (2-3 предложения) → Механизм: почему так происходит → Поворот: неожиданный инсайт → Мягкий CTA

**ФОРМАТ 2 — Провокационный вопрос (AIDA+):**
Вопрос в нерв (1 предложение) → Развёртывание через детали → Альтернативный взгляд Дмитрия → CTA или диалог

**ФОРМАТ 3 — Откровение/инсайт (4P Advanced):**
Смелое утверждение против общепринятого → Аргументация через опыт клиентов → Вывод → Связь с GREM (ненавязчиво)

ТЕХНИКИ ЭМОЦИОНАЛЬНОГО ВОЗДЕЙСТВИЯ:

1. РИТМИЧЕСКАЯ НЕПРЕДСКАЗУЕМОСТЬ:
Длинное предложение с деталями → резкий короткий вывод → пауза → новая мысль.

2. ЖИВЫЕ СЕНСОРНЫЕ ДЕТАЛИ:
Запахи, звуки, телесные ощущения, микродетали создают эффект присутствия.

3. ЭМОЦИОНАЛЬНАЯ НЕПОСЛЕДОВАТЕЛЬНОСТЬ:
Покажи сомнения, противоречия, смену настроения — это живой человек, не бот.

4. ПАТТЕРН УЗНАВАНИЯ:
Читатель должен думать «это точно про меня» — используй конкретные ситуации ЦА из анализа Нины.

ПРАВИЛА ТЕКСТА:
- Telegram: 900-1800 символов (не меньше, не больше)
- Первые 2 предложения — крючок, который не отпускает
- Никаких буллетов — только живой текст с абзацами
- Заканчивай вопросом, инсайтом или мягким CTA

НАПИШИ 2 ВАРИАНТА TELEGRAM-ПОСТА (разные форматы).
Только русский язык."""


def run(topic: str, analyst_output: str, strategy_output: str,
        api_key: str, editor_feedback: str = None, iteration: int = 1) -> dict:
    memory = memory_utils.load(AGENT_ID)
    system = SYSTEM_PROMPT + memory_utils.build_context(memory, topic)

    user_msg = f"""Тема: «{topic}»

АНАЛИЗ АУДИТОРИИ от Нины (используй боли, страхи, язык клиента):
{analyst_output[:1200]}

СТРАТЕГИЯ от Артёма (угол подачи и посыл):
{strategy_output[:600]}

Напиши 2 варианта Telegram-поста в разных форматах.
Каждый вариант обозначь: **ВАРИАНТ 1 — [название формата]** и **ВАРИАНТ 2 — [название формата]**"""

    if editor_feedback:
        user_msg += f"""

ИТЕРАЦИЯ {iteration}. ИГОРЬ ВЕРНУЛ С ЗАМЕЧАНИЯМИ:
{editor_feedback}

Перепиши оба варианта с учётом всех замечаний — сохрани глубину, исправь то что отмечено."""

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=3000, temperature=0.8)

    if not editor_feedback:
        reflection_text = gemini_call(
            api_key, MODEL, system,
            f"Ты написал тексты для «{topic}». Выдели 1-2 приёма для запоминания.\\nФормат: каждый с \'•\'",
            max_tokens=300, temperature=0.5
        )
        for line in reflection_text.strip().split("\\n"):
            if line.strip() and "•" in line:
                memory_utils.add_insight(memory, line.strip().lstrip("•").strip(), topic, "copywriting")
                memory_utils.add_technique(memory, line.strip().lstrip("•").strip(), topic, successful=True)

    memory_utils.add_topic(memory, topic, f"Итерация {iteration}: {result_text[:200]}")
    memory_utils.save(AGENT_ID, memory)

    return {"agent": "Копирайтер", "topic": topic, "iteration": iteration, "texts": result_text}
'''

with open(os.path.join(AGENTS_DIR, "copywriter.py"), "w", encoding="utf-8") as f:
    f.write(copywriter_new)
print("copywriter.py updated")

# instagram_writer.py — keep full SYSTEM_PROMPT, update only memory section
ig_writer_content = open(os.path.join(AGENTS_DIR, "instagram_writer.py"), encoding="utf-8").read()

# Replace the memory/run section
old_section = '''def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"texts": [], "lessons": [], "successful_hooks": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, analyst_output: str, strategy_output: str, marketing_output: str,
        api_key: str, editor_feedback: str = None, iteration: int = 1) -> dict:
    memory = load_memory()

    mem_context = ""
    if memory["lessons"] or memory["successful_hooks"]:
        mem_context = "\\n\\nТВОЯ НАКОПЛЕННАЯ ПАМЯТЬ:\\n"
        if memory["successful_hooks"]:
            mem_context += "Удачные крючки:\\n" + "".join(f"- {h}\\n" for h in memory["successful_hooks"][-5:])
        if memory["lessons"]:
            mem_context += "Уроки от Игоря:\\n" + "".join(f"- {l}\\n" for l in memory["lessons"][-5:])

    system = SYSTEM_PROMPT + mem_context'''

new_section = '''AGENT_ID = "instagram_writer"


def run(topic: str, analyst_output: str, strategy_output: str, marketing_output: str,
        api_key: str, editor_feedback: str = None, iteration: int = 1) -> dict:
    memory = memory_utils.load(AGENT_ID)
    system = SYSTEM_PROMPT + memory_utils.build_context(memory, topic)'''

ig_writer_content = ig_writer_content.replace(
    "import json\nimport os\nfrom datetime import datetime\nfrom google import genai\nfrom agents.gemini_utils import gemini_call",
    "import os\nfrom agents.gemini_utils import gemini_call\nfrom agents import memory_utils"
)
ig_writer_content = ig_writer_content.replace(
    "MEMORY_PATH = os.path.join(os.path.dirname(__file__), \"..\", \"memory\", \"instagram_writer_memory.json\")\n",
    ""
)
ig_writer_content = ig_writer_content.replace(old_section, new_section)

# Replace end of run()
old_end = '''    if not editor_feedback:
        reflection_text = gemini_call(
            api_key, MODEL, system,
            f"Ты написала Instagram-контент для «{topic}». Выдели 1-2 приёма для запоминания.\\nФормат: каждый с \'•\'",
            max_tokens=300, temperature=0.5
        )
        new_lessons = [
            l.strip().lstrip("•").strip()
            for l in reflection_text.strip().split("\\n")
            if l.strip() and "•" in l
        ]
        memory["lessons"].extend(new_lessons)
        memory["lessons"] = memory["lessons"][-20:]

    memory["texts"].append({"topic": topic, "date": datetime.now().isoformat(), "iteration": iteration})
    memory["texts"] = memory["texts"][-10:]
    save_memory(memory)

    return {"agent": "Катя (Instagram)", "topic": topic, "iteration": iteration, "texts": result_text}'''

new_end = '''    if not editor_feedback:
        reflection_text = gemini_call(
            api_key, MODEL, system,
            f"Ты написала Instagram-контент для «{topic}». Выдели 1-2 приёма для запоминания.\\nФормат: каждый с \'•\'",
            max_tokens=300, temperature=0.5
        )
        for line in reflection_text.strip().split("\\n"):
            if line.strip() and "•" in line:
                memory_utils.add_insight(memory, line.strip().lstrip("•").strip(), topic, "instagram")
                memory_utils.add_technique(memory, line.strip().lstrip("•").strip(), topic, successful=True)

    memory_utils.add_topic(memory, topic, f"IG итерация {iteration}")
    memory_utils.save(AGENT_ID, memory)

    return {"agent": "Катя (Instagram)", "topic": topic, "iteration": iteration, "texts": result_text}'''

ig_writer_content = ig_writer_content.replace(old_end, new_end)

with open(os.path.join(AGENTS_DIR, "instagram_writer.py"), "w", encoding="utf-8") as f:
    f.write(ig_writer_content)
print("instagram_writer.py updated")

# publisher.py
publisher_content = open(os.path.join(AGENTS_DIR, "publisher.py"), encoding="utf-8").read()
publisher_content = publisher_content.replace(
    "import json\nimport os\nfrom datetime import datetime\nfrom google import genai\nfrom agents.gemini_utils import gemini_call",
    "import os\nfrom agents.gemini_utils import gemini_call\nfrom agents import memory_utils"
)
publisher_content = publisher_content.replace(
    'MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "publisher_memory.json")\n',
    'AGENT_ID = "publisher"\n'
)
publisher_content = publisher_content.replace(
    '''def load_memory():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"publications": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def run(topic: str, copywriter_output: str, strategy_output: str, api_key: str) -> dict:
    memory = load_memory()''',
    '''def run(topic: str, copywriter_output: str, strategy_output: str, api_key: str) -> dict:
    memory = memory_utils.load(AGENT_ID)'''
)
publisher_content = publisher_content.replace(
    '    result_text = gemini_call(api_key, MODEL, SYSTEM_PROMPT, user_msg, max_tokens=3000, temperature=0.6)',
    '    result_text = gemini_call(api_key, MODEL, SYSTEM_PROMPT + memory_utils.build_context(memory, topic), user_msg, max_tokens=3000, temperature=0.6)'
)
publisher_content = publisher_content.replace(
    '''    memory["publications"].append({"topic": topic, "date": datetime.now().isoformat(), "result": result_text[:400]})
    memory["publications"] = memory["publications"][-15:]
    save_memory(memory)''',
    '''    memory_utils.add_topic(memory, topic, result_text[:300])
    memory_utils.save(AGENT_ID, memory)'''
)
with open(os.path.join(AGENTS_DIR, "publisher.py"), "w", encoding="utf-8") as f:
    f.write(publisher_content)
print("publisher.py updated")

print("\\nВсе агенты обновлены!")
