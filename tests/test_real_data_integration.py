"""Integration checks against the checked-in generated_v3 index; no provider key."""

import threading
import unittest

from backend.chat_service import ChatService
from backend.schemas import ChatRequest
from retrieval.search import Retriever


class InvalidTwiceGenerator:
    model = "fake-integration-provider"

    def __init__(self):
        self.calls = 0

    def generate(self, question, evidence, **kwargs):
        self.calls += 1
        return "not valid structured output"


class RealDataGroundingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = Retriever()

    def service(self):
        return ChatService(
            retriever=self.retriever,
            generator=InvalidTwiceGenerator(),
            retrieval_lock=threading.Lock(),
            generation_lock=threading.Lock(),
            model_name="fake-integration-provider",
        )

    def test_battery_evidence_plan_reserves_primary_and_secondary_standards(self):
        service = self.service()
        response = service.chat(ChatRequest(question="Which standard applies to a battery-operated toy?"))
        self.assertEqual(response.generation_mode, "extractive_fallback")
        self.assertTrue(response.grounded)
        self.assertFalse(response.insufficient_evidence)
        self.assertGreaterEqual(len(response.citations), 2)
        self.assertIn("IS 15644", response.answer)
        self.assertIn("primary standard is IS 15644", response.answer)
        self.assertIn("IS 9873", response.answer)
        self.assertIn("secondary standards", response.answer)
        self.assertNotIn("test report", response.answer.lower())
        self.assertNotIn("may also be considered", response.answer.lower())
        self.assertNotIn("non-electrical toys", response.answer.lower())
        self.assertNotIn(
            "29fd821c7bad9f3dcb591a264bda92029d03e2a79aa51d75573c5f4aea2bb49d",
            {citation.chunk_id for citation in response.citations},
        )
        for part in ("Part 2", "Part 3", "Part 4", "Part 9", "Part 10", "Part 11"):
            self.assertIn(part.lower(), response.answer.lower())
        excerpts = [citation.excerpt.lower() for citation in response.citations]
        self.assertTrue(any("is 15644" in excerpt and "electric toys" in excerpt for excerpt in excerpts))
        self.assertTrue(any("is 9873" in excerpt and "secondary" in excerpt for excerpt in excerpts))
        self.assertEqual(len({item.chunk_id for item in response.citations}), len(response.citations))
        for citation in response.citations:
            self.assertGreaterEqual(len(citation.excerpt), 20)

    def test_artisan_evidence_plan_preserves_scope_and_registration(self):
        service = self.service()
        response = service.chat(ChatRequest(question="Are all handmade toys exempt?"))
        self.assertEqual(response.generation_mode, "extractive_fallback")
        self.assertTrue(response.grounded)
        self.assertFalse(response.insufficient_evidence)
        self.assertGreaterEqual(len(response.citations), 2)
        self.assertFalse(response.answer.lower().startswith("yes"))
        self.assertIn("manufactured and sold by artisans", response.answer.lower())
        self.assertIn("registered with office of the development commissioner", response.answer.lower())
        self.assertIn("ministry of textiles", response.answer.lower())
        self.assertIn("government of india", response.answer.lower())
        self.assertNotIn("\n", response.answer)
        self.assertNotIn("passage:", response.answer.lower())
        self.assertNotIn("subject to registered", response.answer.lower())
        self.assertNotIn(":.", response.answer)
        self.assertTrue(response.answer.endswith((".", "!", "?")))
        self.assertEqual(len({item.chunk_id for item in response.citations}), len(response.citations))
        for citation in response.citations:
            self.assertNotIn("\n", citation.excerpt)
            self.assertFalse(citation.excerpt.lower().startswith("passage:"))
            self.assertNotIn(":.", citation.excerpt)

    def test_new_series_documents_use_complete_evidence_and_bypass_provider(self):
        service = self.service()
        response = service.chat(ChatRequest(question="What documents are required for a new toy series?"))
        self.assertTrue(response.grounded)
        self.assertEqual(response.generation_mode, "extractive_fallback")
        self.assertIn("a declaration", response.answer.lower())
        self.assertIn("series/model details", response.answer.lower())
        self.assertIn("fee declaration", response.answer.lower())
        self.assertIn("to be declared separately to BIS", response.answer)
        self.assertNotIn("bedeclared", response.answer.lower())
        self.assertNotIn("  ", response.answer)
        self.assertGreaterEqual(len(response.citations), 3)
        self.assertEqual(service._generator.calls, 0)

    def test_qco_commencement_uses_legal_clause_and_bypasses_provider(self):
        service = self.service()
        response = service.chat(ChatRequest(question="What was the QCO commencement date?"))
        self.assertTrue(response.grounded)
        self.assertEqual(response.generation_mode, "extractive_fallback")
        self.assertIn("comes into force", response.answer.lower())
        self.assertIn("does not establish a calendar date", response.answer.lower())
        self.assertNotIn("product manual", response.answer.lower())
        self.assertEqual(service._generator.calls, 0)

    def test_transition_order_uses_operative_roles_and_bypasses_provider(self):
        service = self.service()
        response = service.chat(ChatRequest(question="What does the 2026 transition order do?"))
        self.assertTrue(response.grounded)
        self.assertEqual(response.generation_mode, "extractive_fallback")
        self.assertIn("permission may be granted", response.answer.lower())
        self.assertIn("risk assessment", response.answer.lower())
        self.assertNotIn("permission maybe granted", response.answer.lower())
        self.assertNotIn("  ", response.answer)
        self.assertGreaterEqual(len(response.citations), 2)
        self.assertEqual(service._generator.calls, 0)

    def test_deterministic_fragment_join_preserves_word_boundaries(self):
        composed = ChatService._compose_fragments("to be", "declared", "separately to BIS")
        self.assertEqual(composed, "to be declared separately to BIS")
        self.assertNotIn("  ", composed)
