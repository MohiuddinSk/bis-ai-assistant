"""Fact-constrained synthesis tests. No provider key, corpus write, or live call."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.chat_service import ChatService, EvidenceCompletenessError, TrustedEvidence
from backend.generation import GROQ_RESPONSE_SCHEMA, SYNTHESIS_RESPONSE_SCHEMA, GroqGenerator
from backend.prompts import SYNTHESIS_SYSTEM_PROMPT, build_synthesis_user_prompt
from backend.generation import ProviderRateLimitError, ProviderTimeoutError, ProviderUnavailableError
from backend.main import create_app
from backend.openai_compatible_generator import OpenAICompatibleGenerator
from backend.schemas import SynthesisOutput
from backend.settings import GenerationSettings
from tests.test_chat_api import FakeRetriever, valid_output
from tests.test_provider_disabled_api import CompletePlanRetriever


BATTERY_QUESTION = "Which standard applies to a battery-operated toy?"
PROFILE = {
    "role": "manufacturer",
    "product_description": "Battery toy car",
    "power_type": "battery_operated",
    "intended_age_group": "3_to_8",
    "goal": "identify_standards",
    "application_stage": "researching",
    "additional_context": None,
}


def valid_from_packet(packet):
    facts = packet["facts"]
    first, rest = facts[0], facts[1:]
    sections = [{
        "type": "direct_answer",
        "content": first["statement"],
        "items": [],
        "citation_ids": list(first["citation_ids"]),
        "source_fact_ids": [first["fact_id"]],
    }]
    sections.append({
        "type": "explanation",
        "content": "Review the cited material against the product’s actual features before relying on the guidance.",
        "items": [],
        "citation_ids": list(first["citation_ids"]),
        "source_fact_ids": [first["fact_id"]],
    })
    if packet["next_steps"]:
        sections.append({
            "type": "next_steps",
            "content": "",
            "items": list(packet["next_steps"]),
            "citation_ids": list(dict.fromkeys(citation_id for fact in facts for citation_id in fact["citation_ids"])),
            "source_fact_ids": [fact["fact_id"] for fact in facts],
        })
    important = [str(item) for item in packet["limitations"]]
    qualifiers = " ".join(qualifier for fact in facts for qualifier in fact["qualifiers"])
    if "where applicable" in qualifiers.lower() and "where applicable" not in " ".join(important).lower():
        important.append("The approved requirements apply where applicable.")
    if not important:
        important.append("The indexed evidence does not establish a numeric fee, form, laboratory, or timeline.")
    sections.append({
        "type": "important",
        "content": " ".join(important),
        "items": [],
        "citation_ids": list(dict.fromkeys(citation_id for fact in facts for citation_id in fact["citation_ids"])),
        "source_fact_ids": [fact["fact_id"] for fact in facts],
    })
    return json.dumps({"sections": sections})


def strict_valid_from_packet(packet):
    """A complete legacy-schema packet for testing its structural validator.

    Runtime publication deliberately accepts only the provider explanation; this
    fixture remains complete so the legacy closed-schema validator is still
    tested for every approved fact and qualifier rather than being bypassed.
    """
    payload = json.loads(valid_from_packet(packet))
    explanation = next(section for section in payload["sections"] if section["type"] == "explanation")
    explanation["content"] = " ".join(str(fact["statement"]) for fact in packet["facts"])
    explanation["citation_ids"] = list(dict.fromkeys(
        citation_id for fact in packet["facts"] for citation_id in fact["citation_ids"]
    ))
    explanation["source_fact_ids"] = [fact["fact_id"] for fact in packet["facts"]]
    return json.dumps(payload)


class RecordingGenerator:
    model = "synthesis-test-model"

    def __init__(self, mode="valid", error=None):
        self.mode = mode
        self.error = error
        self.calls = []

    def generate(self, question, evidence, **kwargs):
        self.calls.append({"question": question, "evidence": evidence, **kwargs})
        if self.error is not None:
            raise self.error
        packet = kwargs["synthesis_packet"]
        if self.mode == "valid":
            return valid_from_packet(packet)
        if self.mode == "repair":
            if not kwargs.get("repair"):
                payload = json.loads(valid_from_packet(packet))
                next(section for section in payload["sections"] if section["type"] == "explanation")["content"] = packet["facts"][0]["statement"]
                return json.dumps(payload)
            return valid_from_packet(packet)
        if self.mode == "always-invalid":
            payload = json.loads(valid_from_packet(packet))
            next(section for section in payload["sections"] if section["type"] == "explanation")["content"] = packet["facts"][0]["statement"]
            return json.dumps(payload)
        payload = json.loads(valid_from_packet(packet))
        explanation = next(section for section in payload["sections"] if section["type"] == "explanation")
        if self.mode == "invented":
            explanation["content"] += " IS 99999 was approved in 1999. The fee is Rs 500. Use Form No. 12 within 7 days."
        elif self.mode == "unknown-fact":
            explanation["source_fact_ids"].append("F99")
        elif self.mode == "unknown-citation":
            explanation["citation_ids"].append("S99")
        elif self.mode == "duplicate":
            if not kwargs.get("repair"):
                explanation["items"] = [explanation["content"]]
            else:
                return valid_from_packet(packet)
        elif self.mode == "mains":
            explanation["content"] += " It also covers a mains-powered toy."
        return json.dumps(payload)


class ExplodingGenerator:
    model = "unused"

    def __init__(self):
        self.calls = []

    def generate(self, *args, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("provider must not be called")


class SynthesisApiTests(unittest.TestCase):
    def post(self, *, enabled, generator, payload=None, retriever=CompletePlanRetriever, path="/api/chat"):
        app = create_app(retriever_factory=retriever, generator_factory=lambda: generator)
        body = payload or {"question": BATTERY_QUESTION}
        with patch.dict("os.environ", {"LLM_SYNTHESIS_ENABLED": "true" if enabled else "false"}):
            with TestClient(app) as client:
                return client.post(path, json=body)

    def test_flag_off_preserves_deterministic_output_without_provider_calls(self):
        generator = ExplodingGenerator()
        disabled = self.post(enabled=False, generator=generator)
        enabled_key_only = self.post(enabled=False, generator=generator)
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["generation_mode"], "extractive_fallback")
        self.assertEqual(disabled.json()["model"], "extractive-evidence-fallback")
        self.assertEqual(disabled.json(), enabled_key_only.json())
        self.assertEqual(generator.calls, [])

    def test_missing_provider_with_flag_on_returns_deterministic_fallback(self):
        def unavailable():
            raise ProviderUnavailableError("secret provider body")

        app = create_app(retriever_factory=CompletePlanRetriever, generator_factory=unavailable)
        with patch.dict("os.environ", {"LLM_SYNTHESIS_ENABLED": "true"}):
            with TestClient(app) as client:
                response = client.post("/api/chat", json={"question": BATTERY_QUESTION})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["generation_mode"], "extractive_fallback")
        self.assertEqual(body["model"], "extractive-evidence-fallback")
        self.assertTrue(body["grounded"])
        self.assertNotIn("secret", response.text)

    def test_valid_synthesis_publishes_llm_sections_and_backend_citations(self):
        baseline = self.post(enabled=False, generator=ExplodingGenerator()).json()
        generator = RecordingGenerator()
        response = self.post(enabled=True, generator=generator)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["generation_mode"], "llm")
        self.assertEqual(body["model"], "synthesis-test-model")
        self.assertTrue(body["grounded"])
        self.assertFalse(body["insufficient_evidence"])
        self.assertGreaterEqual(len(generator.calls), 1)
        self.assertIn("synthesis_packet", generator.calls[0])
        for section in body["answer_sections"]:
            if section["type"] in {"direct_answer", "explanation", "next_steps"}:
                self.assertTrue(section["citation_ids"])
        for citation in body["citations"]:
            match = next(item for item in baseline["citations"] if item["citation_id"] == citation["citation_id"])
            self.assertEqual(citation["excerpt"], match["excerpt"])
            self.assertEqual(citation["source_filename"], match["source_filename"])
            self.assertEqual(citation["page_start"], match["page_start"])
            self.assertEqual(citation["page_end"], match["page_end"])
            self.assertEqual(citation["chunk_id"], match["chunk_id"])
        self.assertIn("where applicable", body["answer"].lower())
        self.assertIn("IS 15644", body["answer"])
        self.assertIn("primary", body["answer"].lower())

    def test_invented_standard_date_fee_form_and_timeline_fall_back(self):
        baseline = self.post(enabled=False, generator=ExplodingGenerator()).json()
        response = self.post(enabled=True, generator=RecordingGenerator("invented"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), baseline)
        for marker in ("99999", "1999", "Rs 500", "Form No. 12", "within 7 days"):
            self.assertNotIn(marker, response.text)

    def test_unknown_fact_and_citation_ids_fall_back(self):
        baseline = self.post(enabled=False, generator=ExplodingGenerator()).json()
        for mode in ("unknown-fact", "unknown-citation"):
            with self.subTest(mode=mode):
                response = self.post(enabled=True, generator=RecordingGenerator(mode))
                self.assertEqual(response.json(), baseline)
                self.assertNotIn("F99", response.text)
                self.assertNotIn("S99", response.text)

    def test_dropped_where_applicable_falls_back_to_exact_deterministic_answer(self):
        baseline = self.post(enabled=False, generator=ExplodingGenerator()).json()
        response = self.post(enabled=True, generator=RecordingGenerator("always-invalid"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), baseline)

    def test_failed_repair_returns_exact_deterministic_fallback(self):
        baseline = self.post(enabled=False, generator=ExplodingGenerator()).json()
        generator = RecordingGenerator("always-invalid")
        response = self.post(enabled=True, generator=generator)
        self.assertEqual(response.json(), baseline)
        self.assertEqual(len(generator.calls), 2)
        self.assertTrue(generator.calls[1]["repair"])
        self.assertIn("SEMANTIC_REPETITION", generator.calls[1]["repair_feedback"])
        self.assertNotIn("when relevant", generator.calls[1]["repair_feedback"])
        self.assertNotIn("excerpt", generator.calls[1]["repair_feedback"].lower())

    def test_repair_succeeds_only_when_repaired_output_validates(self):
        generator = RecordingGenerator("repair")
        response = self.post(enabled=True, generator=generator)
        body = response.json()
        self.assertEqual(body["generation_mode"], "llm")
        self.assertIn("where applicable", body["answer"].lower())
        self.assertNotIn("when relevant", body["answer"].lower())
        self.assertEqual(len(generator.calls), 2)
        self.assertFalse(generator.calls[0]["repair"])
        self.assertTrue(generator.calls[1]["repair"])
        self.assertNotIn("when relevant", generator.calls[1]["repair_feedback"])

    def test_duplicate_items_are_rejected_until_repair_validates(self):
        generator = RecordingGenerator("duplicate")
        response = self.post(enabled=True, generator=generator)
        self.assertEqual(response.json()["generation_mode"], "llm")
        self.assertIn("DUPLICATE_CONTENT", generator.calls[1]["repair_feedback"])
        self.assertEqual(len(generator.calls), 2)

    def test_synthesis_logs_keep_only_fixed_diagnostic_fields(self):
        class NamedGroqGenerator(RecordingGenerator):
            model = "openai/gpt-oss-120b"

        NamedGroqGenerator.__name__ = "GroqGenerator"
        generator = NamedGroqGenerator()
        with self.assertLogs("backend.chat_service", level="WARNING") as captured:
            response = self.post(enabled=True, generator=generator)
        self.assertEqual(response.json()["generation_mode"], "llm")
        text = "\n".join(captured.output)
        self.assertIn("event=synthesis_attempt", text)
        self.assertIn("provider=groq", text)
        self.assertIn("model=openai/gpt-oss-120b", text)
        self.assertRegex(text, r"plan_category=[a-z0-9_]+")
        self.assertIn("attempt=1", text)
        self.assertIn("outcome=success", text)
        self.assertIn("code=OK", text)
        self.assertRegex(text, r"elapsed_ms=\d+")
        for secret in (
            BATTERY_QUESTION,
            "Approved fact packet",
            "For electric toys, the primary standard is IS 15644:2006.",
            "manual.pdf",
            "gsk_test_key",
            "Authorization",
            "raw response",
        ):
            self.assertNotIn(secret, text)

        failed = RecordingGenerator("always-invalid")
        with self.assertLogs("backend.chat_service", level="WARNING") as failed_logs:
            fallback = self.post(enabled=True, generator=failed)
        self.assertEqual(fallback.json()["generation_mode"], "extractive_fallback")
        failed_text = "\n".join(failed_logs.output)
        self.assertIn("attempt=1", failed_text)
        self.assertIn("outcome=validation_error", failed_text)
        self.assertIn("attempt=2", failed_text)
        self.assertIn("outcome=fallback", failed_text)
        self.assertIn("SEMANTIC_REPETITION", failed_text)
        self.assertNotIn("when relevant", failed_text)
        self.assertNotIn(BATTERY_QUESTION, failed_text)
        self.assertNotIn("manual.pdf", failed_text)

        secret_error = RecordingGenerator(error=ProviderUnavailableError("gsk_test_key Authorization manual.pdf"))
        with self.assertLogs("backend.chat_service", level="WARNING") as error_logs:
            errored = self.post(enabled=True, generator=secret_error)
        self.assertEqual(errored.json()["generation_mode"], "extractive_fallback")
        error_text = "\n".join(error_logs.output)
        self.assertIn("outcome=provider_error", error_text)
        self.assertIn("code=UNAVAILABLE", error_text)
        self.assertNotIn("gsk_test_key", error_text)
        self.assertNotIn("Authorization", error_text)
        self.assertNotIn("manual.pdf", error_text)

    def test_provider_failures_on_complete_plan_fall_back_without_5xx(self):
        baseline = self.post(enabled=False, generator=ExplodingGenerator()).json()
        failures = (
            ProviderTimeoutError("timeout secret"),
            ProviderUnavailableError("secret auth body"),
            ProviderRateLimitError("9"),
        )
        for error in failures:
            with self.subTest(error=type(error).__name__):
                generator = RecordingGenerator(error=error)
                response = self.post(enabled=True, generator=generator)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), baseline)
                self.assertEqual(len(generator.calls), 1)
                self.assertNotIn("secret", response.text)
                self.assertNotIn("retry-after", response.headers)

    def test_incomplete_plan_preserves_legacy_generation_when_synthesis_is_enabled(self):
        class IncompleteGenerator(RecordingGenerator):
            def generate(self, question, evidence, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("synthesis_packet") is not None:
                    raise AssertionError("synthesis packet sent for an incomplete plan")
                if isinstance(self.error, Exception):
                    raise self.error
                return valid_output()

        success = IncompleteGenerator()
        response = self.post(enabled=True, generator=success, retriever=FakeRetriever)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generation_mode"], "llm")
        self.assertNotIn("synthesis_packet", success.calls[0])
        timed_out = IncompleteGenerator(error=ProviderTimeoutError("timeout"))
        failure = self.post(enabled=True, generator=timed_out, retriever=FakeRetriever)
        self.assertEqual(failure.status_code, 504)
        self.assertEqual(failure.json(), {"detail": "Chat generation timed out."})

    def test_reviewed_languages_do_not_call_the_provider(self):
        generator = ExplodingGenerator()
        for language in ("hi", "mr", "ta", "bn"):
            with self.subTest(language=language):
                response = self.post(
                    enabled=True,
                    generator=generator,
                    payload={"question": BATTERY_QUESTION, "response_language": language},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["generation_mode"], "extractive_fallback")
        self.assertEqual(generator.calls, [])

    def test_compliance_route_rejects_contradictory_synthesis(self):
        valid = self.post(enabled=True, generator=RecordingGenerator(), payload=PROFILE, path="/api/compliance/guide")
        guidance = valid.json()["guidance"]
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(guidance["generation_mode"], "llm")
        self.assertTrue(guidance["grounded"])
        self.assertNotIn("mains-powered", guidance["answer"].lower())
        rejected = self.post(enabled=True, generator=RecordingGenerator("mains"), payload=PROFILE, path="/api/compliance/guide")
        fallback = rejected.json()["guidance"]
        self.assertEqual(fallback["generation_mode"], "extractive_fallback")
        self.assertNotIn("mains-powered", fallback["answer"].lower())
        self.assertTrue(fallback["grounded"])


class SynthesisValidationTests(unittest.TestCase):
    def battery_inputs(self):
        evidence = [
            TrustedEvidence("S1", "chunk-1", "For electric toys, the primary standard is IS 15644:2006.", "manual.pdf", 1, 1),
            TrustedEvidence("S2", "chunk-2", "Applicable secondary standards include IS 9873 Parts 2 and 3.", "manual.pdf", 2, 2),
        ]
        packet = {
            "facts": [
                {"fact_id": "F1", "statement": "IS 15644 is the primary standard for electric toys.", "qualifiers": [], "citation_ids": ["S1"]},
                {"fact_id": "F2", "statement": "IS 9873 Parts are secondary or additional requirements where applicable.", "qualifiers": ["where applicable"], "citation_ids": ["S2"]},
            ],
            "next_steps": [],
            "limitations": [],
            "evidence": [
                {"citation_id": item.citation_id, "excerpt": item.text, "source_filename": item.source_filename, "page_start": item.page_start, "page_end": item.page_end, "chunk_id": item.chunk_id}
                for item in evidence
            ],
        }
        return evidence, packet

    def validate(self, payload, packet=None, evidence=None, question=BATTERY_QUESTION):
        if evidence is None or packet is None:
            evidence, packet = self.battery_inputs()
        ChatService._validate_synthesis(
            SynthesisOutput.model_validate(payload), packet, evidence, question, None, None,
        )

    def test_duplicate_complete_package_and_modal_claims_are_rejected(self):
        evidence, packet = self.battery_inputs()
        duplicate = json.loads(valid_from_packet(packet))
        duplicate["sections"][1]["items"] = [duplicate["sections"][1]["content"]]
        with self.assertRaises(EvidenceCompletenessError) as duplicate_error:
            self.validate(duplicate, packet, evidence)
        self.assertIn("DUPLICATE_CONTENT", duplicate_error.exception.code)

        packet["facts"][1]["qualifiers"] = ["where applicable", "partial checklist"]
        packet["limitations"] = ["This is not presented as the complete application package."]
        invented = json.loads(valid_from_packet(packet))
        invented["sections"][-1]["content"] += " This is the complete application package."
        with self.assertRaises(EvidenceCompletenessError) as complete_error:
            self.validate(invented, packet, evidence, "What documents are required for a new toy series?")
        self.assertIn("UNSUPPORTED_COMPLETENESS", complete_error.exception.code)

        modal = json.loads(valid_from_packet(self.battery_inputs()[1]))
        modal["sections"][0]["content"] += " You must comply."
        with self.assertRaises(EvidenceCompletenessError) as modal_error:
            self.validate(modal)
        self.assertIn("UNSUPPORTED_MODAL", modal_error.exception.code)

    def test_closed_object_and_internal_qualifier_tags_validate(self):
        evidence, packet = self.battery_inputs()
        array_payload = json.loads(strict_valid_from_packet(packet))
        by_type = {section["type"]: section for section in array_payload["sections"]}
        by_type["next_steps"] = {"content": "", "items": [], "citation_ids": [], "source_fact_ids": []}
        raw = json.dumps({
            key: {field: value for field, value in by_type[key].items() if field != "type"}
            for key in ("direct_answer", "explanation", "next_steps", "important")
        })
        self.validate(ChatService._parse_synthesis_output(raw).model_dump(), packet, evidence)

        packet["facts"][0]["qualifiers"] = ["partial checklist"]
        packet["limitations"] = ["The cited material is partial."]
        faithful = json.loads(strict_valid_from_packet(packet))
        self.validate(faithful, packet, evidence)

        evidence, packet = self.battery_inputs()
        packet["facts"][1]["qualifiers"] = ["where applicable", "may", "subject to conditions"]
        packet["facts"][1]["statement"] = "IS 9873 Parts are secondary or additional requirements where applicable, and a manufacturer may use them only subject to the stated conditions."
        packet["limitations"] = ["The cited material does not establish a calendar date."]
        faithful = json.loads(strict_valid_from_packet(packet))
        self.validate(faithful, packet, evidence)

    def test_synthesis_prompt_requests_a_specific_bounded_answer(self):
        prompt = SYNTHESIS_SYSTEM_PROMPT + build_synthesis_user_prompt(
            {"facts": []}, repair=True, repair_feedback="MISSING_LIMITATION",
        )
        for phrase in (
            "plain language",
            "backend",
            "Only explanation",
            "filler",
            "repeated",
            "MISSING_LIMITATION",
        ):
            self.assertIn(phrase, prompt)

    def test_synthesis_schema_is_separate_and_closed(self):
        self.assertEqual(
            set(GROQ_RESPONSE_SCHEMA["properties"]),
            {"answer", "insufficient_evidence", "citations"},
        )
        self.assertEqual(
            set(SYNTHESIS_RESPONSE_SCHEMA["properties"]),
            {"direct_answer", "explanation", "next_steps", "important"},
        )
        self.assertEqual(
            SYNTHESIS_RESPONSE_SCHEMA["required"],
            ["direct_answer", "explanation", "next_steps", "important"],
        )
        grounded = SYNTHESIS_RESPONSE_SCHEMA["properties"]["direct_answer"]
        self.assertEqual(grounded["properties"]["citation_ids"]["minItems"], 1)
        self.assertEqual(grounded["properties"]["source_fact_ids"]["minItems"], 1)
        self.assertNotIn("minItems", SYNTHESIS_RESPONSE_SCHEMA["properties"]["next_steps"]["properties"]["citation_ids"])
        self.assertNotIn("minItems", SYNTHESIS_RESPONSE_SCHEMA["properties"]["important"]["properties"]["citation_ids"])
        forbidden = {"minLength", "maxLength", "pattern", "default", "title", "examples", "format", "$defs", "$ref", "anyOf", "oneOf"}

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & set(value))
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(SYNTHESIS_RESPONSE_SCHEMA)

    def test_groq_sdk_sends_the_synthesis_schema_only_for_a_packet(self):
        class Completions:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

        completions = Completions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        generator = GroqGenerator(GenerationSettings("groq", "fixture-key", "openai/gpt-oss-120b", 30, 2048), client=client)
        packet = {"facts": []}
        generator.generate("question", [], synthesis_packet=packet)
        self.assertEqual(completions.kwargs["response_format"]["json_schema"]["name"], "grounded_fact_synthesis")
        self.assertEqual(completions.kwargs["response_format"]["json_schema"]["schema"], SYNTHESIS_RESPONSE_SCHEMA)
        self.assertNotIn("tools", completions.kwargs)
        generator.generate("question", [], synthesis_packet=packet, repair=True, repair_feedback="MISSING_SECTION")
        self.assertEqual(completions.kwargs["response_format"]["json_schema"]["name"], "grounded_fact_synthesis")
        self.assertEqual(completions.kwargs["response_format"]["json_schema"]["schema"], SYNTHESIS_RESPONSE_SCHEMA)
        self.assertIn("MISSING_SECTION", completions.kwargs["messages"][1]["content"])
        generator.generate("question", [{"citation_id": "S1", "text": "evidence"}])
        self.assertEqual(completions.kwargs["response_format"]["json_schema"]["name"], "grounded_bis_answer")
        self.assertEqual(completions.kwargs["response_format"]["json_schema"]["schema"], GROQ_RESPONSE_SCHEMA)

    def test_openai_compatible_synthesis_uses_the_separate_schema(self):
        seen = {}

        def handler(request):
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        settings = GenerationSettings(
            "openai_compatible", "test-key", "test-model", 30, 2048,
            "https://example.test/v1", ("example.test",),
        )
        generator = OpenAICompatibleGenerator(settings, httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))
        generator.generate("question", [], synthesis_packet={"facts": [{"fact_id": "F1"}]}, repair=True, repair_feedback="DROPPED_QUALIFIER")
        schema = seen["payload"]["response_format"]["json_schema"]
        self.assertEqual(schema["name"], "grounded_fact_synthesis")
        self.assertEqual(schema["schema"], SYNTHESIS_RESPONSE_SCHEMA)
        self.assertIn("F1", seen["payload"]["messages"][1]["content"])
        self.assertIn("DROPPED_QUALIFIER", seen["payload"]["messages"][1]["content"])
        self.assertNotIn("Retrieved evidence", seen["payload"]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
