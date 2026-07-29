import unittest

from agents import notebook_playbooks
from agents import telegram_team


class NotebookPlaybooksTest(unittest.TestCase):
    def test_all_editorial_roles_have_notebook_context(self):
        for role in ("researcher", "strategist", "writer", "editor", "voice"):
            context = notebook_playbooks.context_for(role)
            self.assertIn("GEMINI NOTEBOOK", context)
            self.assertGreater(len(context), 900)

    def test_snapshot_has_expected_sources(self):
        self.assertEqual(len(notebook_playbooks.NOTEBOOK_SOURCES), 7)
        self.assertIn("SMM-06", notebook_playbooks.NOTEBOOK_SOURCES["voice"][0])
        self.assertIn(
            "SMM-12",
            notebook_playbooks.NOTEBOOK_SOURCES["ethical_boundaries"][0],
        )

    def test_repetitive_metaphors_are_flagged(self):
        warnings = telegram_team.quality_warnings(
            "Ваш внутренний защитник устал. Внутренний компас молчит."
        )
        self.assertTrue(any("защитника" in item for item in warnings))

    def test_brand_boundary_remains_hard_error(self):
        errors = telegram_team.validate_post(
            "Дмитрий работает как соматический терапевт. " + "Текст. " * 80
        )
        self.assertTrue(any("брендовая граница" in item for item in errors))

    def test_unsupported_brain_processing_is_flagged(self):
        warnings = telegram_team.quality_warnings(
            "Мозг сортирует впечатления, встраивает их в память и создаёт новые связи."
        )
        self.assertTrue(any("мозгу" in item for item in warnings))

    def test_unsafe_strategy_is_stopped_before_writing(self):
        warnings = telegram_team.strategy_warnings(
            "Это эволюционный механизм: мозг интегрирует опыт и сохраняет файл."
        )
        self.assertGreaterEqual(len(warnings), 2)

    def test_long_post_is_delivery_error(self):
        errors = telegram_team.validate_post("Фраза. " * 320)
        self.assertTrue(any("1900" in item for item in errors))

    def test_length_fallback_keeps_post_deliverable(self):
        long_text = (
            "Первая мысль задаёт направление. "
            + "Каждый следующий абзац развивает её без новой причины. " * 45
            + "Финал возвращает читателя к исходному выбору."
        )

        fitted = telegram_team.enforce_length(long_text)

        self.assertLessEqual(len(fitted), 1850)
        self.assertGreaterEqual(len(fitted), 350)
        self.assertTrue(fitted.endswith((".", "!", "?", "…")))

    def test_style_warning_does_not_become_endless_blocker(self):
        text = (
            "Давайте честно: важный разговор иногда хочется отложить. "
            + "Но сам факт паузы ещё не объясняет её причину. " * 12
        )

        self.assertTrue(telegram_team.quality_warnings(text))
        self.assertFalse(telegram_team.blocking_quality_warnings(text))

    def test_hidden_motive_remains_delivery_blocker(self):
        text = (
            "Вы на самом деле просто маскируете страх. "
            + "Остальной текст развивает эту мысль. " * 14
        )

        blockers = telegram_team.blocking_quality_warnings(text)

        self.assertTrue(any("скрытый мотив" in item for item in blockers))

    def test_human_surface_removes_topic_quotes_and_typographic_dashes(self):
        topic = "Когда решение перестаёт быть твоим"
        raw = (
            "Когда решение перестаёт быть твоим\n"
            "Ты говоришь: «Я по-прежнему уверен» — и слышишь фальшь."
        )

        clean = telegram_team.clean_human_surface(topic, raw)

        self.assertFalse(clean.startswith(topic))
        self.assertNotIn("«", clean)
        self.assertNotIn("»", clean)
        self.assertNotIn("—", clean)
        self.assertIn("по-прежнему", clean)

    def test_rejected_control_post_exposes_structural_defects(self):
        topic = (
            "Момент, когда ты продолжаешь объяснять своё решение другим "
            "и вдруг понимаешь, что сам уже в него не веришь"
        )
        text = (
            "Вы стоите перед группой и объясняете стратегию. "
            "Коллеги кивают во время презентации. Вы слышите свой голос. "
            "Вы замечаете напряжение в груди и поверхностное дыхание. "
            "Слова лишены вашей внутренней энергии. Это смена оптики. "
            "Внутри работает другой механизм. Не игнорируйте это ощущение. "
            "Оно может стать ключом к новому пониманию."
        )

        warnings = telegram_team.structural_warnings(topic, text)

        self.assertGreaterEqual(len(warnings), 6)
        self.assertTrue(any("группу" in item for item in warnings))
        self.assertTrue(any("телесные реакции" in item for item in warnings))
        self.assertTrue(any("AI-формулы" in item for item in warnings))
        self.assertTrue(any("второго лица" in item for item in warnings))

    def test_context_neutral_post_has_no_structural_warning(self):
        topic = "Как заметить, что собственный аргумент больше не убеждает"
        text = (
            "Иногда аргумент перестаёт убеждать раньше, чем заканчивается фраза. "
            "Это ещё не доказывает, что решение ошибочно. Полезно отделить два "
            "вопроса. Какой именно довод перестал работать? Появился новый факт "
            "или прежнее объяснение просто больше не выдерживает проверки? "
            "Такая пауза не даёт готового ответа. Она показывает место, которое "
            "перед следующим разговором стоит проверить заново."
        )

        self.assertFalse(telegram_team.structural_warnings(topic, text))


if __name__ == "__main__":
    unittest.main()
