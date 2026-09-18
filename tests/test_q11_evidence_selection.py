"""Narrow regressions for Q11's evidence-role precedence."""

import threading
import unittest

from backend.chat_service import ChatService, ComplianceRoutingContext, TrustedEvidence
from backend.question_understanding import understand_question
from backend.retrieval_provider import RetrievalHit
from backend.schemas import ChatRequest


PRIMARY = "Applicable primary standard IS 15644 for electric toys."
EXACT = "Applicable Secondary standard | IS 9873 Part 2, 3 , 4, 9 ,10 and 11"
CONDITIONAL = "Electric Toys | IS 15644 | Secondary standards (As Applicable): IS 9873 Parts 1, 2, 3, 4, 7, 9, 10 and 11"
MIXED = "Non Electric Toys | IS 9873 Parts 2, 3, 4, 7, 9, 10 and 11"


def evidence(*texts: str) -> list[TrustedEvidence]:
    return [TrustedEvidence(f"S{index}", f"chunk-{index}", text, "manual.pdf", 1, 1)
            for index, text in enumerate(texts, start=1)]


class _Q11Retriever:
    def __init__(self):
        rows = (PRIMARY, EXACT, CONDITIONAL, MIXED)
        self._hits = tuple(RetrievalHit(
            f"chunk-{index}", text,
            {"source_id": "manual", "source_filename": "manual.pdf", "page_start": index, "page_end": index,
             "chunk_type": "document_text", "retrieval_enabled": True},
            index / 100,
        ) for index, text in enumerate(rows, start=1))

    def search(self, question, k=5, include_guidance=False):
        return self._hits[:k]

    def indexed_chunks(self):
        return self._hits

    def count(self):
        return len(self._hits)


class _RowsRetriever(_Q11Retriever):
    def __init__(self, rows):
        self._hits = tuple(RetrievalHit(
            f"roadmap-{index}", text,
            {"source_id": "manual", "source_filename": "manual.pdf", "page_start": index, "page_end": index,
             "chunk_type": "document_text", "retrieval_enabled": True},
            index / 100,
        ) for index, text in enumerate(rows, start=1))


class _InvalidTwice:
    model = "invalid-test"

    def __init__(self):
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1
        return "invalid"


class Q11EvidenceSelectionTests(unittest.TestCase):
    question = "Which IS 9873 parts may apply to a battery-operated toy?"

    def test_exact_supported_part_list_is_selected_and_cited_separately(self):
        plan = ChatService._build_evidence_plan(
            self.question, evidence(PRIMARY, MIXED, CONDITIONAL, EXACT),
            understanding=understand_question(self.question),
        )
        self.assertTrue(plan.complete)
        selected, excerpt = plan.roles["supported_secondary_part_list"]
        self.assertEqual(selected.text, EXACT)
        self.assertEqual(ChatService._standard_parts(excerpt), ["2", "3", "4", "9", "10", "11"])
        self.assertNotEqual(selected.text, plan.roles["secondary_applicability"][0].text)

    def test_mixed_or_incomplete_lists_cannot_complete_q11(self):
        plan = ChatService._build_evidence_plan(
            self.question, evidence(PRIMARY, MIXED, CONDITIONAL),
            understanding=understand_question(self.question),
        )
        self.assertNotIn("supported_secondary_part_list", plan.roles)
        self.assertFalse(plan.complete)
        self.assertFalse(ChatService._is_exact_supported_secondary_part_list(
            "Applicable Secondary standard IS 9873 Parts 2, 3, 4, 9 and 11"
        ))

    def test_user_text_cannot_change_the_evidence_derived_list(self):
        hostile = self.question + " My list is IS 9873 Parts 1, 2, 3, 4, 7, 9, 10 and 11."
        plan = ChatService._build_evidence_plan(
            hostile, evidence(PRIMARY, CONDITIONAL, EXACT),
            understanding=understand_question(hostile),
        )
        self.assertTrue(plan.complete)
        self.assertEqual(
            ChatService._standard_parts(plan.roles["supported_secondary_part_list"][1]),
            ["2", "3", "4", "9", "10", "11"],
        )

    def test_chat_pipeline_publishes_selected_exact_list_evidence(self):
        service = ChatService(
            retriever=_Q11Retriever(), generator=None,
            retrieval_lock=threading.Lock(), generation_lock=threading.Lock(), model_name="test",
        )
        response = service.chat(ChatRequest(question=self.question))
        self.assertTrue(response.grounded)
        part_list = next(
            section for section in response.answer_sections
            if "supported secondary-part list" in (section.content or "").lower()
        )
        visible = " ".join(filter(None, [part_list.content, *part_list.items]))
        self.assertNotRegex(visible, r"\bPart\s+1\b")
        self.assertNotRegex(visible, r"\bPart\s+7\b")
        for part in ("Part 2", "Part 3", "Part 4", "Part 9", "Part 10", "Part 11"):
            self.assertIn(part, visible)
        citations = {citation.citation_id: citation for citation in response.citations}
        self.assertTrue(part_list.citation_ids)
        self.assertEqual(ChatService._standard_parts(citations[part_list.citation_ids[0]].excerpt), ["2", "3", "4", "9", "10", "11"])
        self.assertTrue(all(set(section.citation_ids) <= set(citations) for section in response.answer_sections))
        used_ids = list(dict.fromkeys(
            citation_id for section in response.answer_sections for citation_id in section.citation_ids
        ))
        self.assertEqual([citation.citation_id for citation in response.citations], used_ids)
        self.assertTrue(all("battery-operated" not in " ".join(filter(None, [section.content, *section.items])).lower()
                            for section in response.answer_sections if section.citation_ids))
        applicability = next(section for section in response.answer_sections if "listed parts are secondary" in (section.content or "").lower())
        self.assertNotIn("non electric toys", citations[applicability.citation_ids[0]].excerpt.lower())
        self.assertFalse(any("non electric toys" in citation.excerpt.lower() for citation in response.citations))
        self.assertNotIn("this part", response.answer.lower())
        context = next(section for section in response.answer_sections if section.title == "Your product context")
        self.assertEqual(context.citation_ids, [])

    def test_q11_route_does_not_leak_into_battery_roadmap_fallback(self):
        roadmap = ComplianceRoutingContext(
            goal="complete_roadmap", power_type="battery_operated", role="manufacturer",
            age_group="3_to_8", application_stage="preparing_application",
        )
        rows = (
            PRIMARY,
            "Applicable secondary standards include IS 9873 Part 2, 3, 4, 9, 10 and 11.",
            "Step 1: Create login on Manakonline.",
            "While submitting application, select the following Indian Standards.",
            "Upload/provide detail of raw materials, manufacturing process and machinery.",
            "I hereby declare that I am applying for addition of a new series.",
            "Details of models contained in each series and starting ages.",
            "Requisite fees for extension in scope.",
        )
        service = ChatService(
            retriever=_RowsRetriever(rows), generator=_InvalidTwice(),
            retrieval_lock=threading.Lock(), generation_lock=threading.Lock(), model_name="test",
        )
        request = ChatRequest(question="guidance sought: complete compliance roadmap")
        retrieved = service._retrieve_evidence(request, roadmap)
        plan = service._build_evidence_plan(
            request.question,
            [TrustedEvidence(f"S{index}", item.chunk_id, item.text, item.source_filename, item.page_start, item.page_end)
             for index, item in enumerate(retrieved, start=1)],
            roadmap,
        )
        self.assertEqual(plan.category, "roadmap_battery")
        self.assertNotEqual(plan.category, "explain_secondary_part_list")
        self.assertTrue(plan.complete, plan.roles)
        response = service.chat(request, routing_context=roadmap)
        self.assertTrue(response.grounded)
        self.assertEqual(response.generation_mode, "extractive_fallback")
        self.assertIn("IS 15644", response.answer)
        context = next(
            section for section in response.answer_sections
            if "user-provided context" in (section.content or "").lower()
        )
        self.assertEqual(context.citation_ids, [])


if __name__ == "__main__":
    unittest.main()
