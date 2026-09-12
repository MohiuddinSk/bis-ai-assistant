import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient

from backend.generation import (
    GroqGenerator,
    GROQ_RESPONSE_SCHEMA,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderCompletionExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from backend.main import create_app
from backend.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.settings import GenerationSettings, INSUFFICIENT_EVIDENCE_ANSWER, get_generation_settings


EVIDENCE_QUOTES = {
    "S1": "Exact battery-operated toy evidence",
    "S2": "Second battery-operated toy standard evidence",
    "S3": "Third battery-operated toy conditions evidence",
    "S4": "Fourth battery-operated toy limitations evidence",
    "S5": "Fifth battery-operated toy order evidence",
}


class FakeCollection:
    def count(self):
        return 917


class FakeRetriever:
    def __init__(self, result=None):
        self.collection = FakeCollection()
        self.result = result if result is not None else self.default_result()
        self.calls = []

    @staticmethod
    def default_result():
        return {
            "ids": [[f"chunk-{index}" for index in range(1, 6)]],
            "documents": [[
                "passage: Exact battery-operated toy evidence",
                "passage: Second battery-operated toy standard evidence",
                "passage: Third battery-operated toy conditions evidence",
                "passage: Fourth battery-operated toy limitations evidence",
                "passage: Fifth battery-operated toy order evidence",
            ]],
            "metadatas": [[
                {
                    "source_id": f"source-{index}",
                    "source_filename": (
                        "product_manual_2026.pdf" if index < 5 else "Toy_QC_order.pdf"
                    ),
                    "page_start": index + 10,
                    "page_end": index + 10,
                    "chunk_type": "document_text",
                }
                for index in range(1, 6)
            ]],
            "distances": [[0.1, 0.2, 0.3, 0.4, 0.5]],
        }

    def search(self, question, k=5, include_guidance=False):
        self.calls.append(
            {
                "question": question,
                "k": k,
                "include_guidance": include_guidance,
            }
        )
        return self.result


class FakeGenerator:
    model = "openai/gpt-oss-120b"

    def __init__(self, outputs=None):
        self.outputs = list(outputs or [valid_output()])
        self.calls = []

    def generate(self, question, evidence, *, repair=False, concise=False, repair_feedback=None):
        self.calls.append(
            {"question": question, "evidence": evidence, "repair": repair, "concise": concise, "repair_feedback": repair_feedback}
        )
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def valid_output(citation_ids=None, citations=None, **overrides):
    citation_ids = citation_ids if citation_ids is not None else ["S1"]
    payload = {
        "answer": "IS 15644 applies according to the supplied evidence.",
        "citations": citations if citations is not None else [
            {"citation_id": citation_id, "supporting_quote": EVIDENCE_QUOTES.get(
                citation_id, "passage: Unknown but sufficiently long evidence quote"
            )}
            for citation_id in citation_ids
        ],
        "insufficient_evidence": False,
    }
    payload.update(overrides)
    return json.dumps(payload)


class GroundedChatApiTests(unittest.TestCase):
    def assert_closed_required_schema(self, schema):
        self.assertEqual(schema.get("type"), "object")
        self.assertFalse(schema.get("additionalProperties", True))
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        for property_schema in schema["properties"].values():
            if property_schema.get("type") == "object":
                self.assert_closed_required_schema(property_schema)
            if property_schema.get("type") == "array":
                self.assert_closed_required_schema(property_schema["items"])

    def request(self, *, retriever=None, generator=None, payload=None):
        retriever = retriever or FakeRetriever()
        generator = generator or FakeGenerator()
        app = create_app(
            retriever_factory=lambda: retriever,
            generator_factory=lambda: generator,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json=payload
                or {
                    "question": "Which standard applies to a battery-operated toy?",
                    "top_k": 5,
                    "include_guidance": False,
                },
            )
        return response, retriever, generator

    def test_valid_grounded_answer(self):
        response, retriever, generator = self.request()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["grounded"])
        self.assertFalse(body["insufficient_evidence"])
        self.assertEqual(body["evidence_count"], 5)
        self.assertEqual(body["model"], generator.model)
        self.assertEqual(retriever.calls[0]["k"], 8)

    def test_citation_metadata_mapping(self):
        response, _, _ = self.request()
        citation = response.json()["citations"][0]
        self.assertEqual(citation["citation_id"], "S1")
        self.assertEqual(citation["source_filename"], "product_manual_2026.pdf")
        self.assertEqual(citation["page_start"], 11)
        self.assertEqual(citation["page_end"], 11)
        self.assertEqual(citation["chunk_id"], "chunk-1")
        self.assertEqual(
            citation["excerpt"],
            "Exact battery-operated toy evidence",
        )

    def test_battery_answer_labels_primary_and_secondary_standards(self):
        primary = "For electric toys, the primary standard is IS 15644:2006."
        secondary = "Applicable secondary standards include IS 9873 Parts 2 and 3."
        result = FakeRetriever.default_result()
        result["documents"][0][:2] = [primary, secondary]
        answer = (
            "For a battery-operated (electric) toy, the primary standard is "
            "IS 15644:2006. IS 9873 Parts 2 and 3 are additional secondary standards."
        )
        generated = valid_output(citations=[
            {"citation_id": "S1", "supporting_quote": primary},
            {"citation_id": "S2", "supporting_quote": secondary},
        ], answer=answer)
        response, _, _ = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([generated])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("primary standard is IS 15644", response.json()["answer"])
        self.assertIn("secondary standards", response.json()["answer"])

    def test_coverage_query_merges_deduplicates_and_retains_primary_standard(self):
        primary = "For electric toys, the primary standard is IS 15644:2006."
        secondary = "Applicable secondary standards include IS 9873 Parts 2 and 3."

        class CoverageRetriever(FakeRetriever):
            def search(self, question, k=5, include_guidance=False):
                self.calls.append({"question": question, "k": k, "include_guidance": include_guidance})
                result = self.default_result()
                if question == "electric toy applicable primary standard IS 15644":
                    result["documents"][0][:2] = [primary, secondary]
                    result["ids"][0][:2] = ["coverage-primary", "coverage-secondary"]
                return result

        answer = "The primary standard is IS 15644:2006; IS 9873 Parts 2 and 3 are secondary standards."
        generated = valid_output(citations=[
            {"citation_id": "S1", "supporting_quote": primary},
            {"citation_id": "S2", "supporting_quote": secondary},
        ], answer=answer)
        response, retriever, generator = self.request(
            retriever=CoverageRetriever(), generator=FakeGenerator([generated])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len({item["question"] for item in retriever.calls}), 2)
        self.assertIn("electric toy applicable primary standard IS 15644", [item["question"] for item in retriever.calls])
        self.assertEqual(generator.calls, [])

    def test_secondary_only_answer_repairs_when_primary_evidence_is_available(self):
        primary = "For electric toys, the primary standard is IS 15644:2006."
        secondary = "Applicable secondary standards include IS 9873 Parts 2 and 3."
        result = FakeRetriever.default_result()
        result["documents"][0][:2] = [primary, secondary]
        unsafe = valid_output(
            citations=[{"citation_id": "S2", "supporting_quote": secondary}],
            answer="IS 9873 Parts 2 and 3 are secondary standards.",
        )
        safe = valid_output(citations=[
            {"citation_id": "S1", "supporting_quote": primary},
            {"citation_id": "S2", "supporting_quote": secondary},
        ], answer="IS 15644:2006 is the primary standard; IS 9873 Parts 2 and 3 are secondary standards.")
        response, _, generator = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([unsafe, safe])
        )
        self.assertTrue(response.json()["grounded"])
        self.assertEqual(generator.calls, [])

    def test_complete_battery_evidence_uses_extractive_fallback_after_two_model_failures(self):
        primary = "For electric toys, the primary standard is IS 15644:2006."
        secondary = "Applicable secondary standards include IS 9873 Parts 2 and 3."
        result = FakeRetriever.default_result()
        result["documents"][0][:2] = [primary, secondary]
        invalid = valid_output(citations=[{"citation_id": "S2", "supporting_quote": secondary}], answer="IS 9873 is secondary.")
        response, _, generator = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([invalid, invalid])
        )
        body = response.json()
        self.assertTrue(body["grounded"])
        self.assertEqual(body["generation_mode"], "extractive_fallback")
        self.assertEqual(body["model"], "extractive-evidence-fallback")
        self.assertEqual(len(body["citations"]), 2)
        self.assertEqual(len(generator.calls), 0)

    def test_partial_artisan_quote_before_registration_is_rejected(self):
        partial = "Provided further that nothing in this Order shall apply to goods or articles manufactured and sold by Artisans"
        qualification = "registered with Office of the Development Commissioner (Handicrafts), under Ministry of Textiles, Government of India"
        result = FakeRetriever.default_result()
        result["documents"][0][:2] = [partial, qualification]
        unsafe = valid_output(citations=[{"citation_id": "S1", "supporting_quote": partial}], answer="No, not all handmade toys are exempt.")
        response, _, generator = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([unsafe, unsafe]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertTrue(response.json()["grounded"])
        self.assertEqual(response.json()["generation_mode"], "extractive_fallback")
        self.assertNotEqual(response.json()["model"], "openai/gpt-oss-120b")
        self.assertEqual(len(generator.calls), 0)

    def test_split_artisan_citations_collectively_satisfy_qualification(self):
        scope = "Provided further that nothing in this Order shall apply to goods or articles manufactured and sold by Artisans"
        registration = "registered with Office of the Development Commissioner (Handicrafts), under Ministry of Textiles, Government of India"
        result = FakeRetriever.default_result()
        result["documents"][0][:2] = [scope, registration]
        answer = (
            "No, not all handmade toys are automatically exempt. The exception applies to goods or articles "
            "manufactured and sold by artisans registered with the Office of the Development Commissioner "
            "(Handicrafts), under the Ministry of Textiles."
        )
        generated = valid_output(citations=[
            {"citation_id": "S1", "supporting_quote": scope},
            {"citation_id": "S2", "supporting_quote": registration},
        ], answer=answer)
        response, _, _ = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([generated]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertTrue(response.json()["grounded"])
        self.assertEqual([item["excerpt"] for item in response.json()["citations"]], [scope, registration])

    def test_artisan_repair_receives_safe_reason_and_evidence_ids(self):
        scope = "Provided further that nothing in this Order shall apply to goods or articles manufactured and sold by Artisans"
        registration = "registered with Office of the Development Commissioner (Handicrafts), under Ministry of Textiles, Government of India"
        result = FakeRetriever.default_result()
        result["documents"][0][:2] = [scope, registration]
        incomplete = valid_output(citations=[{"citation_id": "S1", "supporting_quote": scope}], answer="No, not all handmade toys are exempt.")
        complete = valid_output(citations=[
            {"citation_id": "S1", "supporting_quote": scope},
            {"citation_id": "S2", "supporting_quote": registration},
        ], answer=("No, not all handmade toys are automatically exempt. It applies to goods or articles manufactured "
                 "and sold by artisans registered with the Office of the Development Commissioner (Handicrafts), "
                 "under the Ministry of Textiles."))
        response, _, generator = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([incomplete, complete]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertTrue(response.json()["grounded"])
        self.assertEqual(generator.calls, [])

    def test_missing_complete_artisan_evidence_safely_abstains(self):
        partial = "Provided further that nothing in this Order shall apply to goods or articles manufactured and sold by Artisans"
        result = FakeRetriever.default_result()
        result["documents"][0][0] = partial
        generated = valid_output(citations=[{"citation_id": "S1", "supporting_quote": partial}], answer="No, not all handmade toys are exempt.")
        response, _, _ = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([generated, generated]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertTrue(response.json()["insufficient_evidence"])

    def test_conditional_artisan_exemption_preserves_qualifications(self):
        quote = (
            "nothing in this Order shall apply to goods or articles manufactured and "
            "sold by Artisans registered with Office of the Development Commissioner "
            "(Handicrafts), under Ministry of Textiles, Government of India"
        )
        result = FakeRetriever.default_result()
        result["documents"][0][0] = "passage: " + quote
        answer = (
            "No, not all handmade toys are automatically exempt. The exception applies "
            "to goods or articles manufactured and sold by artisans registered with the "
            "Office of the Development Commissioner (Handicrafts), Ministry of Textiles."
        )
        generated = valid_output(citations=[{"citation_id": "S1", "supporting_quote": quote}], answer=answer)
        response, _, _ = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([generated]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["grounded"])
        excerpt = response.json()["citations"][0]["excerpt"]
        self.assertIn(excerpt, "passage: " + quote)
        self.assertEqual(excerpt, quote)  # backend cleaned only the indexing prefix
        self.assertIn("manufactured and sold", response.json()["answer"])
        self.assertIn("registered", response.json()["answer"])

    def test_conditional_artisan_evidence_cannot_support_universal_yes(self):
        quote = "Artisans registered with the Office of the Development Commissioner are exempt."
        result = FakeRetriever.default_result()
        result["documents"][0][0] = quote
        unsafe = valid_output(citations=[{"citation_id": "S1", "supporting_quote": quote}], answer="Yes, all handmade toys are exempt.")
        response, _, generator = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([unsafe, unsafe]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertEqual(len(generator.calls), 2)
        self.assertTrue(response.json()["insufficient_evidence"])

    def test_invented_quote_is_rejected(self):
        hint = "This invented supporting quote does not exist anywhere."
        generated = valid_output(citations=[{"citation_id": "S1", "supporting_quote": hint}])
        response, _, generator = self.request(generator=FakeGenerator([generated, generated]))
        self.assertEqual(len(generator.calls), 2)
        self.assertTrue(response.json()["insufficient_evidence"])

    def test_quote_from_wrong_evidence_id_is_rejected(self):
        generated = valid_output(citations=[{"citation_id": "S1", "supporting_quote": EVIDENCE_QUOTES["S2"]}])
        response, _, generator = self.request(generator=FakeGenerator([generated, generated]))
        self.assertEqual(len(generator.calls), 2)
        self.assertTrue(response.json()["insufficient_evidence"])

    def test_backend_excerpt_preserves_unicode_when_model_hint_differs(self):
        source = "IS 15644—primary electric-toy standard."
        result = FakeRetriever.default_result()
        result["documents"][0][0] = source
        generated = valid_output(
            citations=[{"citation_id": "S1", "supporting_quote": source}],
            answer="IS 15644 is the primary standard.",
        )
        response, _, _ = self.request(retriever=FakeRetriever(result), generator=FakeGenerator([generated]))
        self.assertTrue(response.json()["grounded"])
        self.assertEqual(response.json()["citations"][0]["excerpt"], source)

    def test_preamble_only_quote_cannot_support_exemption_question(self):
        preamble = "In exercise of the powers conferred by the Bureau of Indian Standards Act."
        result = FakeRetriever.default_result()
        result["documents"][0][0] = preamble
        invalid = valid_output(citations=[{"citation_id": "S1", "supporting_quote": preamble}], answer="No, not all handmade toys are exempt.")
        response, _, _ = self.request(
            retriever=FakeRetriever(result), generator=FakeGenerator([invalid, invalid]),
            payload={"question": "Are all handmade toys exempt?"},
        )
        self.assertTrue(response.json()["insufficient_evidence"])

    def test_citation_order_preserved(self):
        generator = FakeGenerator([valid_output(["S3", "S1", "S2"])])
        response, _, _ = self.request(generator=generator)
        self.assertEqual(
            [item["citation_id"] for item in response.json()["citations"]],
            ["S3", "S1", "S2"],
        )

    def test_duplicate_citations_removed_in_order(self):
        generator = FakeGenerator([valid_output(["S2", "S2", "S1", "S2"])])
        response, _, _ = self.request(generator=generator)
        self.assertEqual(
            [item["citation_id"] for item in response.json()["citations"]],
            ["S2", "S1"],
        )

    def test_unknown_citation_rejected_after_retry(self):
        generator = FakeGenerator([valid_output(["S99"]), valid_output(["S99"])])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])
        self.assertEqual(len(generator.calls), 2)
        self.assertNotIn("S99", response.text)

    def test_missing_citation_rejected_for_grounded_answer(self):
        generator = FakeGenerator([valid_output([]), valid_output([])])
        response, _, _ = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])

    def test_insufficient_evidence_forces_safe_abstention(self):
        unsafe = valid_output(
            [],
            answer="All handmade toys are exempt.",
            insufficient_evidence=True,
        )
        response, _, _ = self.request(generator=FakeGenerator([unsafe]))
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(body["grounded"])
        self.assertTrue(body["insufficient_evidence"])
        self.assertEqual(body["answer"], INSUFFICIENT_EVIDENCE_ANSWER)
        self.assertNotIn("All handmade toys are exempt", body["answer"])

    def test_no_retrieval_results_abstains_without_generation(self):
        empty = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        generator = FakeGenerator([AssertionError("generator must not be called")])
        response, _, generator = self.request(
            retriever=FakeRetriever(empty),
            generator=generator,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])
        self.assertEqual(response.json()["evidence_count"], 0)
        self.assertEqual(generator.calls, [])

    def test_provider_unavailable_returns_503(self):
        def unavailable():
            raise ProviderUnavailableError("not configured")

        app = create_app(
            retriever_factory=FakeRetriever,
            generator_factory=unavailable,
        )
        with TestClient(app) as client:
            response = client.post("/api/chat", json={"question": "Tell me about BIS toy regulation"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Chat generation is unavailable."})

    def test_provider_authentication_failure_returns_safe_503(self):
        generator = FakeGenerator([ProviderUnavailableError("secret auth body")])
        response, _, _ = self.request(generator=generator)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret auth body", response.text)

    def test_provider_timeout_returns_504(self):
        response, _, _ = self.request(
            generator=FakeGenerator([ProviderTimeoutError("timeout details")])
        )
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json(), {"detail": "Chat generation timed out."})

    def test_provider_rate_limit_returns_503_and_retry_after(self):
        response, _, _ = self.request(
            generator=FakeGenerator([ProviderRateLimitError("17")])
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["retry-after"], "17")

    def test_malformed_json_triggers_one_repair(self):
        generator = FakeGenerator(["not json", valid_output(["S1"])])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(generator.calls[0]["repair"])
        self.assertTrue(generator.calls[1]["repair"])

    def test_token_exhaustion_receives_one_concise_retry_and_can_succeed(self):
        generator = FakeGenerator([
            ProviderCompletionExhaustedError("completion exhausted"),
            valid_output(["S1"]),
        ])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["grounded"])
        self.assertEqual(len(generator.calls), 2)
        self.assertFalse(generator.calls[0]["concise"])
        self.assertTrue(generator.calls[1]["concise"])
        self.assertFalse(generator.calls[1]["repair"])

    def test_token_exhaustion_retry_failure_safely_abstains(self):
        generator = FakeGenerator([
            ProviderCompletionExhaustedError("completion exhausted"),
            ProviderCompletionExhaustedError("completion exhausted"),
        ])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])
        self.assertEqual(len(generator.calls), 2)

    def test_completion_retry_and_semantic_repair_never_combine(self):
        generator = FakeGenerator([
            ProviderCompletionExhaustedError("completion exhausted"),
            "not json",
        ])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])
        self.assertEqual(len(generator.calls), 2)

    def test_unrelated_provider_bad_request_is_not_retried(self):
        generator = FakeGenerator([ProviderResponseError("ordinary bad request")])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(generator.calls), 1)

    def test_authentication_error_is_not_retried(self):
        generator = FakeGenerator([ProviderUnavailableError("authentication failed")])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(generator.calls), 1)

    def test_completion_token_setting_defaults_and_invalid_values_are_safe(self):
        with patch.dict("os.environ", {"GROQ_MAX_COMPLETION_TOKENS": "not-an-int"}, clear=True):
            self.assertEqual(get_generation_settings().max_completion_tokens, 2048)
        with patch.dict("os.environ", {"GROQ_MAX_COMPLETION_TOKENS": "99999"}, clear=True):
            self.assertEqual(get_generation_settings().max_completion_tokens, 2048)

    def test_successful_schema_repair_retry(self):
        generator = FakeGenerator([
            json.dumps({"answer": "Missing required fields"}),
            valid_output(["S2"]),
        ])
        response, _, _ = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["citations"][0]["citation_id"], "S2")

    def test_failed_repair_retry_returns_safe_abstention(self):
        generator = FakeGenerator(["bad", "still bad"])
        response, _, generator = self.request(generator=generator)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])
        self.assertEqual(len(generator.calls), 2)

    def test_blank_question_rejected(self):
        response, _, _ = self.request(payload={"question": "  \t "})
        self.assertEqual(response.status_code, 422)

    def test_oversized_question_rejected(self):
        response, _, _ = self.request(payload={"question": "x" * 1001})
        self.assertEqual(response.status_code, 422)

    def test_invalid_top_k_rejected(self):
        for value in (0, 9):
            with self.subTest(top_k=value):
                response, _, _ = self.request(
                    payload={"question": "Toy standard", "top_k": value}
                )
                self.assertEqual(response.status_code, 422)

    def test_unknown_request_field_rejected(self):
        response, _, _ = self.request(
            payload={"question": "Toy standard", "unknown": True}
        )
        self.assertEqual(response.status_code, 422)

    def test_health_unaffected_when_generator_unavailable(self):
        def unavailable():
            raise ProviderUnavailableError("missing")

        app = create_app(
            retriever_factory=FakeRetriever,
            generator_factory=unavailable,
        )
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["collection_count"], 917)

    def test_retrieve_unaffected_when_generator_unavailable(self):
        def unavailable():
            raise ProviderUnavailableError("missing")

        app = create_app(
            retriever_factory=FakeRetriever,
            generator_factory=unavailable,
        )
        with TestClient(app) as client:
            response = client.post("/api/retrieve", json={"question": "Toy standard"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result_count"], 5)

    def test_secret_never_appears_in_response_or_safe_log(self):
        secret = "provider-secret-fixture-never-log"
        generator = FakeGenerator([ProviderResponseError(secret)])
        with self.assertLogs("backend.main", level="ERROR") as captured:
            response, _, _ = self.request(generator=generator)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(secret, response.text)
        self.assertNotIn(secret, "\n".join(captured.output))

    def test_same_language_instruction_is_versioned(self):
        self.assertIn("same language as the user", SYSTEM_PROMPT)

    def test_exact_evidence_text_is_supplied_to_provider(self):
        response, _, generator = self.request()
        self.assertEqual(response.status_code, 200)
        supplied = generator.calls[0]["evidence"][0]["text"]
        self.assertEqual(supplied, "passage: Exact battery-operated toy evidence")

    def test_model_authored_page_metadata_is_rejected(self):
        invalid = json.dumps({
            "answer": "Invented citation metadata",
            "citations": [{
                "citation_id": "S1",
                "supporting_quote": EVIDENCE_QUOTES["S1"],
            }],
            "insufficient_evidence": False,
            "page_start": 999,
        })
        response, _, _ = self.request(generator=FakeGenerator([invalid, invalid]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["insufficient_evidence"])
        self.assertNotIn("999", response.text)

    def test_prompt_formats_trusted_ids_source_pages_and_exact_text(self):
        evidence = [{
            "citation_id": "S1",
            "source_filename": "source.pdf",
            "page_start": 4,
            "page_end": 4,
            "text": "passage: exact text",
        }]
        prompt = build_user_prompt("प्रश्न", evidence)
        self.assertIn("[S1]", prompt)
        self.assertIn("Source: source.pdf", prompt)
        self.assertIn("Pages: 4–4", prompt)
        self.assertIn("passage: exact text", prompt)
        self.assertNotIn("chunk", prompt.lower())

    def test_groq_generator_uses_supported_structured_output_without_tools(self):
        class FakeCompletions:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs
                message = SimpleNamespace(content=valid_output())
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        completions = FakeCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        settings = GenerationSettings(
            provider="groq",
            api_key="fixture-key",
            model="openai/gpt-oss-120b",
            timeout_seconds=30,
            max_completion_tokens=2048,
        )
        generator = GroqGenerator(settings, client=client)
        output = generator.generate("question", [{
            "citation_id": "S1",
            "source_filename": "source.pdf",
            "page_start": 1,
            "page_end": 1,
            "text": "passage: evidence",
        }])
        self.assertEqual(output, valid_output())
        self.assertEqual(completions.kwargs["temperature"], 0)
        self.assertEqual(completions.kwargs["max_completion_tokens"], 2048)
        self.assertEqual(completions.kwargs["reasoning_effort"], "low")
        self.assertFalse(completions.kwargs["include_reasoning"])
        self.assertNotIn("reasoning_format", completions.kwargs)
        self.assertEqual(completions.kwargs["tool_choice"], "none")
        self.assertEqual(
            completions.kwargs["response_format"]["type"],
            "json_schema",
        )
        self.assertNotIn("tools", completions.kwargs)
        self.assertNotIn("search_settings", completions.kwargs)

    def test_provider_schema_is_minimal_closed_and_all_properties_required(self):
        self.assert_closed_required_schema(GROQ_RESPONSE_SCHEMA)
        citation = GROQ_RESPONSE_SCHEMA["properties"]["citations"]["items"]
        self.assertEqual(citation["required"], ["citation_id", "supporting_quote"])
        forbidden = {
            "minLength", "maxLength", "pattern", "default", "title", "examples",
            "format", "$defs", "$ref", "anyOf", "oneOf",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & set(value))
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(GROQ_RESPONSE_SCHEMA)

    def test_bad_request_is_safely_classified_and_sanitized(self):
        from groq import BadRequestError

        secret = "fake_api_key_must_not_appear"
        prompt = "PRIVATE PROMPT MUST NOT APPEAR"
        passage = "PRIVATE PASSAGE MUST NOT APPEAR"
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(
            400,
            request=request,
            headers={"x-request-id": "req-test-123"},
            json={"error": {"type": "invalid_request_error", "code": "response_format"}},
        )
        error = BadRequestError(
            f"Bad schema; Authorization: Bearer {secret}; {prompt}; {passage}",
            response=response,
            body={"error": {"type": "invalid_request_error", "code": "response_format"}},
        )
        with self.assertLogs("backend.generation", level="WARNING") as captured:
            with self.assertRaises(ProviderResponseError):
                GroqGenerator._raise_safe_error(error)
        logs = "\n".join(captured.output)
        self.assertIn("exception_class=BadRequestError", logs)
        self.assertIn("status_code=400", logs)
        self.assertIn("error_code=response_format", logs)
        self.assertIn("request_id=req-test-123", logs)
        self.assertNotIn(secret, logs)
        self.assertNotIn(prompt, logs)
        self.assertNotIn(passage, logs)

    def test_failed_generation_content_is_never_logged(self):
        from groq import BadRequestError

        failed_generation = "PRIVATE FAILED GENERATION WITH RETRIEVED PASSAGE"
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(400, request=request)
        error = BadRequestError(
            f"json validation failed; failed_generation: {failed_generation}",
            response=response,
            body={"error": {"code": "json_validate_failed", "failed_generation": failed_generation}},
        )
        with self.assertLogs("backend.generation", level="WARNING") as captured:
            with self.assertRaises(ProviderResponseError):
                GroqGenerator._raise_safe_error(error)
        self.assertNotIn(failed_generation, "\n".join(captured.output))

    def test_rate_limit_is_safely_classified(self):
        from groq import RateLimitError

        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(429, request=request, headers={"Retry-After": "12"})
        error = RateLimitError("rate limited", response=response, body=None)
        with self.assertRaises(ProviderRateLimitError) as captured:
            GroqGenerator._raise_safe_error(error)
        self.assertEqual(captured.exception.retry_after, "12")

    def test_unexpected_provider_failure_returns_safe_500(self):
        secret = "unexpected-secret"
        response, _, _ = self.request(generator=FakeGenerator([RuntimeError(secret)]))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(secret, response.text)


if __name__ == "__main__":
    unittest.main()
