"""Availability tests for deliberately unavailable generation providers."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.test_chat_api import FakeRetriever


class CompletePlanRetriever(FakeRetriever):
    @staticmethod
    def default_result():
        return {
            "ids": [["primary", "secondary"]],
            "documents": [[
                "For electric toys, the primary standard is IS 15644:2006.",
                "Applicable secondary standards include IS 9873 Parts 2 and 3.",
            ]],
            "metadatas": [[
                {"source_id": "primary", "source_filename": "manual.pdf", "page_start": 1, "page_end": 1, "chunk_type": "document_text"},
                {"source_id": "secondary", "source_filename": "manual.pdf", "page_start": 2, "page_end": 2, "chunk_type": "document_text"},
            ]],
            "distances": [[0.1, 0.2]],
        }


class ProviderUnavailableApiTests(unittest.TestCase):
    @contextmanager
    def assert_no_provider_construction(self, provider, retriever_factory=FakeRetriever):
        environment = {"LLM_PROVIDER": provider, "GROQ_MODEL": "irrelevant", "LLM_MODEL": "irrelevant", "LLM_BASE_URL": "https://example.test/v1", "LLM_ALLOWED_HOSTS": "example.test"}
        with patch.dict("os.environ", environment, clear=True), patch("backend.generation_factory.GroqGenerator") as groq, patch("backend.generation_factory.OpenAICompatibleGenerator") as generic, patch("backend.openai_compatible_generator.httpx.Client") as http_client:
            app = create_app(retriever_factory=retriever_factory)
            with TestClient(app) as client:
                yield client
            groq.assert_not_called()
            generic.assert_not_called()
            http_client.assert_not_called()

    def test_disabled_startup_health_and_retrieval_aliases_remain_available(self):
        with self.assert_no_provider_construction("disabled") as client:
            health = client.get("/health")
            versioned_health = client.get("/api/v1/health")
            retrieve = client.post("/api/retrieve", json={"question": "toy standard"})
            versioned_retrieve = client.post("/api/v1/retrieve", json={"question": "toy standard"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ready")
        self.assertEqual(versioned_health.status_code, 200)
        self.assertEqual(health.json(), versioned_health.json())
        self.assertEqual(retrieve.status_code, 200)
        self.assertEqual(versioned_retrieve.status_code, 200)
        self.assertEqual(retrieve.json(), versioned_retrieve.json())

    def test_disabled_deterministic_chat_paths_work_without_generator(self):
        profile_question = {"question": "I am a manufacturer making a battery-operated toy car."}
        wizard = {"role": "manufacturer", "product_description": "Toy car", "power_type": "not_sure", "intended_age_group": "3_to_8", "goal": "identify_standards", "application_stage": "researching", "additional_context": None}
        with self.assert_no_provider_construction("disabled") as client:
            legacy = client.post("/api/chat", json=profile_question)
            versioned = client.post("/api/v1/chat", json=profile_question)
            guidance = client.post("/api/compliance/guide", json=wizard)
        self.assertEqual(legacy.status_code, 200)
        self.assertTrue(legacy.json()["needs_clarification"])
        self.assertEqual(legacy.json()["generation_mode"], "clarification")
        self.assertEqual(legacy.json(), versioned.json())
        self.assertEqual(guidance.status_code, 200)
        self.assertTrue(guidance.json()["guidance"]["needs_clarification"])
        self.assertEqual(guidance.json()["guidance"]["generation_mode"], "clarification")

    def test_disabled_complete_evidence_plan_uses_deterministic_response(self):
        with self.assert_no_provider_construction("disabled", CompletePlanRetriever) as client:
            response = client.post("/api/chat", json={"question": "Which standard applies to a battery-operated toy?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generation_mode"], "extractive_fallback")
        self.assertTrue(response.json()["grounded"])

    def test_disabled_generation_required_request_is_sanitized_503_with_request_id(self):
        with self.assert_no_provider_construction("disabled") as client:
            response = client.post("/api/chat", json={"question": "Tell me about BIS toy regulation"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Chat generation is unavailable."})
        self.assertIn("x-request-id", response.headers)
        self.assertNotIn("provider", response.text.lower())

    def test_unknown_provider_keeps_health_and_retrieval_available_without_groq_fallback(self):
        with self.assert_no_provider_construction("not-a-provider") as client:
            health = client.get("/health")
            retrieve = client.post("/api/retrieve", json={"question": "toy standard"})
            response = client.post("/api/chat", json={"question": "Tell me about BIS toy regulation"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(retrieve.status_code, 200)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Chat generation is unavailable."})


if __name__ == "__main__":
    unittest.main()
