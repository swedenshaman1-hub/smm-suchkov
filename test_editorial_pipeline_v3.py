import unittest
from unittest.mock import patch

from agents import telegram_team


TOPIC = (
    "Самое болезненное в отношениях начинается не с расставания. "
    "А с момента, когда ты уже чувствуешь, что тебя не выбирают, "
    "но всё ещё пытаешься стать удобнее, чтобы это изменить"
)


def valid_blueprint(hook: str, thesis: str) -> str:
    return f"""КАРКАС: ГОТОВ
НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}
ФАКТИЧЕСКИЙ КОНТРАКТ: факты исходной темы и один явно художественный пример
ОБЕЩАНИЕ ЧИТАТЕЛЮ:
Показать разницу между заботой об отношениях и отказом от собственного участия.
ТЕЗИС:
{thesis}
ЭКСПЕРТНАЯ ОПОРА:
- язык и ясность: назвать наблюдаемое без диагноза
- смысловой поворот: удобство не равно самоотмене
- драматургия: от привычного объяснения к точному различению
- этическая граница: не читать намерения другого человека
ХУК:
{hook}
ЛОГИКА:
1. Желание сохранить близость само по себе понятно.
2. Постоянное согласие убирает возможность узнать позицию человека.
3. Честное присутствие не гарантирует исход, но возвращает отношениям реальность.
КОНТРПРИМЕР ИЛИ ГРАНИЦА:
Гибкость и забота могут быть зрелым выбором, если собственная позиция не исчезает.
ФИНАЛ:
Вопрос не в количестве уступок, а в том, остаётся ли в них собственный выбор.
ЗАПРЕЩЕНО В ТЕКСТЕ:
Диагноз, товарная логика, искусственный дефицит, ложный реальный кейс."""


class EditorialPipelineV3Tests(unittest.TestCase):
    def test_reasoning_call_falls_back_when_pro_returns_only_thoughts(self):
        with patch(
            "agents.telegram_team.gemini_call",
            side_effect=[
                ValueError("Gemini вернул пустой ответ"),
                "готовый текст",
            ],
        ) as mocked:
            result = telegram_team._reasoning_call(
                "key",
                "gemini-2.5-pro",
                "system",
                "user",
                max_tokens=7200,
                temperature=0.2,
            )

        self.assertEqual("готовый текст", result)
        self.assertEqual("gemini-2.5-pro", mocked.call_args_list[0].args[1])
        self.assertEqual(telegram_team.MODEL, mocked.call_args_list[1].args[1])
        self.assertFalse(mocked.call_args_list[1].kwargs["disable_thinking"])

    def test_blueprint_fidelity_audit_accepts_grounded_carкас(self):
        with patch(
            "agents.telegram_team._reasoning_call",
            return_value="КАРКАС: ПРИНЯТ",
        ):
            issues = telegram_team.audit_blueprint_fidelity(
                TOPIC,
                valid_blueprint("Новый хук.", "Наблюдаемое различие."),
                "key",
            )

        self.assertEqual([], issues)

    def test_blueprint_fidelity_audit_blocks_fiction_presented_as_fact(self):
        with patch(
            "agents.telegram_team._reasoning_call",
            return_value=(
                "КАРКАС: ИСПРАВИТЬ\n"
                "- Художественная сцена выдана за реальный клиентский случай.\n"
                "- Переживание персонажа объявлено универсальным психологическим законом."
            ),
        ):
            issues = telegram_team.audit_blueprint_fidelity(
                TOPIC,
                valid_blueprint("Новый хук.", "Наблюдаемое различие."),
                "key",
            )

        self.assertEqual(2, len(issues))
        self.assertTrue(all("семантический аудит" in issue for issue in issues))
        self.assertEqual(
            issues,
            telegram_team.blueprint_publication_blockers(issues),
        )

    def test_blueprint_fidelity_prompt_allows_one_fictional_micro_scene(self):
        with patch(
            "agents.telegram_team._reasoning_call",
            return_value="КАРКАС: ПРИНЯТ",
        ) as mocked:
            issues = telegram_team.audit_blueprint_fidelity(
                TOPIC,
                valid_blueprint("Новый хук.", "Наблюдаемое различие."),
                "key",
            )

        self.assertEqual([], issues)
        prompt = mocked.call_args.args[2]
        self.assertIn(
            "Свежий смысловой угол и один вымышленный пример разрешены",
            prompt,
        )

    def test_blueprint_rejects_relationship_commodity_logic(self):
        blueprint = valid_blueprint(
            "Чем доступнее человек, тем меньше его выбирают.",
            "Чтобы вернуть ценность, нужно создать дефицит внимания.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(
            any("товарную логику" in issue for issue in issues),
            issues,
        )

    def test_blueprint_allows_price_of_a_choice_as_non_market_metaphor(self):
        blueprint = valid_blueprint(
            "Уступка может сохранить тишину, но не обязательно диалог.",
            "Ценой такого подхода иногда становится отсутствие ясности "
            "о собственной позиции.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertFalse(
            any("товарную логику" in issue for issue in issues),
            issues,
        )

    def test_blueprint_rejects_human_value_tied_to_availability(self):
        blueprint = valid_blueprint(
            "Чем недоступнее человек, тем сильнее его выбирают.",
            "Доступность снижает ценность человека, поэтому нужно отдалиться.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(
            any("товарную логику" in issue for issue in issues),
            issues,
        )

    def test_blueprint_rejects_copied_topic_as_hook(self):
        blueprint = valid_blueprint(
            TOPIC,
            "Постоянная уступчивость может скрыть собственную позицию.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertIn(
            "blueprint копирует исходную тему вместо нового хука",
            issues,
        )

    def test_blueprint_rejects_unsupported_psychological_mechanism(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Мозг запускает защитный механизм и заставляет человека "
            "минимизировать будущую вину.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertIn(
            "blueprint подменяет наблюдение недоказанным психологическим механизмом",
            issues,
        )

    def test_blueprint_allows_rejected_motive_named_only_as_boundary(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянное согласие может скрыть собственную позицию.",
        ).replace(
            "Гибкость и забота могут быть зрелым выбором, если собственная позиция не исчезает.",
            "Нельзя считать, что такая уступчивость обязательно продиктована тревогой.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertFalse(
            any("скрытый мотив" in issue for issue in issues),
            issues,
        )

    def test_blueprint_rejects_hidden_motive_inside_thesis(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянная уступчивость продиктована тревогой потерять отношения.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(
            any("скрытый мотив" in issue for issue in issues),
            issues,
        )

    def test_soft_blueprint_issue_becomes_caution_instead_of_blocker(self):
        issues = [
            "blueprint приписывает человеку скрытый мотив, вину, тревогу или оправдание"
        ]

        self.assertEqual(
            [],
            telegram_team.blueprint_publication_blockers(issues),
        )
        cautioned = telegram_team.add_blueprint_cautions(
            valid_blueprint("Новый хук.", "Наблюдаемое различие."),
            issues,
        )
        self.assertIn("ПРОГРАММНАЯ ОГОВОРКА К КАРКАСУ", cautioned)
        self.assertIn(issues[0], cautioned)

    def test_unsafe_relationship_blueprint_remains_blocking(self):
        issues = [
            "blueprint переносит товарную логику или искусственный дефицит на отношения"
        ]

        self.assertEqual(
            issues,
            telegram_team.blueprint_publication_blockers(issues),
        )

    def test_program_replaces_model_written_blueprint_guardrails(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянное согласие не позволяет увидеть позицию человека.",
        ).replace(
            "- этическая граница: не читать намерения другого человека",
            "- этическая граница: товар, дефицит, цена и инвестиции",
        )

        finalized = telegram_team._finalize_blueprint(blueprint, TOPIC)
        semantic = finalized.split("ЗАПРЕЩЕНО В ТЕКСТЕ:", 1)[0]

        self.assertNotIn("товар, дефицит", semantic)
        self.assertIn(
            "не приписывать партнёру мотивы и отделять наблюдаемое от вывода",
            semantic,
        )
        self.assertEqual(1, finalized.count("ЗАПРЕЩЕНО В ТЕКСТЕ:"))
        self.assertIn(
            f"НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}",
            finalized,
        )

    def test_program_overwrites_model_written_topic_invariant(self):
        blueprint = valid_blueprint(
            "Новый хук.",
            "Наблюдаемое различие.",
        ).replace(
            f"НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}",
            "НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: Соседняя тема о комфортной тишине",
        )

        finalized = telegram_team._finalize_blueprint(blueprint, TOPIC)

        self.assertIn(
            f"НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}",
            finalized,
        )
        self.assertNotIn("Соседняя тема", finalized)

    def test_contract_catches_real_rejected_generation(self):
        rejected = f"""{TOPIC}.

Ты перечитывал своё сообщение и отправил его снова. Вы всегда доступны.
Представьте редкую книгу или украшение. Когда товар лежит без дефицита,
в него нет необходимости вкладываться.

Чтобы снова стать тем, кого выбирают."""

        issues = telegram_team.editorial_contract_issues(TOPIC, rejected)

        self.assertTrue(any("исходную тему" in issue for issue in issues), issues)
        self.assertTrue(any("не смешивай" in issue for issue in issues), issues)
        self.assertFalse(any("выдуманное событие" in issue for issue in issues), issues)
        self.assertTrue(any("товаром" in issue for issue in issues), issues)
        self.assertTrue(any("главным" in issue for issue in issues), issues)

    def test_contract_rejects_gendered_reader_role(self):
        text = (
            "Иногда желание сохранить отношения постепенно убирает из них "
            "собственную позицию. " * 10
            + "Ты раньше отстаивала своё, а теперь всё чаще соглашаешься."
        )

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertIn(
            "убери женскую форму из обращения к смешанной аудитории",
            issues,
        )

    def test_voice_brief_cannot_force_direct_address_or_abrupt_ending(self):
        raw = """1. коротко
2. просто
3. разговорно
4. прямое обращение на ты в каждом абзаце
5. резкий обрыв без вывода"""

        brief = telegram_team._finalize_voice_brief(raw)

        self.assertIn("полные фразы средней длины", brief)
        self.assertIn("без цепочек обрывков", brief)
        self.assertIn("одно обращение на «ты»", brief)
        self.assertIn("без «вы»", brief)
        self.assertIn("завершённая разговорная фраза", brief)
        self.assertNotIn("резкий обрыв", brief)

    def test_contract_accepts_bounded_human_post(self):
        text = """Иногда человек так старается сохранить отношения, что постепенно
убирает из них собственную позицию.

Сначала это почти незаметно. Один раз проще согласиться. В другой раз не хочется
начинать тяжёлый разговор. Затем привычным становится ответ, который не отражает
ни желания, ни несогласия.

Само по себе умение уступать здесь ни при чём. Гибкость может быть зрелым
выбором. Разница появляется в другом: остаётся ли возможность сказать, чего
хочется, и выдержать ответ другого человека.

Удобство не способно заставить кого-либо любить или разлюбить. Оно также не
доказывает, что близость закончилась. Но постоянное отсутствие собственной
позиции лишает отношения важной информации. Другой человек встречается уже не
с живым выбором, а только с согласием.

Вернуть эту информацию можно без игр в холодность. Иногда достаточно заметить,
где согласие было свободным, а где стало единственным разрешённым ответом.

Количество уступок ничего не решает само по себе. Важнее, остаётся ли в каждой
из них человек, который действительно выбирает."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertEqual([], issues)

    def test_publication_gate_does_not_discard_post_for_direct_address_count(self):
        text = """Иногда попытка сохранить отношения превращается в постоянную
подстройку. Ты всё чаще выбираешь удобный ответ. Тебе проще промолчать, твои
желания откладываются, а твоё несогласие кажется лишним. Твой выбор сужается.

Само по себе умение уступать здесь ни при чём. Гибкость может быть зрелым
выбором. Разница появляется там, где у тебя остаётся возможность сказать,
чего хочется, и выдержать ответ другого человека.

Удобство не способно заставить кого-либо любить или разлюбить. Но постоянное
отсутствие собственной позиции лишает отношения важной информации. Другой
человек встречается уже не с живым выбором, а только с согласием.

Количество уступок ничего не решает само по себе. Важнее, остаётся ли в каждой
из них человек, который действительно выбирает."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)
        blockers = telegram_team.editorial_publication_blockers(TOPIC, text)

        self.assertTrue(any("пяти" in issue for issue in issues), issues)
        self.assertFalse(any("пяти" in issue for issue in blockers), blockers)

    def test_publication_gate_keeps_relationship_commodity_logic_blocking(self):
        text = """Иногда попытка сохранить отношения превращается в подстройку.
Собственная позиция постепенно исчезает, а согласие становится единственным
ответом. Это может выглядеть как гибкость, хотя выбора уже почти не остаётся.

Человеческая ценность здесь устроена как цена товара. Нужно создать дефицит,
чтобы партнёр снова начал вкладываться и выбирать. Доступность снижает цену,
поэтому холодность возвращает интерес.

Такой способ предлагает управлять вниманием другого человека, а не говорить о
том, что происходит между людьми. В результате близость подменяется расчётом,
а отношения становятся способом доказать собственную ценность."""

        blockers = telegram_team.editorial_publication_blockers(TOPIC, text)

        self.assertTrue(any("товаром" in issue for issue in blockers), blockers)

    def test_contract_catches_defects_from_latest_real_generation(self):
        text = """В какой момент забота о другом превращается в отказ от себя?
Эта граница часто стирается незаметно, когда в отношениях появляется холод.

Когда возникает ощущение, что тебя больше не выбирают, первая мысль в башке —
нужно срочно что-то исправить. Стать лучше, понятнее, удобнее. Это кажется
логичным способом удержать связь.

Но есть огромная разница между компромиссом ради двоих и односторонними
уступками, в которых один человек постепенно исчезает.

Забота — это усилие для контакта, даже если оно требует временных неудобств.
А попытка стать удобнее — это желание избежать конфликта или молчания ценой
собственных интересов и чувств.

Такая стратегия не возвращает близость. Она создаёт иллюзию контакта, где
партнёр общается уже не с живым человеком, а с удобной ролью.

Конечно, бывают ситуации, когда партнёр проходит через объективно тяжёлый
период вроде болезни или потери работы.

Временно подстроиться под его нужды — это не стирание себя, а поддержка.

Ключевое отличие в том, что это временный процесс, а не новый стандарт.

Поэтому главный вопрос здесь не в том, любит ли он. Этот вопрос ведёт в тупик.

Гораздо честнее спросить: остаётся ли собственная позиция в этих отношениях?
Ответ отделяет заботу от самоотмены."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertTrue(any("шаблонный хук" in issue for issue in issues), issues)
        self.assertTrue(any("скрытый мотив" in issue for issue in issues), issues)
        self.assertTrue(any("не возвращает близость" in issue for issue in issues), issues)
        self.assertTrue(any("мужской пол" in issue for issue in issues), issues)
        self.assertTrue(any("абстрактные ярлыки" in issue for issue in issues), issues)
        self.assertTrue(any("6–9" in issue for issue in issues), issues)
        cleaned = telegram_team.clean_human_surface(TOPIC, text)
        self.assertNotIn("башк", cleaned.lower())
        self.assertNotRegex(cleaned, r"[«»“”„\"'‐‑‒–—−-]")

    def test_surface_replaces_bashka_and_removes_quotes_dashes_and_hyphens(self):
        raw = (
            "Первая мысль в башке — нужно что-то исправить. "
            "Это «по-настоящему» важный вопрос."
        )

        cleaned = telegram_team.clean_human_surface("Другая тема", raw)

        self.assertEqual(
            "Первая мысль в голове нужно что то исправить. "
            "Это по настоящему важный вопрос.",
            cleaned,
        )
        self.assertNotRegex(cleaned, r"[«»“”„\"'‐‑‒–—−-]")

    def test_contract_catches_defects_from_second_real_generation(self):
        text = """Бывает состояние острее, чем сам разрыв. Это момент, когда вы
формально вместе, но ты себя в этих отношениях уже не находишь.

Всё начинается с едва уловимого сдвига. Разговоры становятся короче, общие
планы теряют ясность, а привычного тепла будто стало меньше. Вы ещё не
расстались, но уже появилось ощущение, что тебя больше не выбирают по умолчанию.

В ответ на эту тревожную тишину может появиться желание стать удобнее.
Сглаживать острые углы и пытаться угадать желания партнёра.

Со стороны это может выглядеть как работа над отношениями. Но вопрос как нам
быть вместе превращается в вопрос что сделать, чтобы меня не оставили.

Такая стратегия не имеет ничего общего со здоровым компромиссом, где двое
меняются ради общего будущего. Один человек отказывается от своих потребностей
и границ, чтобы отсрочить финал, который уже предчувствует.

Задай себе вопрос. Я меняюсь ради будущего или удерживаю то, что уходит?
Это отделяет заботу от самоотмены."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)
        blockers = telegram_team.editorial_publication_blockers(TOPIC, text)

        self.assertIn("не смешивай обращения «ты» и «вы»", issues)
        self.assertFalse(
            any("придуманный признак охлаждения" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("скрытый мотив" in issue for issue in issues), issues)
        self.assertTrue(
            any("дежурную психологическую лексику" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("абстрактные ярлыки" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("не смешивай обращения" in issue for issue in blockers),
            blockers,
        )
        self.assertFalse(
            any("придуманный признак охлаждения" in issue for issue in blockers),
            blockers,
        )
        self.assertTrue(any("скрытый мотив" in issue for issue in blockers), blockers)

    def test_v3_prompts_bound_number_of_drafts(self):
        self.assertIn("Напиши один текст", telegram_team.SINGLE_WRITER_PROMPT)
        self.assertIn(
            "НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ",
            telegram_team.SINGLE_WRITER_PROMPT,
        )
        self.assertIn(
            "один раз",
            telegram_team.SINGLE_REPAIR_PROMPT,
        )
        self.assertIn(
            "Не переписывай пост",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "подменяет соседней темой",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "за этим скрывается",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "Не возвращайся к сырым ответам NotebookLM",
            telegram_team.BLUEPRINT_REPAIR_PROMPT,
        )
        self.assertIn(
            "разрешён один короткий художественный пример",
            telegram_team.SINGLE_WRITER_PROMPT,
        )
        self.assertIn(
            "Художественный пример допустим",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "Можно сохранить или улучшить один художественный",
            telegram_team.SINGLE_REPAIR_PROMPT,
        )
        self.assertIn(
            "одно наблюдаемое действие",
            telegram_team.SINGLE_WRITER_PROMPT,
        )
        self.assertIn(
            "Художественный пример сохрани",
            telegram_team.BLUEPRINT_REPAIR_PROMPT,
        )
        self.assertIn(
            "художественная сцена выдана за реального клиента",
            telegram_team.FINAL_REVIEW_PROMPT,
        )
        self.assertNotIn(
            "никаких новых сцен",
            telegram_team.SINGLE_REPAIR_PROMPT.lower(),
        )


if __name__ == "__main__":
    unittest.main()
