"""Session-aware personalization and relevance regressions without a provider key."""

import unittest

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.question_understanding import normalize_question, understand_question
from backend.schemas import AssistantContext
from tests.test_chat_api import FakeGenerator, FakeRetriever


class PersonalizedUnderstandingTests(unittest.TestCase):
    def test_under_eight_profile_statement_gets_age_clarification(self):
        result = understand_question("I manufacture non electric toys for under age 8")
        self.assertTrue(result.profile_statement)
        self.assertTrue(result.clarification_required)
        self.assertEqual(result.power, "non_electric")
        self.assertEqual(result.assistant_context.role, "manufacturer")
        self.assertEqual(result.assistant_context.age_group, "not_sure")
        self.assertEqual(result.assistant_context.expected_slots, ["age_group"])
        self.assertEqual(result.suggested_replies, ("Under 3", "3–8", "Both age groups"))

    def test_fully_specified_profile_asks_for_goal(self):
        result = understand_question(
            "I manufacture non-electric kitchen play sets for children aged five"
        )
        self.assertEqual(result.assistant_context.role, "manufacturer")
        self.assertEqual(result.assistant_context.power_type, "non_electric")
        self.assertEqual(result.assistant_context.age_group, "3_to_8")
        self.assertEqual(result.assistant_context.product_description, "kitchen play sets")
        self.assertEqual(result.assistant_context.expected_slots, ["goal"])
        self.assertIn("Show my complete compliance roadmap", result.suggested_replies)

    def test_new_question_clears_context_but_short_slot_answer_retains_it(self):
        context = AssistantContext(
            original_question="How do I certify my toys?",
            expected_slots=["product_description", "power_type"],
            product_description="toys",
            current_goal="new_licence",
        )
        independent = understand_question(
            "How many days will BIS take to approve my licence?",
            assistant_context=context,
        )
        self.assertFalse(independent.context_retained)
        self.assertEqual(independent.intent, "timeline")

        continuation = understand_question("Non-electric toy car", assistant_context=context)
        self.assertTrue(continuation.context_retained)
        self.assertEqual(continuation.power, "non_electric")
        self.assertNotIn("power_type", continuation.missing_required_details)

    def test_known_slots_are_not_requested_again(self):
        context = AssistantContext(
            original_question="How do I certify my toys?",
            expected_slots=["application_stage"], role="manufacturer",
            product_description="toy car", power_type="non_electric",
            age_group="3_to_8", current_goal="new_licence",
        )
        result = understand_question("This is a new licence", assistant_context=context)
        self.assertTrue(result.context_retained)
        self.assertNotIn("power_type", result.missing_required_details)
        self.assertNotIn("role", result.missing_required_details)
        self.assertNotIn("application_stage", result.missing_required_details)

    def test_leading_timeline_typo_is_conservatively_corrected(self):
        normalized, corrections = normalize_question("ow many days will approval take?")
        self.assertTrue(normalized.startswith("how many days"))
        self.assertIn("ow many->how many", corrections)

    def test_profile_onboarding_advances_without_reasking_known_slots(self):
        first = understand_question("I manufacture non electric toys for under age 8")
        second = understand_question("3–8", assistant_context=first.assistant_context)
        self.assertTrue(second.context_retained)
        self.assertEqual(second.assistant_context.age_group, "3_to_8")
        self.assertEqual(second.assistant_context.expected_slots, ["goal"])
        self.assertNotIn("power type", second.clarification_question.lower())

        third = understand_question(
            "Identify applicable standards",
            assistant_context=second.assistant_context,
        )
        self.assertTrue(third.context_retained)
        self.assertEqual(third.intent, "standards")
        self.assertEqual(third.power, "non_electric")
        self.assertFalse(third.clarification_required)


class PersonalizedApiTests(unittest.TestCase):
    def setUp(self):
        self.retriever = FakeRetriever()
        self.generator = FakeGenerator([])
        self.context = TestClient(create_app(
            retriever_factory=lambda: self.retriever,
            generator_factory=lambda: self.generator,
        ))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def ask(self, question, assistant_context=None):
        payload = {"question": question, "top_k": 8, "include_guidance": False}
        if assistant_context:
            payload["assistant_context"] = assistant_context
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_profile_statement_is_not_evidence_insufficient(self):
        body = self.ask("I manufacture non electric toys for under age 8")
        self.assertFalse(body["grounded"])
        self.assertFalse(body["insufficient_evidence"])
        self.assertTrue(body["needs_clarification"])
        self.assertIn("user-provided profile information", body["answer"])
        self.assertIn("under 3, 3–8, or both", body["answer"])
        self.assertEqual(body["suggested_replies"], ["Under 3", "3–8", "Both age groups"])
        self.assertEqual(self.retriever.calls, [])
        self.assertEqual(self.generator.calls, [])

    def test_independent_timeline_question_is_not_polluted(self):
        body = self.ask(
            "How many days will BIS take to approve my licence?",
            {
                "original_question": "How do I certify my toys?",
                "expected_slots": ["product_description", "power_type"],
                "current_goal": "new_licence",
            },
        )
        self.assertTrue(body["insufficient_evidence"])
        self.assertFalse(body["needs_clarification"])
        self.assertIn("do not state a guaranteed licence-approval timeline", body["answer"])
        self.assertNotIn("battery-operated", body["answer"])
        self.assertEqual(body["citations"], [])

    def test_unsupported_details_receive_specific_distinct_limitations(self):
        cases = {
            "What is the exact fee for a toy licence?": "current exact fee",
            "Which laboratory do you recommend?": "specific laboratory",
            "Which form do I need to submit?": "current form number",
            "ow many days will approval take?": "guaranteed licence-approval timeline",
        }
        answers = []
        for question, expected in cases.items():
            with self.subTest(question=question):
                body = self.ask(question)
                self.assertTrue(body["insufficient_evidence"])
                self.assertFalse(body["needs_clarification"])
                self.assertIn(expected, body["answer"])
                answers.append(body["answer"])
        self.assertEqual(len(set(answers)), len(cases))

    def test_context_is_strict_and_bounded(self):
        base = {"original_question": "What standards apply?", "expected_slots": ["power_type"]}
        self.assertEqual(self.client.post("/api/chat", json={"question": "Non-electric", "assistant_context": {**base, "debug": True}}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"question": "Non-electric", "assistant_context": {**base, "product_description": "x" * 301}}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
