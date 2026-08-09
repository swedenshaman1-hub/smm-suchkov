import unittest
from unittest.mock import patch

from agents import editorial_history


class EditorialHistoryTests(unittest.TestCase):
    def test_selector_avoids_last_two_entrances_and_endings(self):
        history = [
            {"actual": {"entrance": "direct_thesis", "ending": "open_question", "metaphor": False}},
            {"actual": {"entrance": "concrete_moment", "ending": "clear_conclusion", "metaphor": True}},
        ]
        profile = editorial_history.select_profile("Тестовая тема", history)
        self.assertNotIn(profile["entrance"], {"direct_thesis", "concrete_moment"})
        self.assertNotIn(profile["ending"], {"open_question", "clear_conclusion"})

    def test_profile_suppresses_metaphor_after_recent_metaphor(self):
        history = [{"actual": {"entrance": "observation", "ending": "quiet_observation", "metaphor": True}}]
        profile = editorial_history.select_profile("Любая тема", history)
        self.assertFalse(profile["metaphor"])
        self.assertIn("без метафор", editorial_history.profile_instruction(profile))

    def test_fingerprint_detects_question_final_and_metaphor(self):
        actual = editorial_history.fingerprint(
            "Телефон лежит на столе. Словно между людьми выросла стена.\n\nЧто здесь изменилось?"
        )
        self.assertEqual(actual["entrance"], "concrete_moment")
        self.assertEqual(actual["ending"], "open_question")
        self.assertTrue(actual["metaphor"])

    def test_diagnostics_warn_about_cliche_and_repeated_shape(self):
        history = [{"actual": {"entrance": "observation", "ending": "open_question", "question_final": True}}] * 6
        text = "Иногда всё выглядит просто. И тогда главный вопрос не в том, кто прав, а в том, что важно?"
        actual = editorial_history.fingerprint(text)
        warnings = editorial_history.diagnose(text, actual, history)
        joined = " ".join(warnings)
        self.assertIn("main_question", joined)
        self.assertIn("Финал-вопрос", joined)

    @patch("agents.editorial_history.memory_utils.save")
    @patch("agents.editorial_history.memory_utils.load")
    def test_draft_lifecycle_only_accepts_after_explicit_status(self, load, save):
        memory = {"profile": {}, "editorial_records": []}
        load.return_value = memory
        draft_id = editorial_history.record_draft(
            1, "Тема", "Текст", {"entrance": "observation", "ending": "clear_conclusion", "metaphor": False},
            {"entrance": "observation", "ending": "clear_conclusion", "metaphor": False}, [],
        )
        self.assertEqual(memory["editorial_records"][0]["status"], "generated")
        editorial_history.set_status(draft_id, "accepted")
        self.assertEqual(memory["editorial_records"][0]["status"], "accepted")
        self.assertGreaterEqual(save.call_count, 2)


if __name__ == "__main__":
    unittest.main()
