import unittest

from agents import notebook_live, team_registry


class NotebookLiveRouterTests(unittest.TestCase):
    def test_editorial_selection_is_bounded_and_excludes_sales(self):
        route = team_registry.route_for("Как не торопиться с важным ответом")
        selected = notebook_live._selected_notebooks(route)
        keys = {nb.key for nb in selected}

        self.assertEqual(len(selected), 5)
        self.assertNotIn("hormozi_1", keys)
        self.assertNotIn("smm05a_positioning", keys)
        self.assertEqual(
            keys,
            {
                "smm02a_audience",
                "smm03a_angles",
                "smm03b_dramaturgy",
                "smm06_voice",
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
                "voice:smm06_voice": "Голос Дмитрия",
            },
            selected_notebooks=(
                "smm02a_audience",
                "hormozi_1",
                "smm04_ethics",
                "smm12_ethical_boundaries",
                "smm06_voice",
            ),
        )

        researcher_context = contexts.for_agents("researcher")
        offer_context = contexts.for_agents("offer_architect")

        self.assertIn("Язык аудитории", researcher_context)
        self.assertNotIn("Каркас оффера", researcher_context)
        self.assertIn("Каркас оффера", offer_context)
        self.assertIn("Этическая проверка", offer_context)
        self.assertIn("Проверка этических границ", offer_context)
        self.assertNotIn("Голос Дмитрия", offer_context)


if __name__ == "__main__":
    unittest.main()
