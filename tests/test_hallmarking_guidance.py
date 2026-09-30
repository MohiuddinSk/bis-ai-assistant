"""Hallmarking source and shared-chat regression checks."""

from contextlib import nullcontext
import json
from pathlib import Path
import unittest

from backend.chat_service import ChatService
from backend.documents import SourceDocumentRegistry
from backend.hallmarking_guidance import is_hallmarking_question, load_candidate, retrieve_hallmarking
from backend.schemas import ChatRequest


ROOT = Path(__file__).resolve().parents[1]


class NoToyRetriever:
    def search(self, question, k=5, include_guidance=False):
        raise AssertionError("Hallmarking must not retrieve toy Chroma results")


def ask(question: str, audience: str = "consumer", language: str = "en"):
    service = ChatService(
        retriever=NoToyRetriever(), generator=None, retrieval_lock=nullcontext(),
        generation_lock=nullcontext(), model_name="disabled",
    )
    return service.chat(ChatRequest(question=question, audience=audience, response_language=language))


class HallmarkingGuidanceTests(unittest.TestCase):
    def test_candidate_is_separate_and_retains_verified_provenance(self):
        path = ROOT / "data/processed/hallmarking_candidate_v1/evidence.json"
        package = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "hallmarking_candidate_v1")
        self.assertEqual(len(load_candidate()), package["record_count"])
        self.assertGreaterEqual(package["record_count"], 8)
        for record in load_candidate():
            self.assertTrue(record["source_url"].startswith("https://www.bis.gov.in/"))
            self.assertTrue(record["source_sha256"])
            self.assertTrue(record["section_heading"])
            self.assertTrue(record["retrieved_at"])
            if record["source_type"] == "html":
                self.assertIsNone(record.get("page"))
                self.assertIsNone(record.get("source_filename"))

    def test_consumer_and_jeweller_question_families_use_relevant_sources(self):
        buying = ask("What should I check before buying hallmarked gold jewellery?")
        self.assertTrue(buying.grounded)
        self.assertEqual(buying.response_kind, "grounded_guidance")
        self.assertTrue(all(c.source_url and "bis.gov.in" in c.source_url for c in buying.citations))
        self.assertTrue(any("General" in (c.source_title or "") for c in buying.citations))
        self.assertNotIn("toy", buying.answer.lower())

        huid = ask("What is HUID, and how can I verify it?")
        self.assertTrue(huid.grounded)
        self.assertIn("BIS Care", huid.answer)
        self.assertEqual(huid.official_next_step_url, "https://www.bis.gov.in/bis-apps/?lang=en")
        self.assertTrue(any(c.source_section and "HUID" in c.source_section for c in huid.citations))

        jeweller = ask("How can a jeweller get started with BIS hallmarking?", "manufacturer")
        self.assertTrue(jeweller.grounded)
        self.assertIn("NSWS", jeweller.answer)
        pdf = next(c for c in jeweller.citations if c.source_type == "pdf")
        self.assertEqual((pdf.source_filename, pdf.page_start), ("Guidelines-for-Jewellers.pdf", 4))
        self.assertEqual(SourceDocumentRegistry().resolve(pdf.source_filename).name, pdf.source_filename)

    def test_different_phrasings_and_official_service_topics(self):
        self.assertTrue(ask("Where may a consumer have hallmarked jewellery assayed?").grounded)
        fineness = ask("What does 22K916 mean on my gold jewellery?")
        self.assertTrue(fineness.grounded)
        self.assertIn("916 parts per thousand", fineness.answer)
        self.assertTrue(any(c.source_section and "grades permitted" in c.source_section for c in fineness.citations))
        complaint = ask("How do I make a complaint about hallmarked jewellery?")
        self.assertTrue(complaint.grounded)
        self.assertIn("complaint", complaint.answer.lower())
        self.assertTrue(any(c.source_section and "complaint" in c.source_section.lower() for c in complaint.citations))
        self.assertEqual(complaint.official_next_step_url, "https://www.bis.gov.in/consumer-overview/online-complaint-registration/?lang=en")
        purity_complaint = ask("How can I complain about the purity of hallmarked jewellery?")
        self.assertEqual([c.source_section for c in purity_complaint.citations], ["3. What is the process of complaint registration in BIS?"])
        self.assertTrue(retrieve_hallmarking("How can I locate an Assaying and Hallmarking Centre?"))

    def test_ambiguous_and_unsupported_claims_fail_closed(self):
        clarification = ask("Is hallmarking mandatory?")
        self.assertTrue(clarification.needs_clarification)
        self.assertFalse(clarification.citations)
        unsupported = ask("What is the current hallmarking fee in my district?")
        self.assertTrue(unsupported.insufficient_evidence)
        self.assertFalse(unsupported.citations)
        unrelated = ask("How do I repair a gold jewellery clasp?")
        self.assertTrue(unrelated.insufficient_evidence)
        self.assertFalse(unrelated.citations)
        applicability = ask("Which Indian Standard applies to my gold jewellery?")
        self.assertTrue(applicability.insufficient_evidence)
        self.assertFalse(applicability.citations)
        authenticity = ask("Is my HUID ABC123 valid?")
        self.assertTrue(authenticity.insufficient_evidence)
        self.assertIn("BIS Care", authenticity.answer)
        self.assertEqual(authenticity.official_next_step_url, "https://www.bis.gov.in/bis-apps/?lang=en")
        self.assertFalse(authenticity.citations)
        self.assertFalse(is_hallmarking_question("Which standard applies to a battery-operated toy?"))

    def test_language_selection_keeps_citations_and_localizes_limitations(self):
        for language in ("en", "hi", "mr", "ta", "bn"):
            response = ask("What is HUID, and how can I verify it?", language=language)
            self.assertTrue(response.grounded)
            self.assertTrue(response.citations)
            self.assertIn("BIS Care", response.answer)
            if language != "en":
                self.assertNotIn("unique six-character", response.answer)
            limitation = ask("Is my HUID ABC123 valid?", language=language)
            self.assertTrue(limitation.insufficient_evidence)
            self.assertIn("BIS Care", limitation.answer)


if __name__ == "__main__":
    unittest.main()
