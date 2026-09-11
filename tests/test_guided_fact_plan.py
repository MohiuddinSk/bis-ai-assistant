"""Deterministic checks for backend-owned guided-answer fact plans."""

import unittest

from backend.chat_service import ChatService, EvidenceCompletenessError, FactPlan, TrustedFact
from backend.schemas import AnswerSection, ChatCitation


class GuidedFactPlanTests(unittest.TestCase):
    def setUp(self):
        self.citations = [ChatCitation(citation_id="S1", chunk_id="chunk-1", excerpt="IS 15644 is the primary standard for electric toys.")]
        self.plan = FactPlan("standards", (TrustedFact("F1", "IS 15644 is primary.", (), ("S1",)),))

    def test_sections_require_backend_selected_citations(self):
        section = AnswerSection(type="direct_answer", title="Direct answer", content="IS 15644 is primary.", citation_ids=["S1"])
        ChatService._validate_sections([section], self.plan, self.citations)

    def test_unknown_citation_is_rejected(self):
        section = AnswerSection(type="direct_answer", title="Direct answer", content="IS 15644 is primary.", citation_ids=["S99"])
        with self.assertRaises(EvidenceCompletenessError):
            ChatService._validate_sections([section], self.plan, self.citations)

    def test_unsupported_must_is_rejected(self):
        section = AnswerSection(type="important", title="Important condition", content="A user must do this.", citation_ids=["S1"])
        with self.assertRaises(EvidenceCompletenessError):
            ChatService._validate_sections([section], self.plan, self.citations)

    def test_plain_text_join_has_no_raw_extraction_artifacts(self):
        sections = [AnswerSection(type="direct_answer", title="Direct answer", content="IS 15644 is primary.", citation_ids=["S1"])]
        answer = ChatService._join_sections(sections)
        self.assertNotIn("Column", answer)
        self.assertNotIn("passage:", answer.lower())

    def test_flattened_sections_keep_word_boundaries_and_single_spaces(self):
        sections = [
            AnswerSection(type="direct_answer", title="Direct answer", content="Additional", citation_ids=["S1"]),
            AnswerSection(type="explanation", title="What this means", content=" requirements from the Development Commissioner apply.", citation_ids=["S1"]),
        ]
        answer = ChatService._join_sections(sections)
        self.assertIn("Additional requirements", answer)
        self.assertIn("Development Commissioner", answer)
        self.assertNotIn("additionalrequirements", answer.lower())
        self.assertNotIn("developmentcommissioner", answer.lower())
        self.assertNotIn("  ", answer)

    def test_section_citations_are_deduplicated_in_first_seen_order(self):
        section = AnswerSection(type="explanation", title="What this means", content="Trusted explanation.", citation_ids=["S2", "S1", "S1", "S2"])
        normalized = ChatService._deduplicate_section_citations([section])
        self.assertEqual(normalized[0].citation_ids, ["S2", "S1"])

    def test_flattening_skips_empty_content_includes_items_once_and_deduplicates_fragments(self):
        sections = [
            AnswerSection(type="direct_answer", title="Direct answer", content="  First sentence. ", citation_ids=["S1"]),
            AnswerSection(type="next_steps", title="What you should do", content="", items=[" Second sentence. ", "Second sentence."], citation_ids=["S1"]),
            AnswerSection(type="important", title="Important condition", content=None, items=["Third sentence."], citation_ids=["S1"]),
        ]
        self.assertEqual(ChatService._join_sections(sections), "First sentence. Second sentence. Third sentence.")

    def test_llm_guided_response_uses_the_same_finalized_sections(self):
        sections = [AnswerSection(type="direct_answer", title="Direct answer", content="Development Commissioner guidance.", citation_ids=["S1", "S1"])]
        response = ChatService._guided_response(
            sections=sections, grounded=True, insufficient_evidence=False, evidence_count=1,
            citations=self.citations, model="fake", generation_mode="llm", disclaimer="Verify.",
        )
        self.assertEqual(response.answer, ChatService._join_sections(response.answer_sections))
        self.assertEqual(response.answer_sections[0].citation_ids, ["S1"])
