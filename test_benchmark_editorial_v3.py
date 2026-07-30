import unittest

from benchmark_editorial_v3 import SCORE_WEIGHTS, _parse_json


class BenchmarkParserTests(unittest.TestCase):
    def test_recovers_complete_scores_when_judge_omits_a_comma(self):
        score_lines = "\n".join(
            f'"{key}": 8.5{"," if index < len(SCORE_WEIGHTS) - 1 else ""}'
            for index, key in enumerate(SCORE_WEIGHTS)
        )
        malformed = f"""{{
  "scores": {{
{score_lines}
  }}
  "blocking": [],
  "strengths": ["ясная логика"],
  "weaknesses": ["слишком общий язык"]
}}"""

        parsed = _parse_json(malformed)

        self.assertEqual(set(SCORE_WEIGHTS), set(parsed["scores"]))
        self.assertEqual([], parsed["blocking"])
        self.assertTrue(parsed["parser_recovered_malformed_json"])


if __name__ == "__main__":
    unittest.main()
