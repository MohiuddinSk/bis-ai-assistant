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

    def test_grounded_sections_use_plain_language_order_without_changing_citations(self):
        sections = [
            AnswerSection(type="direct_answer", title="Direct answer", content="IS 15644 is the primary standard.", citation_ids=["S1"]),
            AnswerSection(type="explanation", title="What this means", content="IS 9873 may apply where applicable.", citation_ids=["S1"]),
            AnswerSection(type="next_steps", title="What you should do", items=["Review the cited standard first."], citation_ids=["S1"]),
            AnswerSection(type="important", title="Important condition", content="The indexed documents do not establish a fee.", citation_ids=["S1"]),
        ]
        response = ChatService._guided_response(
            sections=sections, grounded=True, insufficient_evidence=False, evidence_count=1,
            citations=self.citations, model="fake", generation_mode="extractive_fallback", disclaimer="Verify.",
        )
        self.assertEqual(
            [section.title for section in response.answer_sections],
            ["In simple terms", "What this means for you", "What to do next", "Important to know"],
        )
        self.assertEqual([section.citation_ids for section in response.answer_sections], [["S1"]] * 4)
        self.assertIn("may apply where applicable", response.answer)

    def test_plain_language_deduplication_removes_only_exact_visible_repetition(self):
        sections = [
            AnswerSection(type="direct_answer", title="Direct answer", content="One supported fact.", citation_ids=["S1"]),
            AnswerSection(type="direct_answer", title="Different direct answer", content="A distinct supported fact.", citation_ids=["S1"]),
            AnswerSection(type="next_steps", title="What you should do", items=["First action.", "First action.", "Second action."], citation_ids=["S1"]),
            AnswerSection(type="next_steps", title="Another action list", items=["Second action.", "A separate action."], citation_ids=["S1"]),
        ]
        normalized = ChatService._plain_language_sections(sections)
        self.assertEqual(len([section for section in normalized if section.type == "direct_answer"]), 1)
        self.assertEqual(normalized[1].items, ["First action.", "Second action."])
        self.assertEqual(normalized[2].items, ["A separate action."])
        self.assertEqual(normalized[1].citation_ids, ["S1"])

    def test_clarification_is_not_relabelled_or_given_citations(self):
        section = AnswerSection(type="clarification", title="Need more details", content="Which power type applies?", citation_ids=[])
        response = ChatService._guided_response(
            sections=[section], grounded=False, insufficient_evidence=False, evidence_count=0,
            citations=[], model="fake", generation_mode="clarification", disclaimer="Verify.", needs_clarification=True,
        )
        self.assertEqual(response.answer_sections, [section])
        self.assertEqual(response.citations, [])
