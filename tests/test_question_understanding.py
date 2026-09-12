"""Focused deterministic question-understanding regressions."""

import unittest

from backend.question_understanding import normalize_question, understand_question


class QuestionUnderstandingTests(unittest.TestCase):
    def test_conservative_typo_corrections(self):
        understood = understand_question("how to certify mt toys")
        self.assertEqual(understood.intent, "certification")
        self.assertIn("my toys", understood.normalized_query)
        self.assertTrue(understood.clarification_required)
        self.assertIn("product_description", understood.missing_required_details)
        self.assertIn("power_type", understood.missing_required_details)

        standards = understand_question("what standrads apply to non eletric toys")
        self.assertEqual(standards.intent, "standards")
        self.assertEqual(standards.power, "non_electric")
        self.assertFalse(standards.clarification_required)

    def test_corrections_do_not_change_standard_numbers_or_product_names(self):
        normalized, _ = normalize_question("Acme Z9 standrad IS 15644 on 1 January 2026")
        self.assertIn("acme z9", normalized)
        self.assertIn("is 15644", normalized)
        self.assertIn("1 january 2026", normalized)

    def test_power_classification_is_negation_aware_and_exact(self):
        cases = {
            "non electrical toy": "non_electric",
            "toy without electrical power": "non_electric",
            "toy without electric power": "non_electric",
            "manual toy": "non_electric",
            "battery-powered toy": "battery_operated",
            "plug-in toy": "mains_electric",
            "electrical toy": "electric_unspecified",
            "ordinary toy": "unknown",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(understand_question(f"what standards apply to {query}").power, expected)

    def test_intent_precedence_beats_power_words(self):
        cases = {
            "how do I certify a battery toy": "certification",
            "are battery toys exempt for artisans": "exemption",
            "documents to add a battery toy series": "documents",
            "what does the battery transition order do": "transition",
            "what is the commencement date for the electric toy order": "commencement",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(understand_question(query).intent, expected)

    def test_standards_without_power_requests_concrete_clarification(self):
        for query in ("what are standards for toys", "bis standards for toys"):
            with self.subTest(query=query):
                understood = understand_question(query)
                self.assertTrue(understood.clarification_required)
                self.assertEqual(understood.power, "unknown")
                self.assertIn("battery-operated, mains-powered, or non-electric", understood.clarification_question)

    def test_generic_electrical_certification_does_not_become_battery(self):
        understood = understand_question("how to get certified my electrical toy car")
        self.assertEqual(understood.intent, "certification")
        self.assertEqual(understood.power, "electric_unspecified")
        self.assertTrue(understood.clarification_required)
        self.assertIn("battery-operated", understood.clarification_question)

    def test_ambiguous_kitchen_set_asks_product_scope(self):
        understood = understand_question("how to get certified for my non electrical kitchen set")
        self.assertEqual(understood.power, "non_electric")
        self.assertTrue(understood.clarification_required)
        self.assertIn("children's toy intended for play", understood.clarification_question)

    def test_follow_up_resolves_original_standards_question(self):
        understood = understand_question(
            "Non-electric kitchen play set for children aged five.",
            "What standards apply to toys?",
        )
        self.assertEqual(understood.intent, "standards")
        self.assertEqual(understood.power, "non_electric")
        self.assertFalse(understood.clarification_required)


if __name__ == "__main__":
    unittest.main()
