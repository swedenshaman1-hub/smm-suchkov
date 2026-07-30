import unittest

from agents import notebook_live, team_registry


class NotebookLiveRouterTests(unittest.TestCase):
    def test_editorial_selection_is_bounded_and_excludes_sales(self):
        route = team_registry.route_for("Как не торопиться с важным ответом")
        selected = notebook_live._selected_notebooks(route)
        keys = {nb.key for nb in selected}

        self.assertEqual(len(selected), 7)
        self.assertNotIn("hormozi_1", keys)
        self.assertNotIn("smm05a_positioning", keys)
        self.assertEqual(
            keys,
            {
                "smm02a_audience",
                "smm02c_human_text",
                "smm03a_angles",
                "smm03b_dramaturgy",
                "smm06_voice",
                "smm09_hooks",
                "smm12_ethical_boundaries",
            },
        )

    def test_commercial_selection_includes_sales_and_ethics(self):
        route = team_registry.route_for("Оффер на новый курс")
        selected = notebook_live._selected_notebooks(route)
        keys = {nb.key for nb in selected}

        self.assertIn("hormozi_1", keys)
        self.assertIn("hormozi_2", keys)
        self.assertIn("smm04_ethics", keys)
        self.assertIn("smm12_ethical_boundaries", keys)
        self.assertIn("smm06_voice", keys)

    def test_context_is_delivered_only_to_assigned_agents(self):
        contexts = notebook_live.TopicContexts(
            mode=team_registry.COMMERCIAL,
            answers={
                "audience:smm02a_audience": "Язык аудитории",
                "offer:hormozi_1": "Каркас оффера",
                "ethics:smm04_ethics": "Этическая проверка",
                "ethics:smm12_ethical_boundaries": "Проверка этических границ",
                "human_text:smm02c_human_text": "Человеческая редактура",
                "voice:smm06_voice": "Голос Дмитрия",
            },
            selected_notebooks=(
                "smm02a_audience",
                "hormozi_1",
                "smm04_ethics",
                "smm12_ethical_boundaries",
                "smm02c_human_text",
                "smm06_voice",
            ),
        )

        researcher_context = contexts.for_agents("researcher")
        offer_context = contexts.for_agents("offer_architect")
        writer_context = contexts.for_agents("writer")
        voice_context = contexts.for_agents("voice")

        self.assertIn("Язык аудитории", researcher_context)
        self.assertNotIn("Каркас оффера", researcher_context)
        self.assertIn("Каркас оффера", offer_context)
        self.assertIn("Этическая проверка", offer_context)
        self.assertIn("Проверка этических границ", offer_context)
        self.assertNotIn("Голос Дмитрия", offer_context)
        self.assertIn("Человеческая редактура", writer_context)
        self.assertNotIn("Голос Дмитрия", writer_context)
        self.assertIn("Человеческая редактура", voice_context)
        self.assertIn("Голос Дмитрия", voice_context)

    def test_voice_query_is_style_only(self):
        prompt = notebook_live._query_prompt(
            "Почему после решения не пришло облегчение",
            "voice",
        )

        self.assertIn("только по слышимой форме речи", prompt)
        self.assertIn("Не объясняй рабочую тему", prompt)
        self.assertIn("темы головы и", prompt)
        self.assertIn("тела, энергии, терапии", prompt)
        self.assertIn("editorial-blueprint", notebook_live.PROMPT_VERSION)

    def test_blueprint_context_excludes_raw_voice(self):
        contexts = notebook_live.TopicContexts(
            mode=team_registry.EDITORIAL,
            answers={
                "angles:smm03a_angles": "Смысловые углы",
                "ethics:smm12_ethical_boundaries": "Этическое вето",
                "human_text:smm02c_human_text": "Человеческий текст",
                "voice:smm06_voice": "Сырая речь Дмитрия",
            },
            selected_notebooks=(
                "smm03a_angles",
                "smm12_ethical_boundaries",
                "smm02c_human_text",
                "smm06_voice",
            ),
        )

        blueprint_context = contexts.without_roles("voice", "ethics")

        self.assertIn("Смысловые углы", blueprint_context)
        self.assertIn("Человеческий текст", blueprint_context)
        self.assertNotIn("Этическое вето", blueprint_context)
        self.assertNotIn("Сырая речь Дмитрия", blueprint_context)

    def test_only_transient_notebook_errors_are_retried(self):
        self.assertTrue(
            notebook_live._is_retryable_query_error(
                TimeoutError("The handshake operation timed out")
            )
        )
        self.assertTrue(
            notebook_live._is_retryable_query_error(
                RuntimeError("status 503: temporarily unavailable")
            )
        )
        self.assertFalse(
            notebook_live._is_retryable_query_error(
                RuntimeError("authentication cookies expired")
            )
        )


if __name__ == "__main__":
    unittest.main()
