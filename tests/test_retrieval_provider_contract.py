import unittest

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.retrieval_provider import LocalChromaRetriever, RetrievalHit
from backend.schemas import RetrieveRequest
from backend.service import RetrievalService


class RawLocalRetriever:
    def __init__(self, result):
        self.result = result
        self.collection = type("Collection", (), {"count": lambda _: 917})()

    def search(self, question, k=5, include_guidance=False):
        return self.result

    def adjacent_chunks(self, chunk_id, source_id, page_start):
        return [{"chunk_id": "adjacent", "text": "adjacent text", "source_id": source_id, "source_filename": "source.pdf", "page_start": page_start, "page_end": page_start, "chunk_type": "document_text"}]


def raw_result():
    return {
        "ids": [["first", "second"]],
        "documents": [["first text", "second text"]],
        "metadatas": [[
            {"source_id": "source", "source_filename": "source.pdf", "page_start": 1, "page_end": 1, "chunk_type": "document_text"},
            {"source_id": "source", "source_filename": "source.pdf", "page_start": 2, "page_end": 2, "chunk_type": "document_text"},
        ]],
        "distances": [[0.1, 0.2]],
    }


class RetrievalProviderContractTests(unittest.TestCase):
    def test_local_adapter_normalizes_order_metadata_distance_count_and_adjacent_hits(self):
        adapter = LocalChromaRetriever(RawLocalRetriever(raw_result()))
        hits = adapter.search("question", k=2)
        self.assertEqual([hit.chunk_id for hit in hits], ["first", "second"])
        self.assertEqual(hits[0].metadata["source_filename"], "source.pdf")
        self.assertEqual([hit.distance for hit in hits], [0.1, 0.2])
        self.assertEqual(adapter.count(), 917)
        self.assertEqual(adapter.adjacent_chunks("first", "source", 1)[0].chunk_id, "adjacent")

    def test_local_adapter_empty_and_malformed_results_fail_closed(self):
        empty = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        self.assertEqual(LocalChromaRetriever(RawLocalRetriever(empty)).search("question"), [])
        malformed = raw_result(); malformed["documents"] = [["first text"]]
        with self.assertRaisesRegex(ValueError, "invalid results"):
            LocalChromaRetriever(RawLocalRetriever(malformed)).search("question")

    def test_service_preserves_public_semantics_and_rejects_invalid_hits(self):
        class Provider:
            def count(self): return 1
            def search(self, question, k=5, include_guidance=False):
                return [RetrievalHit("chunk", "text", {"source_filename": "source.pdf", "page_start": 1, "page_end": 1}, 0.25)]

        response = RetrievalService(Provider()).retrieve(RetrieveRequest(question="question"))
        self.assertEqual(response.model_dump(), {"question": "question", "result_count": 1, "results": [{"rank": 1, "chunk_id": "chunk", "text": "text", "source_id": None, "source_filename": "source.pdf", "page_start": 1, "page_end": 1, "chunk_type": None, "distance": 0.25, "similarity": 0.75}]})
        for distance in (True, float("nan"), float("inf")):
            class InvalidProvider:
                def count(self): return 1
                def search(self, question, k=5, include_guidance=False): return [RetrievalHit("chunk", "text", {}, distance)]
            with self.subTest(distance=repr(distance)), self.assertRaisesRegex(ValueError, "invalid results") as raised:
                RetrievalService(InvalidProvider()).retrieve(RetrieveRequest(question="question"))
            self.assertNotIn("private", str(raised.exception))
        for hit in (RetrievalHit("", "text", {}, 0.1), RetrievalHit("chunk", "", {}, 0.1), RetrievalHit("chunk", "text", {"page_start": 0}, 0.1)):
            class InvalidMetadataProvider:
                def count(self): return 1
                def search(self, question, k=5, include_guidance=False): return [hit]
            with self.subTest(hit=repr(hit)), self.assertRaisesRegex(ValueError, "invalid results"):
                RetrievalService(InvalidMetadataProvider()).retrieve(RetrieveRequest(question="question"))

    def test_application_uses_count_without_collection_and_preserves_route_parity(self):
        class Provider:
            def count(self): return 3
            def search(self, question, k=5, include_guidance=False): return []

        with TestClient(create_app(retriever_factory=Provider, generator_factory=lambda: None)) as client:
            legacy = client.get("/health")
            versioned = client.get("/api/v1/health")
            retrieve = client.post("/api/retrieve", json={"question": "question"})
            retrieve_v1 = client.post("/api/v1/retrieve", json={"question": "question"})
        self.assertEqual(legacy.json(), versioned.json())
        self.assertEqual(legacy.json()["collection_count"], 3)
        self.assertEqual(retrieve.json(), retrieve_v1.json())

    def test_application_constructor_failure_stays_degraded_and_logs_safely(self):
        sentinel = "private constructor detail C:\\private\\path"
        factory = lambda: (_ for _ in ()).throw(RuntimeError(sentinel))
        with self.assertLogs("backend.main", level="ERROR") as captured:
            with TestClient(create_app(retriever_factory=factory, generator_factory=lambda: None)) as client:
                response = client.get("/health")
        surface = "\n".join(captured.output)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Retrieval service is unavailable.")
        self.assertIn("event=retrieval_initialization_failed", surface)
        self.assertNotIn(sentinel, surface)
        self.assertNotIn("Traceback", surface)
        self.assertNotIn("C:\\private\\path", surface)

    def test_application_count_failure_stays_degraded_and_logs_safely(self):
        class CountFailureProvider:
            def count(self): raise RuntimeError("private count detail C:\\private\\path")
            def search(self, question, k=5, include_guidance=False): return []

        with self.assertLogs("backend.main", level="ERROR") as captured:
            with TestClient(create_app(retriever_factory=CountFailureProvider, generator_factory=lambda: None)) as client:
                response = client.get("/health")
        surface = "\n".join(captured.output)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Retrieval service is unavailable.")
        self.assertIn("event=retrieval_count_failed", surface)
        self.assertNotIn("private count detail", surface)
        self.assertNotIn("Traceback", surface)
        self.assertNotIn("C:\\private\\path", surface)

    def test_search_failures_remain_sanitized_and_log_safe_request_ids(self):
        question = "question-sentinel"
        exception_sentinel = "private failure C:\\private\\path evidence-sentinel"
        request_id = "retrieval-request-001"

        class SearchFailureProvider:
            def count(self): return 1
            def search(self, question, k=5, include_guidance=False): raise RuntimeError(exception_sentinel)

        with self.assertLogs("backend.main", level="ERROR") as captured:
            with TestClient(create_app(retriever_factory=SearchFailureProvider, generator_factory=lambda: None)) as client:
                responses = [client.post(path, headers={"X-Request-ID": request_id}, json={"question": question}) for path in ("/api/retrieve", "/api/v1/retrieve")]
        surface = "\n".join(captured.output)
        for response in responses:
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"detail": "Retrieval request failed."})
            self.assertEqual(response.headers["x-request-id"], request_id)
        self.assertEqual(surface.count("event=retrieval_request_failed"), 2)
        self.assertIn("request_id=retrieval-request-001", surface)
        for sentinel in (question, exception_sentinel, "evidence-sentinel", "C:\\private\\path", "Traceback"):
            self.assertNotIn(sentinel, surface)


if __name__ == "__main__":
    unittest.main()
