"""Read-only real-index acceptance matrix for free-form question understanding."""

import unittest

from fastapi.testclient import TestClient

from backend.main import create_app
from retrieval.search import Retriever


class InvalidGenerator:
    model = "fake-no-key"

    def generate(self, *_args, **_kwargs):
        return "invalid"


class QuestionUnderstandingRealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(create_app(
            retriever_factory=Retriever,
            generator_factory=InvalidGenerator,
        ))
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def ask(self, question: str, clarification_context=None):
        payload = {"question": question, "top_k": 8, "include_guidance": False, "audience": "manufacturer"}
        if clarification_context:
            payload["clarification_context"] = {"original_question": clarification_context}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_power_standard_matrix(self):
        battery = self.ask("what standards apply to a battery-operated toy")
        mains = self.ask("what standards apply to a mains-powered toy")
        non_electric = self.ask("what standards apply to a non-electrical toy")
        unknown = self.ask("what are standards for toys")
        self.assertIn("battery-operated electric toy", battery["answer"].lower())
        self.assertIn("mains-powered electric toy", mains["answer"].lower())
        self.assertNotIn("battery-operated", mains["answer"].lower())
        self.assertIn("non-electric toy", non_electric["answer"].lower())
        self.assertNotIn("is 15644", non_electric["answer"].lower())
        self.assertTrue(unknown["needs_clarification"])
        self.assertFalse(unknown["insufficient_evidence"])

    def test_certification_missing_slots_clarifies_before_retrieval(self):
        result = self.ask("how to certify mt toys")
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["evidence_count"], 0)
        self.assertNotIn("is 15644", result["answer"].lower())

    def test_certification_with_supported_context_returns_partial_procedure(self):
        result = self.ask(
            "I am a manufacturer applying for a new licence for a battery-operated toy car. How do I get certified?"
        )
        self.assertTrue(result["grounded"])
        self.assertFalse(result["needs_clarification"])
        self.assertIn("manakonline", result["answer"].lower())
        self.assertIn("not the complete certification procedure", result["answer"].lower())
        self.assertGreaterEqual(len(result["citations"]), 4)

    def test_follow_up_resolves_original_standards_question(self):
        result = self.ask(
            "Non-electric kitchen play set for children aged five.",
            "What standards apply to toys?",
        )
        self.assertTrue(result["grounded"])
        self.assertFalse(result["needs_clarification"])
        self.assertIn("non-electric toy", result["answer"].lower())
        self.assertNotIn("is 15644", result["answer"].lower())

    def test_intent_precedence_for_existing_grounded_plans(self):
        exemption = self.ask("Are battery toys made by all handmade artisans exempt?")
        documents = self.ask("What documents add a battery toy model to an existing licence scope?")
        transition = self.ask("What does the 2026 battery toy transition order do?")
        commencement = self.ask("What is the commencement date of the electric Toys QCO?")
        self.assertIn("not all handmade toys", exemption["answer"].lower())
        self.assertIn("partial checklist", documents["answer"].lower())
        self.assertIn("transition facilitation order", transition["answer"].lower())
        self.assertIn("which quality control order", commencement["answer"].lower())
        for result in (exemption, documents, transition, commencement):
            self.assertNotIn("battery-operated electric toy, the primary standard", result["answer"].lower())

    def test_out_of_domain_and_ambiguous_product_are_safe(self):
        outside = self.ask("How do I certify an industrial solar inverter?")
        ambiguous = self.ask("how to get certified for my non electrical kitchen set")
        self.assertTrue(outside["insufficient_evidence"])
        self.assertNotIn("is 15644", outside["answer"].lower())
        self.assertTrue(ambiguous["needs_clarification"])
        self.assertIn("actual household kitchen product", ambiguous["answer"].lower())

    def test_typo_query_uses_non_electric_evidence(self):
        result = self.ask("what standrads apply to non eletric toys")
        self.assertTrue(result["grounded"])
        self.assertIn("is 9873 part 1", result["answer"].lower())
        self.assertNotIn("is 15644", result["answer"].lower())


if __name__ == "__main__":
    unittest.main()
