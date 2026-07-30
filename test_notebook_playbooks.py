import unittest
from unittest.mock import patch

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

    def test_human_surface_removes_topic_quotes_dashes_and_hyphens(self):
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
        self.assertNotIn("-", clean)
        self.assertIn("по прежнему", clean)

    def test_human_surface_removes_double_sentence_punctuation(self):
        clean = telegram_team.clean_human_surface(
            "Тема",
            "Что происходит?. Это уже закончилось!.",
        )

        self.assertEqual("Что происходит? Это уже закончилось!", clean)

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

    def test_second_person_limit_is_editorial_not_delivery_blocker(self):
        topic = "Как заметить, что собственный аргумент больше не убеждает"
        text = (
            "Вы продолжаете объяснять свою позицию. Вы повторяете доводы. "
            "Ваш голос звучит уверенно, но вы уже замечаете противоречие. "
            "Вы можете проверить, какой ваш аргумент перестал работать и почему."
        )

        warnings = telegram_team.structural_warnings(topic, text)
        blockers = telegram_team.blocking_structural_warnings(topic, text)

        self.assertTrue(any("обращения" in item for item in warnings))
        self.assertFalse(blockers)

    def test_invented_context_remains_structural_delivery_blocker(self):
        topic = "Как заметить, что собственный аргумент больше не убеждает"
        text = (
            "На совещании коллеги слушают презентацию проекта. "
            "Аргумент перестаёт убеждать раньше, чем заканчивается фраза."
        )

        blockers = telegram_team.blocking_structural_warnings(topic, text)

        self.assertTrue(any("коллег" in item for item in blockers))
        self.assertTrue(any("презентац" in item for item in blockers))
        self.assertTrue(any("проект" in item for item in blockers))

    def test_hidden_reputation_motive_is_rejected_when_topic_does_not_supply_it(self):
        topic = (
            "Момент, когда продолжаешь объяснять своё решение другим "
            "и понимаешь, что сам уже в него не веришь"
        )
        text = (
            "Ответ сейчас скорее защита своего лица, чем поиск истины. "
            "Слова нужны, чтобы удержать правоту, сохранить образ и не выглядеть "
            "непоследовательным перед другими."
        )

        blockers = telegram_team.blocking_structural_warnings(topic, text)

        self.assertTrue(any("мотивом защиты" in item for item in blockers))

    def test_second_rejected_post_exposes_causal_and_invented_scene_defects(self):
        topic = (
            "Почему иногда после правильного решения не приходит облегчение "
            "и означает ли это, что решение было ошибочным"
        )
        text = (
            "Вы удалили сотни старых контактов из телефона. "
            "Мозг и тело адаптируются к привычному порядку и выстраивают вокруг "
            "него защитные механизмы. Поэтому дискомфорт после решения является "
            "инерцией привычки и частью процесса отпускания."
        )

        blockers = telegram_team.blocking_structural_warnings(topic, text)

        self.assertTrue(any("означает ли это" in item for item in blockers))
        self.assertTrue(any("мозга и тела" in item for item in blockers))
        self.assertTrue(any("выдуманное событие" in item for item in blockers))

    def test_ambiguous_question_passes_with_explicit_limit_of_inference(self):
        topic = (
            "Почему иногда после правильного решения не приходит облегчение "
            "и означает ли это, что решение было ошибочным"
        )
        text = (
            "Облегчение после сложного решения приходит не всегда. Само по себе "
            "его отсутствие не доказывает, что выбор был ошибочным. Полезнее "
            "проверить, изменились ли факты, нарушены ли важные критерии и готов "
            "ли человек принять цену выбранного решения."
        )

        self.assertFalse(telegram_team.blocking_structural_warnings(topic, text))

    @patch("agents.telegram_team.gemini_call", return_value="Короткий готовый текст.")
    def test_length_editor_receives_structural_issues(self, gemini_mock):
        result = telegram_team.fit_length(
            "Тема",
            "Длинный исходный текст.",
            "test-key",
            issues=["сократи обращения «вы/ты» до пяти"],
        )

        user_message = gemini_mock.call_args.args[3]
        self.assertIn("сократи обращения", user_message)
        self.assertLessEqual(gemini_mock.call_args.kwargs["max_tokens"], 900)
        self.assertEqual(result, "Короткий готовый текст.")


if __name__ == "__main__":
    unittest.main()
