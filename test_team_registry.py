import os
import unittest
from unittest.mock import patch

from agents import team_registry


class TeamRegistryTests(unittest.TestCase):
    def test_editorial_is_the_safe_default(self):
        route = team_registry.route_for(
            "Почему иногда трудно выдержать паузу перед важным ответом"
        )

        self.assertEqual(route.mode, team_registry.EDITORIAL)
        self.assertNotIn("hormozi_1", {nb.key for nb in route.notebooks})
        self.assertFalse(route.missing_required)

    def test_neutral_word_mesto_does_not_trigger_sales(self):
        self.assertEqual(
            team_registry.classify_task("Как найти своё место в новой команде"),
            team_registry.EDITORIAL,
        )

    def test_brand_route_adds_positioning_without_hormozi(self):
        route = team_registry.route_for(
            "Как выстроить личный бренд Дмитрия и показать экспертность"
        )
        notebook_keys = {nb.key for nb in route.notebooks}

        self.assertEqual(route.mode, team_registry.BRAND)
        self.assertIn("smm05a_positioning", notebook_keys)
        self.assertIn("smm07_brand_architecture", notebook_keys)
        self.assertNotIn("hormozi_1", notebook_keys)

    def test_commercial_route_requires_both_hormozi_notebooks(self):
        route = team_registry.route_for(
            "Создай продающий оффер и пригласи на групповую программу"
        )
        required_keys = {nb.key for nb in route.required_notebooks}
        agent_keys = {agent.key for agent in route.agents}

        self.assertEqual(route.mode, team_registry.COMMERCIAL)
        self.assertTrue({"hormozi_1", "hormozi_2"} <= required_keys)
        self.assertIn("smm12_ethical_boundaries", required_keys)
        self.assertIn("offer_architect", agent_keys)

    def test_sandel_ethics_is_required_and_routed_to_reviewers(self):
        route = team_registry.route_for("Напиши пост о выборе и ответственности")
        notebook = next(
            nb
            for nb in route.notebooks
            if nb.key == "smm12_ethical_boundaries"
        )

        self.assertTrue(notebook.is_required(team_registry.EDITORIAL))
        self.assertEqual(notebook.adviser_role, "ethics")
        self.assertTrue(
            {"editor", "instagram_editor", "comment_analyst"}
            <= set(notebook.agents)
        )

    def test_optional_notebooks_do_not_block(self):
        clean_env = dict(os.environ)
        clean_env.pop("NOTEBOOKLM_SMM09_ID", None)
        with patch.dict(os.environ, clean_env, clear=True):
            route = team_registry.route_for("Напиши спокойный экспертный пост")

            self.assertIn(
                "smm02c_human_text",
                {nb.key for nb in route.optional_notebooks},
            )
            self.assertFalse(route.missing_required)

    def test_hook_notebook_and_editor_are_required_in_every_text_mode(self):
        for mode in team_registry.TASK_MODES:
            route = team_registry.route_for("", explicit_mode=mode)
            required_keys = {nb.key for nb in route.required_notebooks}
            agent_keys = {agent.key for agent in route.agents}

            self.assertIn("smm09_hooks", required_keys)
            self.assertIn("hook_editor", agent_keys)

    def test_registry_manifest_is_shared_and_explicit(self):
        manifest = team_registry.team_manifest()

        self.assertIn(
            "editorial=экспертный/рефлексивный пост без продажи",
            manifest,
        )
        self.assertIn("commercial=оффер/продажа", manifest)
        self.assertIn("Алекс Громов", manifest)
        self.assertIn("Alex Hormozi 1", manifest)

    def test_v3_responsibilities_match_the_actual_pipeline(self):
        responsibilities = {
            agent.key: agent.responsibility
            for agent in team_registry.AGENTS
        }

        self.assertIn("отдельный текст в /post не пишет", responsibilities["researcher"])
        self.assertIn("хук выбирает главред", responsibilities["hook_editor"])
        self.assertIn("Сохраняет пять правил формы SMM-06", responsibilities["voice"])
        hooks_notebook = next(
            notebook
            for notebook in team_registry.NOTEBOOKS
            if notebook.key == "smm09_hooks"
        )
        self.assertIn("Paddy Galloway", hooks_notebook.title)


if __name__ == "__main__":
    unittest.main()
