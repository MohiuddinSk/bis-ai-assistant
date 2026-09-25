"""Phase 3A: reviewed Hindi/Marathi deterministic routing and presentation."""

import unittest
import re
import threading

from backend.chat_service import ChatService, TrustedEvidence
from backend.question_understanding import understand_question
from backend.response_localization import localized_english_fallback_notice, localize_reviewed_sections
from backend.retrieval_provider import LocalChromaRetriever
from backend.schemas import AnswerSection, ChatRequest, ComplianceProfile


PRIMARY = "For electric toys, the applicable primary standard is IS 15644:2006 electric toys."
SECONDARY = "Applicable secondary standards include IS 9873 Part 2, 3, 4, 9, 10 and 11 where applicable."
EXACT_Q11 = "Applicable Secondary standard | IS 9873 Part 2, 3, 4, 9, 10 and 11"
Q11_CONDITION = "Electric Toys | IS 15644 | Secondary standards (As Applicable): IS 9873 Parts 1, 2, 3, 4, 7, 9, 10 and 11"
CERTIFICATION = (
    "Step 1: Create login on Manakonline. While submitting application select following Indian Standards. "
    "Upload/provide detail of raw materials. Step 4: Provide details of test facilities."
)


def evidence():
    rows = (PRIMARY, SECONDARY, EXACT_Q11, Q11_CONDITION, CERTIFICATION)
    return [TrustedEvidence(f"S{index}", f"chunk-{index}", text, "manual.pdf", index, index)
            for index, text in enumerate(rows, start=1)]


class MultilingualPhase3ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retriever = LocalChromaRetriever()
        cls.service = ChatService(
            retriever=retriever, generator=None,
            retrieval_lock=threading.Lock(), generation_lock=threading.Lock(), model_name="test",
        )
    def test_response_language_contract_is_closed_and_defaults_to_english(self):
        self.assertEqual(ChatRequest(question="toy standards").response_language, "en")
        self.assertEqual(ComplianceProfile(
            role="manufacturer", product_description="Toy car", power_type="battery_operated",
            intended_age_group="3_to_8", goal="identify_standards", application_stage="researching",
        ).response_language, "en")
        for language in ("en", "hi", "mr"):
            self.assertEqual(ChatRequest(question="toy standards", response_language=language).response_language, language)
        with self.assertRaises(Exception):
            ChatRequest(question="toy standards", response_language="fr")

    def test_reviewed_hindi_and_marathi_questions_resolve_to_english_categories_and_roles(self):
        cases = (
            ("Which standard applies to a battery-operated toy?", "बैटरी से चलने वाले खिलौने पर कौन-सा मानक लागू होता है?", "बॅटरीवर चालणाऱ्या खेळण्याला कोणते मानक लागू होते?"),
            ("Explain IS 15644 in simple words.", "IS 15644 आसान भाषा में समझाइए।", "IS 15644 सोप्या भाषेत समजावून सांगा."),
            ("When does IS 15644 apply?", "IS 15644 कब लागू होता है?", "IS 15644 कधी लागू होते?"),
            ("Explain IS 9873 Part 2 in simple words.", "IS 9873 भाग 2 आसान भाषा में समझाइए।", "IS 9873 भाग 2 सोप्या भाषेत समजावून सांगा."),
            ("What are the steps to obtain BIS certification for a toy?", "खिलौने के लिए BIS प्रमाणन प्राप्त करने के चरण क्या हैं?", "खेळण्यासाठी BIS प्रमाणन मिळवण्याच्या पायऱ्या कोणत्या आहेत?"),
            ("Which IS 9873 parts may apply to a battery-operated toy?", "बैटरी से चलने वाले खिलौने पर IS 9873 के कौन-से भाग लागू हो सकते हैं?", "बॅटरीवर चालणाऱ्या खेळण्याला IS 9873 चे कोणते भाग लागू होऊ शकतात?"),
        )
        localized_answers: dict[str, str] = {}
        for english, hindi, marathi in cases:
            with self.subTest(english=english):
                english_plan = ChatService._build_evidence_plan(english, evidence(), understanding=understand_question(english))
                for localized in (hindi, marathi):
                    plan = ChatService._build_evidence_plan(localized, evidence(), understanding=understand_question(localized))
                    self.assertEqual(plan.category, english_plan.category)
                    self.assertEqual(set(plan.roles), set(english_plan.roles))
                    self.assertEqual(
                        {role: item.chunk_id for role, (item, _excerpt) in plan.roles.items()},
                        {role: item.chunk_id for role, (item, _excerpt) in english_plan.roles.items()},
                    )
                english_response = self.service.chat(ChatRequest(question=english))
                hindi_response = self.service.chat(ChatRequest(question=hindi, response_language="hi"))
                marathi_response = self.service.chat(ChatRequest(question=marathi, response_language="mr"))
                localized_answers[english] = hindi_response.answer
                for language, response in (("hi", hindi_response), ("mr", marathi_response)):
                    self.assertNotIn(localized_english_fallback_notice(language), response.answer)
                    self.assertEqual(
                        [citation.model_dump() for citation in response.citations],
                        [citation.model_dump() for citation in english_response.citations],
                    )
                if english.startswith("Which standard applies"):
                    self.assertIn("प्राथमिक मानक" if hindi_response.answer else "", hindi_response.answer)
                    self.assertIn("where applicable", english_response.answer.lower())
                if english.startswith("Explain IS 15644"):
                    self.assertEqual(hindi_response.answer.count("IS 15644"), 1)
                if english.startswith("When does IS 15644"):
                    self.assertIn("कम से कम एक कार्य बिजली पर निर्भर", hindi_response.answer)
                    self.assertIn("किमान एक कार्य विजेवर अवलंबून", marathi_response.answer)
        self.assertNotEqual(
            localized_answers["Explain IS 15644 in simple words."],
            localized_answers["When does IS 15644 apply?"],
        )

    def test_reviewed_copy_preserves_citations_metadata_and_q11_identifiers(self):
        english = [
            AnswerSection(type="direct_answer", title="Direct answer", content="English one", citation_ids=["S1"]),
            AnswerSection(type="explanation", title="Supported IS 9873 parts", content="English two", citation_ids=["S2"]),
            AnswerSection(type="explanation", title="Where applicable", content="English three", citation_ids=["S3"]),
            AnswerSection(type="explanation", title="Your product context", content="English four", citation_ids=[]),
            AnswerSection(type="important", title="What the indexed documents do not establish", content="English five", citation_ids=[]),
        ]
        for language in ("hi", "mr"):
            localized = localize_reviewed_sections(language, "explain_secondary_part_list", english, "battery_q11_parts")
            self.assertIsNotNone(localized)
            self.assertEqual([section.citation_ids for section in localized], [section.citation_ids for section in english])
            visible = " ".join((section.content or "") for section in localized)
            for part in ("Part 2", "Part 3", "Part 4", "Part 9", "Part 10", "Part 11"):
                self.assertIn(part, visible)
            self.assertIsNone(re.search(r"\bPart\s+1(?!\d)", visible))
            self.assertNotIn("Part 7", visible)
            self.assertIn("स्थापित नहीं" if language == "hi" else "स्थापित करत नाहीत", visible)

    def test_unreviewed_deterministic_category_has_no_translation_template(self):
        section = AnswerSection(type="important", title="Important condition", content="English evidence-bound answer")
        self.assertIsNone(localize_reviewed_sections("hi", "exemption", [section], None))
        self.assertIsNone(localize_reviewed_sections("mr", "transition", [section], None))


if __name__ == "__main__":
    unittest.main()
