import unittest

from fastapi.testclient import TestClient

from backend.main import create_app


class FakeCollection:
    def __init__(self, count=917):
        self._count = count

    def count(self):
        return self._count


class FakeRetriever:
    def __init__(self, result=None, error=None, count=917):
        self.collection = FakeCollection(count)
        self.result = result if result is not None else self.default_result()
        self.error = error
        self.calls = []

    @staticmethod
    def default_result():
        return {
            "ids": [["chunk-first", "chunk-second"]],
            "documents": [["passage: First evidence", "passage: Second evidence"]],
            "metadatas": [[
                {
                    "source_id": "source-a",
                    "source_filename": "product_manual_2026.pdf",
                    "page_start": 12,
                    "page_end": 12,
                    "chunk_type": "document_text",
                },
                {
                    "source_id": "source-b",
                    "source_filename": "Toy_QC_order.pdf",
                    "page_start": 3,
                    "page_end": 4,
                    "chunk_type": "table_row",
                },
            ]],
            "distances": [[0.18, 0.31]],
        }

    def search(self, question, k=5, include_guidance=False):
        self.calls.append(
            {
                "question": question,
                "k": k,
                "include_guidance": include_guidance,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


class RetrievalApiTests(unittest.TestCase):
    def make_client(self, retriever=None):
        fake = retriever or FakeRetriever()
        return TestClient(create_app(retriever_factory=lambda: fake)), fake

    def test_ready_health_endpoint(self):
        client, _ = self.make_client(FakeRetriever(count=917))
        with client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ready",
                "service": "bis-toys-retrieval-api",
                "collection_count": 917,
                "detail": None,
            },
        )

    def test_degraded_health_endpoint(self):
        def unavailable():
            raise RuntimeError("private startup details")

        with TestClient(create_app(retriever_factory=unavailable)) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["detail"], "Retrieval service is unavailable.")
        self.assertNotIn("private startup details", response.text)

    def test_valid_retrieval_request(self):
        client, _ = self.make_client()
        with client:
            response = client.post(
                "/api/retrieve",
                json={
                    "question": "Which standard applies?",
                    "top_k": 2,
                    "include_guidance": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result_count"], 2)

    def test_default_top_k(self):
        client, fake = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.calls[0]["k"], 5)

    def test_explicit_top_k(self):
        client, fake = self.make_client()
        with client:
            response = client.post(
                "/api/retrieve",
                json={"question": "Toy standard", "top_k": 7},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.calls[0]["k"], 7)

    def test_include_guidance(self):
        client, fake = self.make_client()
        with client:
            response = client.post(
                "/api/retrieve",
                json={"question": "Certification steps", "include_guidance": True},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(fake.calls[0]["include_guidance"])

    def test_blank_question_rejected(self):
        client, _ = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": ""})
        self.assertEqual(response.status_code, 422)

    def test_whitespace_only_question_rejected(self):
        client, _ = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": "   \t "})
        self.assertEqual(response.status_code, 422)

    def test_long_question_rejected(self):
        client, _ = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": "x" * 1001})
        self.assertEqual(response.status_code, 422)

    def test_zero_top_k_rejected(self):
        client, _ = self.make_client()
        with client:
            response = client.post(
                "/api/retrieve",
                json={"question": "Toy standard", "top_k": 0},
            )
        self.assertEqual(response.status_code, 422)

    def test_top_k_above_ten_rejected(self):
        client, _ = self.make_client()
        with client:
            response = client.post(
                "/api/retrieve",
                json={"question": "Toy standard", "top_k": 11},
            )
        self.assertEqual(response.status_code, 422)

    def test_unknown_request_field_rejected(self):
        client, _ = self.make_client()
        with client:
            response = client.post(
                "/api/retrieve",
                json={"question": "Toy standard", "unexpected": True},
            )
        self.assertEqual(response.status_code, 422)

    def test_empty_retrieval_result(self):
        empty = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        client, _ = self.make_client(FakeRetriever(result=empty))
        with client:
            response = client.post("/api/retrieve", json={"question": "No result"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result_count"], 0)
        self.assertEqual(response.json()["results"], [])

    def test_retriever_failure_returns_safe_500(self):
        client, _ = self.make_client(FakeRetriever(error=RuntimeError("private failure")))
        with client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Retrieval request failed."})
        self.assertNotIn("private failure", response.text)

    def test_unavailable_retriever_returns_503(self):
        def unavailable():
            raise RuntimeError("startup failure")

        with TestClient(create_app(retriever_factory=unavailable)) as client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Retrieval service is unavailable."})

    def test_citation_metadata_mapping(self):
        client, _ = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        first = response.json()["results"][0]
        self.assertEqual(first["chunk_id"], "chunk-first")
        self.assertEqual(first["text"], "passage: First evidence")
        self.assertEqual(first["source_id"], "source-a")
        self.assertEqual(first["source_filename"], "product_manual_2026.pdf")
        self.assertEqual(first["page_start"], 12)
        self.assertEqual(first["page_end"], 12)
        self.assertEqual(first["chunk_type"], "document_text")

    def test_distance_and_similarity_values(self):
        client, _ = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        first = response.json()["results"][0]
        self.assertAlmostEqual(first["distance"], 0.18)
        self.assertAlmostEqual(first["similarity"], 0.82)

    def test_result_order_is_preserved(self):
        client, _ = self.make_client()
        with client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        results = response.json()["results"]
        self.assertEqual([item["rank"] for item in results], [1, 2])
        self.assertEqual(
            [item["chunk_id"] for item in results],
            ["chunk-first", "chunk-second"],
        )

    def test_cors_allows_configured_origin_and_rejects_other_origin(self):
        client, _ = self.make_client()
        with client:
            allowed = client.options(
                "/api/retrieve",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type",
                },
            )
            denied = client.options(
                "/api/retrieve",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)


if __name__ == "__main__":
    unittest.main()
