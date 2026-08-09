import unittest
from unittest.mock import MagicMock, patch

from agents import editorial_history


class EditorialHistoryTests(unittest.TestCase):
    def test_selector_avoids_last_two_entrances_and_endings(self):
        history = [
            {"actual": {"entrance": "direct_thesis", "ending": "open_question", "viewpoint": "neutral", "metaphor": False}},
            {"actual": {"entrance": "concrete_moment", "ending": "clear_conclusion", "viewpoint": "shared_we", "metaphor": True}},
        ]
        profile = editorial_history.select_profile("Тестовая тема", history)
        self.assertNotIn(profile["entrance"], {"direct_thesis", "concrete_moment"})
        self.assertNotIn(profile["ending"], {"open_question", "clear_conclusion"})
        self.assertNotIn(profile["viewpoint"], {"neutral", "shared_we"})

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
        joined = " ".join(editorial_history.warning_text(item) for item in warnings)
        self.assertIn("main_question", joined)
        self.assertIn("Финал-вопрос", joined)

    def test_contrast_question_is_stored_as_specific_ending(self):
        text = "Разговор закончился.\n\nЧто если эта тишина не оценка встречи, а чувство момента, когда снова остался один?"
        actual = editorial_history.fingerprint(text)
        self.assertEqual(actual["ending"], "contrast_question")
        self.assertTrue(actual["question_final"])

    def test_first_person_axis_mismatch_creates_warning(self):
        planned = {
            "entrance": "observation", "ending": "clear_conclusion",
            "viewpoint": "author_first_person", "metaphor": False,
        }
        text = "Иногда решение приходит не сразу. Со временем различие становится заметнее."
        actual = editorial_history.fingerprint(text, planned)
        warnings = editorial_history.diagnose(text, actual, history=[], planned=planned)
        self.assertTrue(any(item.get("code") == "mismatch_viewpoint" for item in warnings))

    def test_author_first_person_marker_is_detected_outside_quotes(self):
        actual = editorial_history.fingerprint(
            "Я бы здесь различал усталость и нежелание продолжать разговор."
        )
        self.assertEqual(actual["viewpoint"], "author_first_person")

    @patch("agents.editorial_history.memory_utils._get_client")
    def test_draft_lifecycle_only_accepts_after_explicit_status(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        client.table.return_value.insert.return_value.execute.return_value.data = [{}]
        client.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"status": "accepted"}]
        draft_id = editorial_history.record_draft(
            1, "Тема", "Текст", {"entrance": "observation", "ending": "clear_conclusion", "metaphor": False},
            {"entrance": "observation", "ending": "clear_conclusion", "metaphor": False}, [],
        )
        result, row = editorial_history.decide(draft_id, 1, "accepted")
        self.assertEqual(result, "updated")
        self.assertEqual(row["status"], "accepted")

    def test_contrast_question_across_paragraph_boundary(self):
        text = (
            "И тогда главный вопрос не в том, хотите ли вы видеть друга сегодня.\n\n"
            "А в том, что вы чувствуете к нему, когда встреча отменяется?"
        )
        actual = editorial_history.fingerprint(text)
        self.assertEqual(actual["ending"], "contrast_question")

    def test_all_planned_axes_produce_structured_mismatches(self):
        planned = {"entrance": "direct_thesis", "ending": "clear_conclusion",
                   "viewpoint": "author_first_person", "metaphor": True}
        text = "Иногда решение становится понятнее со временем. Что теперь изменилось?"
        actual = editorial_history.fingerprint(text, planned)
        codes = {item["code"] for item in editorial_history.diagnose(text, actual, [], planned)}
        self.assertTrue({"mismatch_entrance", "mismatch_ending", "mismatch_viewpoint", "mismatch_metaphor"}.issubset(codes))


if __name__ == "__main__":
    unittest.main()
