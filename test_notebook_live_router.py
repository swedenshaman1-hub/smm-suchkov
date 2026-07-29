import unittest

from agents import notebook_live, team_registry


class NotebookLiveRouterTests(unittest.TestCase):
    def test_editorial_selection_is_bounded_and_excludes_sales(self):
        route = team_registry.route_for("Как не торопиться с важным ответом")
        selected = notebook_live._selected_notebooks(route)
        keys = {nb.key for nb in selected}

        self.assertLessEqual(len(selected), 8)
        self.assertNotIn("hormozi_1", keys)
        self.assertNotIn("smm05a_positioning", keys)
        self.assertTrue(
            {
                "smm02a_audience",
                "smm03a_angles",
                "smm03b_dramaturgy",
                "smm04_ethics",
                "smm06_voice",
            }
            <= keys
        )

    def test_commercial_selection_includes_sales_and_ethics(self):
        route = team_registry.route_for("Оффер на новый курс")
        selected = notebook_live._selected_notebooks(route)
        keys = {nb.key for nb in selected}

        self.assertIn("hormozi_1", keys)
        self.assertIn("hormozi_2", keys)
        self.assertIn("smm04_ethics", keys)
        self.assertIn("smm06_voice", keys)

    def test_context_is_delivered_only_to_assigned_agents(self):
        contexts = notebook_live.TopicContexts(
            mode=team_registry.COMMERCIAL,
            answers={
                "audience:smm02a_audience": "Язык аудитории",
                "offer:hormozi_1": "Каркас оффера",
                "ethics:smm04_ethics": "Этическая проверка",
                "voice:smm06_voice": "Голос Дмитрия",
            },
            selected_notebooks=(
                "smm02a_audience",
                "hormozi_1",
                "smm04_ethics",
                "smm06_voice",
            ),
        )

        researcher_context = contexts.for_agents("researcher")
        offer_context = contexts.for_agents("offer_architect")

        self.assertIn("Язык аудитории", researcher_context)
        self.assertNotIn("Каркас оффера", researcher_context)
        self.assertIn("Каркас оффера", offer_context)
        self.assertIn("Этическая проверка", offer_context)
        self.assertNotIn("Голос Дмитрия", offer_context)


if __name__ == "__main__":
    unittest.main()
