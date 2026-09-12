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

    def test_standard_explanation_and_comparison_intents(self):
        explanation = understand_question("What is IS 15644?")
        self.assertEqual(explanation.intent, "standard_explanation")
        self.assertEqual(explanation.standard_references[0].display, "IS 15644")
        self.assertTrue(explanation.standard_references[0].supported)
        self.assertFalse(explanation.clarification_required)

        comparison = understand_question("What is the difference between IS 15644 and IS 9873 Part 1?")
        self.assertEqual(comparison.intent, "standard_comparison")
        self.assertEqual([item.display for item in comparison.standard_references], ["IS 15644", "IS 9873 Part 1"])

        meaning = understand_question("What does IS mean?")
        self.assertEqual(meaning.intent, "is_general_meaning")

    def test_standard_number_formatting_is_normalized_without_correction(self):
        for query, display in (
            ("Explain IS-15644 in simple words.", "IS 15644"),
            ("Explain IS15644", "IS 15644"),
            ("explain is 15644", "IS 15644"),
            ("What does IS 9873 Part 1 mean?", "IS 9873 Part 1"),
        ):
            with self.subTest(query=query):
                understood = understand_question(query)
                self.assertEqual(understood.standard_references[0].display, display)
                self.assertEqual(understood.standard_references[0].number, display.split()[1])

    def test_ambiguous_or_unknown_numbers_are_preserved(self):
        for query, display in (
            ("Explain IS 1564", "IS 1564"),
            ("Explain IS 987", "IS 987"),
            ("Explain IS 99999", "IS 99999"),
        ):
            with self.subTest(query=query):
                understood = understand_question(query)
                self.assertEqual(understood.standard_references[0].display, display)
                self.assertFalse(understood.standard_references[0].supported)
                self.assertNotEqual(understood.standard_references[0].display, "IS 15644")
                self.assertNotEqual(understood.standard_references[0].display, "IS 9873")

    def test_contextual_standard_resolution_and_ambiguity(self):
        from backend.schemas import AssistantContext
        single = understand_question(
            "Explain that standard.",
            assistant_context=AssistantContext(referenced_standards=["IS 15644"], current_goal="explain_standard"),
        )
        self.assertTrue(single.context_retained)
        self.assertEqual(single.intent, "standard_explanation")
        self.assertEqual(single.standard_references[0].display, "IS 15644")
        self.assertFalse(single.clarification_required)

        multiple = understand_question(
            "Explain that standard.",
            assistant_context=AssistantContext(
                referenced_standards=["IS 15644", "IS 9873 Part 1", "IS 9873 Part 3"],
                current_goal="explain_standard",
            ),
        )
        self.assertTrue(multiple.clarification_required)
        self.assertEqual(multiple.standard_references, ())
        self.assertIn("Which of the previously mentioned", multiple.clarification_question)

    def test_independent_question_clears_stale_standard_context(self):
        from backend.schemas import AssistantContext
        understood = understand_question(
            "How many days will BIS take to approve my licence?",
            assistant_context=AssistantContext(
                referenced_standards=["IS 15644"],
                current_goal="explain_standard",
                expected_slots=["standard_reference"],
            ),
        )
        self.assertFalse(understood.context_retained)
        self.assertEqual(understood.intent, "timeline")
        self.assertEqual(understood.standard_references, ())

    def test_product_description_is_not_treated_as_standard_evidence(self):
        understood = understand_question("I manufacture battery-operated toys")
        self.assertTrue(understood.profile_statement)
        self.assertEqual(understood.standard_references, ())
        self.assertTrue(understood.clarification_required)


if __name__ == "__main__":
    unittest.main()
