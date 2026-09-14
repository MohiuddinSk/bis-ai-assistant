import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.retrieval_provider import RetrievalHit


class TrackingGenerator:
    model = "tracking-generator"

    def __init__(self):
        self.calls = []

    def generate(self, question, evidence, **kwargs):
        self.calls.append((question, evidence, kwargs))
        raise AssertionError("generator must not receive retrieval-disabled requests")


class RetrievalDisabledApiTests(unittest.TestCase):
    def environment(self, **values):
        base = {
            "RETRIEVAL_PROVIDER": "disabled",
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "",
            "GROQ_MODEL": "",
            "LLM_API_KEY": "",
            "LLM_BASE_URL": "",
            "LLM_MODEL": "",
            "LLM_ALLOWED_HOSTS": "",
        }
        base.update(values)
        return patch.dict("os.environ", base, clear=True)

    def test_disabled_routes_are_sanitized_equivalent_and_do_not_construct_or_call_providers(self):
        generator = TrackingGenerator()
        private = "C:\\private\\retrieval-sentinel"
        with self.environment(RETRIEVAL_LOCAL_PATH=private), patch("backend.retrieval_factory.LocalChromaRetriever") as local:
            with self.assertNoLogs("backend", level="WARNING"), TestClient(create_app(generator_factory=lambda: generator)) as client:
                health = [client.get(path, headers={"X-Request-ID": "disabled-request-001"}) for path in ("/health", "/api/v1/health")]
                retrieve = [client.post(path, headers={"X-Request-ID": "disabled-request-001"}, json={"question": "question-sentinel"}) for path in ("/api/retrieve", "/api/v1/retrieve")]
                chat = [client.post(path, headers={"X-Request-ID": "disabled-request-001"}, json={"question": "question-sentinel"}) for path in ("/api/chat", "/api/v1/chat")]
        local.assert_not_called()
        self.assertEqual(health[0].status_code, health[1].status_code)
        self.assertEqual(health[0].json(), health[1].json())
        self.assertEqual(health[0].status_code, 503)
        self.assertEqual(retrieve[0].json(), retrieve[1].json())
        self.assertEqual(retrieve[0].json(), {"detail": "Retrieval service is unavailable."})
        self.assertEqual(chat[0].json(), chat[1].json())
        self.assertEqual(chat[0].json(), {"detail": "Retrieval service is unavailable."})
        for response in [*health, *retrieve, *chat]:
            self.assertEqual(response.headers["x-request-id"], "disabled-request-001")
            self.assertNotIn(private, response.text)
            self.assertNotIn(private, str(response.headers))
        self.assertEqual(generator.calls, [])

    def test_retrieval_disabled_generation_enabled_constructs_generator_without_requests(self):
        generator = TrackingGenerator()
        constructed = []
        with self.environment(LLM_PROVIDER="openai_compatible", LLM_API_KEY="private-key"), patch("backend.retrieval_factory.LocalChromaRetriever") as local:
            with TestClient(create_app(generator_factory=lambda: constructed.append(generator) or generator)) as client:
                response = client.post("/api/chat", json={"question": "question-sentinel"})
        local.assert_not_called()
        self.assertEqual(constructed, [generator])
        self.assertEqual(generator.calls, [])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Retrieval service is unavailable."})

    def test_retrieval_enabled_generation_disabled_constructs_retriever(self):
        class LocalProvider:
            def count(self): return 1
            def search(self, question, k=5, include_guidance=False):
                return [RetrievalHit("chunk", "text", {"source_filename": "source.pdf", "page_start": 1, "page_end": 1}, 0.1)]

        provider = LocalProvider()
        with self.environment(RETRIEVAL_PROVIDER="chroma_local", LLM_PROVIDER="disabled"), patch("backend.retrieval_factory.LocalChromaRetriever", return_value=provider) as local:
            with TestClient(create_app()) as client:
                health = client.get("/health")
                retrieve = client.post("/api/retrieve", json={"question": "question-sentinel"})
        local.assert_called_once_with()
        self.assertEqual(health.status_code, 200)
        self.assertEqual(retrieve.status_code, 200)
        self.assertEqual(retrieve.json()["results"][0]["chunk_id"], "chunk")

    def test_both_disabled_constructs_neither_provider_client(self):
        with self.environment(LLM_PROVIDER="disabled"), patch("backend.retrieval_factory.LocalChromaRetriever") as local, patch("backend.generation_factory.GroqGenerator") as groq, patch("backend.generation_factory.OpenAICompatibleGenerator") as generic:
            with TestClient(create_app()) as client:
                response = client.get("/api/v1/health")
        local.assert_not_called()
        groq.assert_not_called()
        generic.assert_not_called()
        self.assertEqual(response.status_code, 503)

    def test_unknown_retrieval_provider_has_no_local_fallback(self):
        generator = TrackingGenerator()
        with self.environment(RETRIEVAL_PROVIDER="unknown-retriever"), patch("backend.retrieval_factory.LocalChromaRetriever") as local:
            with TestClient(create_app(generator_factory=lambda: generator)) as client:
                health = client.get("/health")
                retrieve = client.post("/api/v1/retrieve", json={"question": "question-sentinel"})
                chat = client.post("/api/v1/chat", json={"question": "question-sentinel"})
        local.assert_not_called()
        self.assertEqual(health.status_code, 503)
        self.assertEqual(retrieve.json(), {"detail": "Retrieval service is unavailable."})
        self.assertEqual(chat.json(), {"detail": "Retrieval service is unavailable."})
        self.assertEqual(generator.calls, [])


if __name__ == "__main__":
    unittest.main()
