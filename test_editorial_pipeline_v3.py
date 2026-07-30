import unittest

from agents import telegram_team


TOPIC = (
    "Самое болезненное в отношениях начинается не с расставания. "
    "А с момента, когда ты уже чувствуешь, что тебя не выбирают, "
    "но всё ещё пытаешься стать удобнее, чтобы это изменить"
)


def valid_blueprint(hook: str, thesis: str) -> str:
    return f"""КАРКАС: ГОТОВ
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
Диагноз, товарная логика, искусственный дефицит, выдуманная сцена."""


class EditorialPipelineV3Tests(unittest.TestCase):
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

    def test_program_replaces_model_written_blueprint_guardrails(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянное согласие не позволяет увидеть позицию человека.",
        ).replace(
            "- этическая граница: не читать намерения другого человека",
            "- этическая граница: товар, дефицит, цена и инвестиции",
        )

        finalized = telegram_team._finalize_blueprint(blueprint)
        semantic = finalized.split("ЗАПРЕЩЕНО В ТЕКСТЕ:", 1)[0]

        self.assertNotIn("товар, дефицит", semantic)
        self.assertIn(
            "не приписывать партнёру мотивы и отделять наблюдаемое от вывода",
            semantic,
        )
        self.assertEqual(1, finalized.count("ЗАПРЕЩЕНО В ТЕКСТЕ:"))

    def test_contract_catches_real_rejected_generation(self):
        rejected = f"""{TOPIC}.

Ты перечитывал своё сообщение и отправил его снова. Вы всегда доступны.
Представьте редкую книгу или украшение. Когда товар лежит без дефицита,
в него нет необходимости вкладываться.

Чтобы снова стать тем, кого выбирают."""

        issues = telegram_team.editorial_contract_issues(TOPIC, rejected)

        self.assertTrue(any("исходную тему" in issue for issue in issues), issues)
        self.assertTrue(any("не смешивай" in issue for issue in issues), issues)
        self.assertTrue(any("выдуманное событие" in issue for issue in issues), issues)
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
        self.assertIn("не более пяти обращений", brief)
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

    def test_v3_prompts_bound_number_of_drafts(self):
        self.assertIn("Напиши один текст", telegram_team.SINGLE_WRITER_PROMPT)
        self.assertIn(
            "один раз",
            telegram_team.SINGLE_REPAIR_PROMPT,
        )
        self.assertIn(
            "Не переписывай пост",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "Не возвращайся к сырым ответам NotebookLM",
            telegram_team.BLUEPRINT_REPAIR_PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
