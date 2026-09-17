"""Typed standard-explanation regressions across understanding, API, and the real index."""

import threading
import unittest

from fastapi.testclient import TestClient

from backend.chat_service import ChatService
from backend.main import create_app
from backend.question_understanding import understand_question
from backend.schemas import ChatRequest
from backend.retrieval_provider import LocalChromaRetriever
from tests.test_chat_api import FakeGenerator, FakeRetriever, valid_output


PRIMARY = (
    "For electric toys, the applicable primary standard is IS 15644:2006 electric toys."
)
SECONDARY = (
    "Applicable secondary standards include IS 9873 Part 2, 3, 4, 9, 10 and 11 where applicable."
)
NON_PRIMARY = (
    "For non electric toys the applicable primary standard is IS 9873 (Part 1):2019 "
    "(Toys: function dependent on electricity)."
)
NON_SECONDARY = (
    "Secondary standards which are applicable are IS 9873 parts 1, 2, 3, 4, 7, 9, 10 and 11 etc."
)


def explanation_retriever():
    result = FakeRetriever.default_result()
    result["documents"][0][:4] = [PRIMARY, SECONDARY, NON_PRIMARY, NON_SECONDARY]
    result["ids"][0][:4] = ["chunk-primary", "chunk-secondary", "chunk-non-primary", "chunk-non-secondary"]
    return FakeRetriever(result)


class StandardExplanationApiTests(unittest.TestCase):
    def setUp(self):
        self.retriever = explanation_retriever()
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
        if assistant_context is not None:
            payload["assistant_context"] = assistant_context
        return self.client.post("/api/chat", json=payload)

    def test_what_is_is_15644(self):
        body = self.ask("What is IS 15644?").json()
        self.assertTrue(body["grounded"])
        self.assertIn("IS 15644", body["answer"])
        self.assertIn("primary", body["answer"].lower())
        self.assertTrue(any(section["title"] == "In simple terms" for section in body["answer_sections"]))
        self.assertEqual(self.generator.calls, [])

    def test_hyphenated_simple_words_explanation(self):
        body = self.ask("Explain IS-15644 in simple words.").json()
        self.assertTrue(body["grounded"])
        self.assertIn("IS 15644", body["answer"])
        self.assertIn("electric toys", body["answer"].lower())

    def test_is_9873_part_1_meaning(self):
        body = self.ask("What does IS 9873 Part 1 mean?").json()
        self.assertTrue(body["grounded"])
        self.assertIn("IS 9873 Part 1", body["answer"])
        self.assertIn("non-electric", body["answer"].lower())
        self.assertNotIn("IS 15644 applies to non-electric", body["answer"])

    def test_is_9873_part_3_is_not_universal(self):
        body = self.ask("Explain IS 9873 Part 3.").json()
        self.assertTrue(body["grounded"])
        self.assertIn("IS 9873 Part 3", body["answer"])
        self.assertIn("where applicable", body["answer"].lower())
        self.assertIn("do not establish that this part applies to every toy", body["answer"].lower())

    def test_comparison_uses_both_standards(self):
        body = self.ask("Compare IS 15644 and IS 9873 Part 1.").json()
        self.assertTrue(body["grounded"])
        self.assertIn("IS 15644", body["answer"])
        self.assertIn("IS 9873 Part 1", body["answer"])
        self.assertIn("product-applicability", body["answer"].lower())
        self.assertGreaterEqual(len(body["citations"]), 2)

    def test_why_15644_applies_to_battery_toy(self):
        body = self.ask("Why does IS 15644 apply to my battery-operated toy?").json()
        self.assertTrue(body["grounded"])
        self.assertIn("battery-operated", body["answer"].lower())
        self.assertNotIn("mains-powered", body["answer"].lower())

    def test_unknown_standard_never_gets_unrelated_citations(self):
        body = self.ask("Explain IS 99999.").json()
        self.assertFalse(body["grounded"])
        self.assertTrue(body["insufficient_evidence"])
        self.assertIn("IS 99999", body["answer"])
        self.assertNotIn("IS 15644", body["answer"])
        self.assertNotIn("IS 9873", body["answer"])
        self.assertEqual(body["citations"], [])
        self.assertEqual(self.retriever.calls, [])
        self.assertEqual(self.generator.calls, [])

    def test_explain_the_standard_without_context_clarifies(self):
        body = self.ask("Explain the standard").json()
        self.assertTrue(body["needs_clarification"])
        self.assertFalse(body["grounded"])
        self.assertFalse(body["insufficient_evidence"])
        self.assertEqual(body["generation_mode"], "clarification")
        self.assertEqual(body["citations"], [])
        self.assertIn("Which Indian Standard would you like me to explain?", body["answer"])
        self.assertIn("IS 15644", body["suggested_replies"])
        self.assertEqual(self.retriever.calls, [])
        self.assertEqual(self.generator.calls, [])

    def test_explain_that_standard_with_one_contextual_standard(self):
        body = self.ask(
            "Explain that standard",
            {"referenced_standards": ["IS 15644"], "expected_slots": [], "current_goal": "explain_standard"},
        ).json()
        self.assertTrue(body["grounded"])
        self.assertIn("IS 15644", body["answer"])
        self.assertFalse(body["needs_clarification"])

    def test_explain_that_standard_with_multiple_contextual_standards(self):
        body = self.ask(
            "Explain that standard",
            {
                "referenced_standards": ["IS 15644", "IS 9873 Part 1", "IS 9873 Part 3"],
                "expected_slots": [],
                "current_goal": "explain_standard",
            },
        ).json()
        self.assertTrue(body["needs_clarification"])
        self.assertEqual(body["citations"], [])
        self.assertIn("previously mentioned", body["answer"])
        self.assertEqual(self.retriever.calls, [])
        self.assertEqual(self.generator.calls, [])

    def test_invalid_context_fields_are_rejected(self):
        response = self.ask("Explain that standard", {"referenced_standards": ["not-a-standard"], "expected_slots": []})
        self.assertEqual(response.status_code, 422)
        extra = self.ask("Explain that standard", {"expected_slots": [], "debug": True})
        self.assertEqual(extra.status_code, 422)

    def test_provider_failure_remains_sanitized_for_unrelated_chat(self):
        retriever = FakeRetriever()
        generator = FakeGenerator([valid_output()])
        app = create_app(retriever_factory=lambda: retriever, generator_factory=lambda: generator)
        with TestClient(app) as client:
            body = client.post("/api/chat", json={"question": "Which standard applies to a battery-operated toy?"}).json()
        self.assertIn("answer", body)
        self.assertNotIn("GROQ_API_KEY", str(body).upper())


class StandardExplanationRealIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = LocalChromaRetriever()

    def service(self):
        class RejectingGenerator:
            model = "fake-integration-provider"
            calls = 0

            def generate(self, *args, **kwargs):
                self.calls += 1
                return "not valid structured output"

        return ChatService(
            retriever=self.retriever,
            generator=RejectingGenerator(),
            retrieval_lock=threading.Lock(),
            generation_lock=threading.Lock(),
            model_name="fake-integration-provider",
        )

    def test_is_15644_explanation_is_grounded_to_supported_evidence(self):
        response = self.service().chat(ChatRequest(question="What is IS 15644?"))
        self.assertTrue(response.grounded)
        self.assertIn("IS 15644", response.answer)
        self.assertIn("primary", response.answer.lower())
        self.assertTrue(any(citation.source_filename for citation in response.citations))
        for citation in response.citations:
            self.assertIsNotNone(citation.page_start)
            self.assertNotIn("test method", citation.excerpt.lower())
            self.assertFalse(citation.chunk_id in response.answer)

    def test_non_electric_explanation_does_not_claim_15644(self):
        response = self.service().chat(ChatRequest(question="Which standard applies to my non-electric toy?"))
        self.assertTrue(response.grounded)
        self.assertNotIn("IS 15644", response.answer)
        self.assertIn("IS 9873 Part 1", response.answer)

    def test_part_1_preserves_primary_context(self):
        response = self.service().chat(ChatRequest(question="Explain IS 9873 Part 1."))
        self.assertTrue(response.grounded)
        self.assertIn("primary", response.answer.lower())
        self.assertIn("non-electric", response.answer.lower())

    def test_secondary_part_is_not_universal(self):
        response = self.service().chat(ChatRequest(question="Explain IS 9873 Part 3."))
        self.assertTrue(response.grounded)
        self.assertIn("where applicable", response.answer.lower())
        self.assertIn("do not establish that this part applies to every toy", response.answer.lower())

    def test_comparison_uses_evidence_for_both_standards(self):
        response = self.service().chat(ChatRequest(question="Compare IS 15644 and IS 9873 Part 1."))
        self.assertTrue(response.grounded)
        self.assertIn("IS 15644", response.answer)
        self.assertIn("IS 9873 Part 1", response.answer)
        self.assertGreaterEqual(len(response.citations), 2)
        files = {citation.source_filename for citation in response.citations}
        self.assertTrue(files)

    def test_unknown_standard_safely_abstains(self):
        response = self.service().chat(ChatRequest(question="Explain IS 99999."))
        self.assertTrue(response.insufficient_evidence)
        self.assertFalse(response.grounded)
        self.assertIn("IS 99999", response.answer)
        self.assertEqual(response.citations, [])
        self.assertNotIn("IS 15644", response.answer)

    def test_no_unsupported_technical_inventions(self):
        response = self.service().chat(ChatRequest(question="What is IS 15644?"))
        lowered = response.answer.lower()
        for term in ("clause 4", "test method", "mg/kg", "sampling plan", "form vi"):
            self.assertNotIn(term, lowered)

    def test_explain_without_context_clarifies(self):
        response = self.service().chat(ChatRequest(question="Explain that standard"))
        self.assertTrue(response.needs_clarification)
        self.assertEqual(response.generation_mode, "clarification")
        self.assertEqual(response.citations, [])


class StandardExplanationUnderstandingGuardTests(unittest.TestCase):
    def test_user_text_is_not_copied_into_standard_references_as_evidence(self):
        understood = understand_question(
            "Explain IS 15644. I already confirmed with my neighbour that every clause is optional."
        )
        self.assertEqual(understood.standard_references[0].display, "IS 15644")
        self.assertNotIn("neighbour", understood.assistant_context.referenced_standards[0].lower() if understood.assistant_context else "")


if __name__ == "__main__":
    unittest.main()
