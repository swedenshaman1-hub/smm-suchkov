import unittest
from unittest.mock import patch

from agents import notebook_live, team_registry


class NotebookLiveRouterTests(unittest.TestCase):
    def test_editorial_selection_is_bounded_and_excludes_sales(self):
        route = team_registry.route_for("Как не торопиться с важным ответом")
        selected = notebook_live._selected_notebooks(route)
        keys = {nb.key for nb in selected}

        self.assertEqual(len(selected), 6)
        self.assertNotIn("hormozi_1", keys)
        self.assertNotIn("smm05a_positioning", keys)
        self.assertNotIn("smm02c_human_text", keys)
        self.assertEqual(
            keys,
            {
                "smm02a_audience",
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
        self.assertIn("«башка», «блин», «головастики»", prompt)
        self.assertIn("message-map-human-edit", notebook_live.PROMPT_VERSION)

    def test_copywriting_contexts_are_separated_by_stage(self):
        contexts = notebook_live.TopicContexts(
            mode=team_registry.EDITORIAL,
            answers={
                "audience:smm02a_audience": "Метод Joanna",
                "human_text:smm02c_human_text": "Метод Ann",
                "voice:smm06_voice": "Голос Дмитрия",
            },
            selected_notebooks=(
                "smm02a_audience",
                "smm02c_human_text",
                "smm06_voice",
            ),
        )

        self.assertEqual("Метод Joanna", contexts.message_strategy)
        self.assertEqual("Метод Ann", contexts.human_text)
        self.assertEqual("Голос Дмитрия", contexts.author_voice)
        self.assertNotIn("Метод Ann", contexts.author_voice)
        self.assertNotIn("Голос Дмитрия", contexts.human_text)

    def test_joanna_and_ann_queries_have_bounded_authority(self):
        joanna = notebook_live._query_prompt("Тестовая тема", "audience")
        ann = notebook_live._query_prompt("Тестовая тема", "human_text")

        self.assertIn("архитектуру сообщения до написания текста", joanna)
        self.assertIn("не являются самими данными Voice of Customer", joanna)
        self.assertIn("не пиши готовый пост", joanna)
        self.assertIn("только как редактуру уже написанного черновика", ann)
        self.assertIn("не меняй факты", ann)
        self.assertIn("не\nподменяй голос Дмитрия", ann)

    @patch("agents.notebook_live._query_one")
    @patch("agents.notebook_live._load_auth")
    def test_ann_notebook_is_queried_with_the_concrete_draft(
        self,
        load_auth,
        query_one,
    ):
        load_auth.return_value = notebook_live.NotebookAuth(
            cookies={"SID": "test"},
        )
        query_one.return_value = (
            "smm02c_human_text",
            "ГДЕ ЗВУЧИТ КАК ЛЕКЦИЯ: второй абзац",
        )

        result = notebook_live.build_human_text_context(
            "Тестовая тема",
            "Уникальный черновик для Ann.",
            team_registry.EDITORIAL,
        )

        self.assertIn("ГДЕ ЗВУЧИТ КАК ЛЕКЦИЯ", result)
        prompt = query_one.call_args.args[1]
        self.assertIn("Уникальный черновик для Ann", prompt)
        self.assertIn("Не пиши новый пост", prompt)

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

        blueprint_context = contexts.without_roles(
            "voice",
            "ethics",
            "audience",
            "human_text",
        )

        self.assertIn("Смысловые углы", blueprint_context)
        self.assertNotIn("Человеческий текст", blueprint_context)
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
