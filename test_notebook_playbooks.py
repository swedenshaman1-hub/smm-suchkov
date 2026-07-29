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
        self.assertEqual(len(notebook_playbooks.NOTEBOOK_SOURCES), 6)
        self.assertIn("SMM-06", notebook_playbooks.NOTEBOOK_SOURCES["voice"][0])

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


if __name__ == "__main__":
    unittest.main()
