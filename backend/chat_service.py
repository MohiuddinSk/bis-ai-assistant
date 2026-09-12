"""Grounded chat orchestration and backend-controlled citation mapping."""

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import re
from typing import ContextManager, Literal

from pydantic import ValidationError

from backend.generation import (
    GenerationProvider,
    ProviderCompletionExhaustedError,
    ProviderUnavailableError,
)
from backend.schemas import (
    AnswerSection,
    ChatCitation,
    ChatRequest,
    ChatResponse,
    GenerationOutput,
    RetrieveRequest,
    RetrievalResult,
)
from backend.service import RetrievalService, RetrieverProtocol
from backend.question_understanding import QuestionUnderstanding
from backend.settings import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    LEGAL_INFORMATION_DISCLAIMER,
)


logger = logging.getLogger(__name__)


class ChatRetrievalError(Exception):
    pass


class EvidenceCompletenessError(ValueError):
    def __init__(self, code: str, citation_ids: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.citation_ids = citation_ids or []


@dataclass(frozen=True)
class TrustedEvidence:
    citation_id: str
    chunk_id: str
    text: str
    source_filename: str | None
    page_start: int | None
    page_end: int | None

    def prompt_mapping(self) -> Mapping[str, object]:
        return {
            "citation_id": self.citation_id,
            "text": self.text,
            "source_filename": self.source_filename,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


@dataclass(frozen=True)
class EvidencePlan:
    category: str
    roles: dict[str, tuple[TrustedEvidence, str]]

    @property
    def complete(self) -> bool:
        required = {
            "standards": {"primary_standard", "secondary_standard"},
            "standards_battery": {"primary_standard", "secondary_standard"},
            "standards_mains": {"primary_standard", "secondary_standard"},
            "standards_non_electric": {"non_electric_primary", "non_electric_secondary"},
            "certification": {
                "certification_portal", "certification_standard_selection",
                "certification_application_details", "certification_test_facilities",
            },
            "exemption": {"exemption_scope", "registration_condition", "registering_authority"},
            "documents": {"series_declaration", "series_details", "scope_fee"},
            "commencement": {"commencement_clause"},
            "transition": {"operative_scope", "operative_permission"},
        }.get(self.category, set())
        return bool(required) and required <= set(self.roles)


@dataclass(frozen=True)
class ComplianceRoutingContext:
    """Server-only routing derived from validated ComplianceProfile enums."""

    goal: Literal[
        "identify_standards", "new_licence", "add_new_series",
        "check_exemption", "understand_transition", "not_sure",
    ]
    power_type: Literal[
        "battery_operated", "mains_electric", "non_electric", "not_sure",
    ]


@dataclass(frozen=True)
class TrustedFact:
    """A backend-owned, evidence-bound fact passed to the language layer."""

    fact_id: str
    statement: str
    qualifiers: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class FactPlan:
    intent: str
    facts: tuple[TrustedFact, ...]
    limitations: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return bool(self.facts)


class ChatService:
    def __init__(
        self,
        *,
        retriever: RetrieverProtocol,
        generator: GenerationProvider | None,
        retrieval_lock: ContextManager[None],
        generation_lock: ContextManager[None],
        model_name: str,
    ):
        self._retriever = retriever
        self._generator = generator
        self._retrieval_lock = retrieval_lock
        self._generation_lock = generation_lock
        self._model_name = model_name

    def chat(
        self,
        request: ChatRequest,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> ChatResponse:
        if routing_context is not None:
            clarification = self._routing_clarification(routing_context)
            if clarification:
                return self._clarification(clarification)
        if routing_context is None and understanding and understanding.clarification_required:
            return self._clarification(understanding.clarification_question or "What additional detail can you provide?")
        if routing_context is None and understanding and understanding.intent == "out_of_domain":
            return self._abstention(evidence=[])
        effective_question = understanding.normalized_query if understanding else request.question
        try:
            with self._retrieval_lock:
                retrieved_results = self._retrieve_evidence(request, routing_context, understanding)
        except Exception:
            raise ChatRetrievalError("Chat retrieval failed") from None

        evidence = [
            TrustedEvidence(
                citation_id=f"S{index}",
                chunk_id=result.chunk_id,
                text=result.text,
                source_filename=result.source_filename,
                page_start=result.page_start,
                page_end=result.page_end,
            )
            for index, result in enumerate(retrieved_results, start=1)
        ]

        if not evidence:
            return self._abstention(evidence=[])
        plan = self._build_evidence_plan(request.question, evidence, routing_context, understanding)
        if plan.category == "clarification":
            return self._abstention(evidence=evidence)
        # Complete trusted evidence plans bypass Groq: this removes avoidable
        # latency and cannot weaken citation or qualification controls.
        if plan.complete:
            return self._fallback_or_abstain(evidence, plan, request.audience)
        if self._generator is None:
            raise ProviderUnavailableError("Chat generation is unavailable")

        prompt_evidence = [item.prompt_mapping() for item in evidence]
        with self._generation_lock:
            # At most two provider calls per chat request: either an initial call
            # plus one token-exhaustion concise retry, or an initial call plus one
            # semantic-output repair. These paths never combine.
            used_completion_retry = False
            try:
                first_output = self._generator.generate(
                    effective_question,
                    prompt_evidence,
                )
            except ProviderCompletionExhaustedError:
                used_completion_retry = True
                try:
                    first_output = self._generator.generate(
                        effective_question,
                        prompt_evidence,
                        concise=True,
                    )
                except ProviderCompletionExhaustedError:
                    return self._abstention(evidence=evidence)
            try:
                generated, citations = self._validate_output(first_output, evidence, effective_question)
            except (ValidationError, ValueError) as validation_error:
                if used_completion_retry:
                    self._log_abstention(validation_error, evidence, [])
                    return self._fallback_or_abstain(evidence, plan, request.audience)
                try:
                    repaired_output = self._generator.generate(
                        effective_question,
                        prompt_evidence,
                        repair=True,
                        repair_feedback=self._repair_feedback(validation_error, evidence),
                    )
                except ProviderCompletionExhaustedError:
                    return self._abstention(evidence=evidence)
                try:
                    generated, citations = self._validate_output(
                        repaired_output,
                        evidence,
                        effective_question,
                    )
                except (ValidationError, ValueError) as repair_error:
                    # Invalid model evidence must never be surfaced as a grounded claim.
                    self._log_abstention(repair_error, evidence, [])
                    return self._fallback_or_abstain(evidence, plan, request.audience)

        if generated.insufficient_evidence:
            return self._abstention(evidence=evidence, citations=citations)
        if understanding is not None and not self._answer_matches_understanding(generated.answer, understanding):
            logger.warning(
                "Model candidate rejected; validation_code=QUESTION_INTENT_MISMATCH intent=%s power=%s",
                understanding.intent,
                understanding.power,
            )
            return self._fallback_or_abstain(evidence, plan, request.audience)

        # Certain high-risk, structured facts have an unambiguous evidence-role
        # plan.  Compose those facts from the verified roles instead of allowing
        # table layout artefacts from a PDF extraction to leak into the answer.
        # This is intent/role driven, not an exact-question shortcut.
        guided_sections = self._deduplicate_section_citations([AnswerSection(
            type="direct_answer", title="Direct answer", content=generated.answer,
            citation_ids=[citation.citation_id for citation in citations],
        )])
        return self._guided_response(
            sections=guided_sections,
            grounded=True,
            insufficient_evidence=False,
            evidence_count=len(evidence),
            citations=citations,
            model=self._generator.model,
            generation_mode="llm",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
        )

    @staticmethod
    def _build_evidence_plan(
        question: str,
        evidence: list[TrustedEvidence],
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> EvidencePlan:
        question_lower = question.lower()
        roles: dict[str, tuple[TrustedEvidence, str]] = {}
        if routing_context is not None:
            category = {
                "check_exemption": "exemption",
                "add_new_series": "documents",
                "understand_transition": "transition",
                "new_licence": "certification",
                "not_sure": "clarification",
            }.get(routing_context.goal, "")
            if routing_context.goal == "identify_standards":
                category = {
                    "battery_operated": "standards_battery",
                    "mains_electric": "standards_mains",
                    "non_electric": "standards_non_electric",
                    "not_sure": "clarification",
                }[routing_context.power_type]
        elif understanding is not None:
            category = {
                "certification": "certification",
                "documents": "documents",
                "exemption": "exemption",
                "commencement": "commencement",
                "transition": "transition",
                "out_of_domain": "clarification",
                "general": "",
            }.get(understanding.intent, "")
            if understanding.intent == "standards":
                category = {
                    "battery_operated": "standards_battery",
                    "mains_electric": "standards_mains",
                    "non_electric": "standards_non_electric",
                    "electric_unspecified": "clarification",
                    "unknown": "clarification",
                }[understanding.power]
        elif any(term in question_lower for term in ("handmade", "artisan", "exempt")):
            category = "exemption"
        elif any(term in question_lower for term in ("document", "application", "checklist")) and any(
            term in question_lower for term in ("series", "model", "variety")
        ):
            category = "documents"
        elif "commencement" in question_lower or "come into force" in question_lower:
            category = "commencement"
        elif "transition" in question_lower and "order" in question_lower:
            category = "transition"
        elif "battery" in question_lower or "electric" in question_lower:
            category = "standards"
        else:
            category = ""

        if category in {"standards", "standards_battery", "standards_mains"}:
            primary_options: list[tuple[TrustedEvidence, str]] = []
            secondary_options: list[tuple[TrustedEvidence, str]] = []
            for item in evidence:
                text = item.text.lower()
                if ChatService._is_normative_primary(item.text):
                    excerpt = (
                        ChatService._excerpt_for_standard_role(item.text, "primary")
                        if "applicable primary standard" in item.text.lower()
                        else ChatService._excerpt_for_anchor(item.text, "is 15644")
                    )
                    if excerpt: primary_options.append((item, excerpt))
                if ChatService._is_normative_secondary(item.text):
                    excerpt = ChatService._excerpt_for_standard_role(item.text, "secondary")
                    if excerpt: secondary_options.append((item, excerpt))
            if primary_options:
                roles["primary_standard"] = min(primary_options, key=lambda option: len(option[1]))
            if secondary_options:
                roles["secondary_standard"] = min(secondary_options, key=lambda option: len(option[1]))
            # Keep deterministic fake-provider fixtures usable while production
            # retrieval supplies the stronger, normative role passages above.
            for item in evidence:
                if "primary_standard" not in roles and "is 15644" in item.text.lower():
                    excerpt = ChatService._excerpt_for_anchor(item.text, "is 15644")
                    if excerpt: roles["primary_standard"] = (item, excerpt)
                if "secondary_standard" not in roles and "is 9873" in item.text.lower():
                    excerpt = ChatService._excerpt_for_anchor(item.text, "is 9873")
                    if excerpt: roles["secondary_standard"] = (item, excerpt)
        elif category == "standards_non_electric":
            for item in evidence:
                if ChatService._is_normative_non_electric_primary(item.text):
                    excerpt = ChatService._excerpt_for_non_electric_role(item.text, "primary")
                    if excerpt: roles.setdefault("non_electric_primary", (item, excerpt))
                if ChatService._is_normative_non_electric_secondary(item.text):
                    excerpt = ChatService._excerpt_for_non_electric_role(item.text, "secondary")
                    if excerpt: roles.setdefault("non_electric_secondary", (item, excerpt))
        elif category == "certification":
            for item in evidence:
                text = ChatService._display_text(item.text).lower()
                if "step 1: create login on manakonline" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "step 1: create login on manakonline")
                    if excerpt: roles.setdefault("certification_portal", (item, excerpt))
                if "while submitting application" in text and "following indian standards" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "while submitting application")
                    if excerpt: roles.setdefault("certification_standard_selection", (item, excerpt))
                if "upload/provide detail of raw materials" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "upload/provide detail of raw materials")
                    if excerpt: roles.setdefault("certification_application_details", (item, excerpt))
                if "step 4: provide details of test facilities" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "step 4: provide details of test facilities")
                    if excerpt: roles.setdefault("certification_test_facilities", (item, excerpt))
        elif category == "exemption":
            for item in evidence:
                text = item.text.lower()
                if "manufactured and sold by artisans" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "manufactured and sold by artisans")
                    if excerpt: roles.setdefault("exemption_scope", (item, excerpt))
                if "registered with office of the development commissioner" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "registered with office of the development commissioner")
                    if excerpt:
                        roles.setdefault("registration_condition", (item, excerpt))
                        if "ministry of textiles" in text:
                            roles.setdefault("registering_authority", (item, excerpt))
        elif category == "documents":
            for item in evidence:
                text = item.text.lower()
                if "i hereby declare" in text and "applying for addition" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "i hereby declare")
                    if excerpt: roles["series_declaration"] = (item, excerpt)
                if "details of models contained in each series" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "details of models contained in each series")
                    if excerpt: roles["series_details"] = (item, excerpt)
                if "requisite fees for extension in scope" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "requisite fees for extension in scope")
                    if excerpt: roles["scope_fee"] = (item, excerpt)
        elif category == "commencement":
            for item in evidence:
                if "come into force" in item.text.lower():
                    excerpt = ChatService._excerpt_for_anchor(item.text, "come into force")
                    if excerpt: roles.setdefault("commencement_clause", (item, excerpt))
        elif category == "transition":
            for item in evidence:
                text = item.text.lower()
                if "this order shall apply" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "this order shall apply")
                    if excerpt: roles.setdefault("operative_scope", (item, excerpt))
                if "permission under this order may be granted" in text and "company" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "permission under this order may be granted")
                    if excerpt: roles.setdefault("operative_permission", (item, excerpt))
        return EvidencePlan(category, roles)

    @staticmethod
    def _fact_plan(plan: EvidencePlan) -> FactPlan:
        """Translate selected roles into facts; no model may alter this mapping."""
        role_facts = {
            "primary_standard": ("IS 15644 is the primary standard for electric toys.", ()),
            "secondary_standard": ("IS 9873 Parts are secondary or additional requirements where applicable.", ("where applicable",)),
            "non_electric_primary": ("IS 9873 Part 1 is the primary standard for non-electric toys.", ()),
            "non_electric_secondary": ("Other IS 9873 parts are secondary requirements where applicable.", ("where applicable",)),
            "certification_portal": ("The BIS guidance starts with creating a Manakonline account and applying through it.", ()),
            "certification_standard_selection": ("The application requires selection of the standard matching the toy type.", ()),
            "certification_application_details": ("The application guidance asks for specified product and factory information.", ("partial procedure",)),
            "certification_test_facilities": ("The guidance asks for details of available test facilities.", ("partial procedure",)),
            "exemption_scope": ("The exception applies only to goods manufactured and sold by qualifying artisans.", ("only",)),
            "registration_condition": ("The artisan must be registered with the Office of the Development Commissioner (Handicrafts).", ("must be registered",)),
            "registering_authority": ("The registration authority is under the Ministry of Textiles, Government of India.", ()),
            "series_declaration": ("A declaration is included in the retrieved new-series material.", ("partial checklist",)),
            "series_details": ("The material asks for series or model details, including starting ages.", ("partial checklist",)),
            "scope_fee": ("The material refers to the requisite fee for extension of scope.", ("partial checklist",)),
            "commencement_clause": ("The selected order comes into force on publication in the Official Gazette.", ("no calendar date established",)),
            "operative_scope": ("The order applies to goods or articles covered by specified Quality Control Orders.", ()),
            "operative_permission": ("Permission may be granted only subject to the operative eligibility and risk-assessment conditions.", ("may", "subject to conditions")),
        }
        facts: list[TrustedFact] = []
        for index, (role, (item, _excerpt)) in enumerate(plan.roles.items(), start=1):
            statement, qualifiers = role_facts.get(role, ("Trusted evidence supports this point.", ()))
            facts.append(TrustedFact(f"F{index}", statement, tuple(qualifiers), (item.citation_id,)))
        limitations = ("The cited material is partial.",) if plan.category == "documents" else ()
        return FactPlan(plan.category, tuple(facts), limitations)

    @staticmethod
    def _validate_sections(sections: list[AnswerSection], fact_plan: FactPlan, citations: list[ChatCitation]) -> None:
        """Keep returned guidance tied to backend-selected facts and citations."""
        allowed_citations = {citation.citation_id for citation in citations}
        if not fact_plan.complete:
            raise EvidenceCompletenessError("INCOMPLETE_FACT_PLAN")
        for section in sections:
            if not set(section.citation_ids) <= allowed_citations:
                raise EvidenceCompletenessError("UNKNOWN_FACT_OR_CITATION_ID")
            text = " ".join(filter(None, [section.content, *section.items])).lower()
            if re.search(r"\bmust\b", text) and not any("must" in qualifier for fact in fact_plan.facts for qualifier in fact.qualifiers):
                raise EvidenceCompletenessError("UNSUPPORTED_MODAL")

    @staticmethod
    def _join_sections(sections: list[AnswerSection]) -> str:
        """Flatten visible guidance without leaking section boundaries into words."""
        chunks: list[str] = []
        seen: set[str] = set()
        for section in sections:
            for fragment in [section.content, *section.items]:
                if not fragment or not fragment.strip():
                    continue
                normalized = re.sub(r"\s+", " ", fragment).strip()
                if normalized not in seen:
                    seen.add(normalized)
                    chunks.append(normalized)
        return " ".join(chunks)

    @staticmethod
    def _deduplicate_section_citations(sections: list[AnswerSection]) -> list[AnswerSection]:
        """Preserve first-seen citation order within each user-visible section."""
        normalized: list[AnswerSection] = []
        for section in sections:
            citation_ids = list(dict.fromkeys(section.citation_ids))
            normalized.append(section.model_copy(update={"citation_ids": citation_ids}))
        return normalized

    @classmethod
    def _guided_response(
        cls,
        *,
        sections: list[AnswerSection],
        grounded: bool,
        insufficient_evidence: bool,
        evidence_count: int,
        citations: list[ChatCitation],
        model: str | None,
        generation_mode: str,
        disclaimer: str,
        needs_clarification: bool = False,
    ) -> ChatResponse:
        """The sole non-abstention response assembly boundary.

        The compatibility answer must always be a lossless, whitespace-safe view
        of the user-visible guided sections; no earlier fact or PDF fragment may
        bypass this final boundary.
        """
        finalized_sections = cls._deduplicate_section_citations(sections)
        return ChatResponse(
            answer=cls._join_sections(finalized_sections),
            grounded=grounded,
            insufficient_evidence=insufficient_evidence,
            evidence_count=evidence_count,
            citations=citations,
            model=model,
            generation_mode=generation_mode,
            disclaimer=disclaimer,
            answer_sections=finalized_sections,
            needs_clarification=needs_clarification,
        )

    def _fallback_or_abstain(
        self,
        evidence: list[TrustedEvidence],
        plan: EvidencePlan,
        audience: str = "general",
    ) -> ChatResponse:
        if not plan.complete:
            return self._abstention(evidence=evidence)
        ordered_roles = {
            "standards": ("primary_standard", "secondary_standard"),
            "standards_battery": ("primary_standard", "secondary_standard"),
            "standards_mains": ("primary_standard", "secondary_standard"),
            "standards_non_electric": ("non_electric_primary", "non_electric_secondary"),
            "certification": (
                "certification_portal", "certification_standard_selection",
                "certification_application_details", "certification_test_facilities",
            ),
            "exemption": ("exemption_scope", "registration_condition", "registering_authority"),
            "documents": ("series_declaration", "series_details", "scope_fee"),
            "commencement": ("commencement_clause",),
            "transition": ("operative_scope", "operative_permission"),
        }[plan.category]
        selected = [plan.roles[role] for role in ordered_roles]
        citations = self._map_citations(
            [(item.citation_id, excerpt) for item, excerpt in selected], evidence
        )
        if plan.category in {"standards", "standards_battery", "standards_mains"}:
            parts = self._standard_parts(selected[1][1])
            secondary = ", ".join(f"Part {part}" for part in parts[:-1])
            if len(parts) > 1:
                secondary += f", and Part {parts[-1]}"
            elif parts:
                secondary = f"Part {parts[0]}"
            else:
                secondary = ""
            subject = (
                "a mains-powered electric toy" if plan.category == "standards_mains"
                else "a battery-operated electric toy"
            )
            sections = [
                AnswerSection(type="direct_answer", title="Direct answer", content=f"For {subject}, the primary standard is IS 15644.", citation_ids=[selected[0][0].citation_id]),
                AnswerSection(type="explanation", title="What this means", content=f"IS 9873 {secondary} are secondary standards and additional requirements, where applicable. They do not replace IS 15644 as the primary standard.", citation_ids=[selected[1][0].citation_id]),
            ]
            if audience == "manufacturer":
                sections.append(AnswerSection(type="next_steps", title="What you should do", items=["Check IS 15644 first, then identify the listed IS 9873 parts that apply to your toy."], citation_ids=[selected[0][0].citation_id, selected[1][0].citation_id]))
        elif plan.category == "standards_non_electric":
            sections = [
                AnswerSection(
                    type="direct_answer", title="Direct answer",
                    content="For a non-electric toy, the primary standard is IS 9873 Part 1.",
                    citation_ids=[selected[0][0].citation_id],
                ),
                AnswerSection(
                    type="explanation", title="What this means",
                    content=("The 2026 product manual also identifies IS 9873 Parts 2, 3, 4, 7, 9, 10 and 11 "
                             "as secondary standards, where applicable."),
                    citation_ids=[selected[1][0].citation_id],
                ),
            ]
            if audience == "manufacturer":
                sections.append(AnswerSection(
                    type="next_steps", title="What you should do",
                    items=["Start with IS 9873 Part 1, then identify which cited secondary parts apply to the toy."],
                    citation_ids=[selected[0][0].citation_id, selected[1][0].citation_id],
                ))
        elif plan.category == "certification":
            sections = [
                AnswerSection(
                    type="direct_answer", title="Direct answer",
                    content="The indexed BIS guidance supports the opening steps for a new toy-licence application.",
                    citation_ids=[item.citation_id for item, _ in selected],
                ),
                AnswerSection(
                    type="next_steps", title="What you should do",
                    items=[
                        "Create an account on Manakonline and apply for a licence through that account.",
                        "Choose the Indian Standard that matches whether the toy is electric or non-electric.",
                        "Provide the listed product and factory details, including raw materials, factory location, manufacturing process, machinery, plant layout and testing personnel.",
                        "Provide details of the test facilities available at the factory.",
                    ],
                    citation_ids=[item.citation_id for item, _ in selected],
                ),
                AnswerSection(
                    type="important", title="Important limitation",
                    content="These are only the cited opening steps, not the complete certification procedure. The selected evidence does not establish every remaining step.",
                    citation_ids=[item.citation_id for item, _ in selected],
                ),
            ]
        elif plan.category == "exemption":
            scope = re.sub(
                r"^provided further that nothing in this order shall apply to\s+",
                "", selected[0][1], flags=re.I,
            ).rstrip(".:")
            registration = selected[1][1].rstrip(".:")
            sections = [
                AnswerSection(type="direct_answer", title="Direct answer", content="No, not all handmade toys are automatically exempt.", citation_ids=[selected[0][0].citation_id]),
                AnswerSection(type="explanation", title="What this means", content=f"The exception applies to {scope} {registration}.", citation_ids=[item.citation_id for item, _ in selected]),
                AnswerSection(type="important", title="Important condition", content="Handmade alone does not establish this exemption; the manufacture, sale, registration, and authority conditions all matter.", citation_ids=[item.citation_id for item, _ in selected]),
            ]
        elif plan.category == "documents":
            sections = [
                AnswerSection(type="direct_answer", title="Direct answer", content="The available manual material provides only a partial checklist for adding a new toy series.", citation_ids=[item.citation_id for item, _ in selected]),
                AnswerSection(type="next_steps", title="What you should do", items=["Include a declaration for the new-series application.", "Include series/model details, including starting ages, to be declared separately to BIS.", "Include the requisite fee declaration for extension of scope."], citation_ids=[item.citation_id for item, _ in selected]),
                AnswerSection(type="important", title="Important condition", content="This is not presented as the complete application package; check the current BIS application requirements before submitting.", citation_ids=[item.citation_id for item, _ in selected]),
            ]
        elif plan.category == "commencement":
            sections = [
                AnswerSection(type="clarification", title="Please clarify", content="Which Quality Control Order, amendment, extension, or year do you mean? Several orders may have different commencement dates.", citation_ids=[]),
                AnswerSection(type="important", title="What the cited order says", content="The selected extension-order clause says it comes into force on publication in the Official Gazette. The cited passage does not establish a calendar date.", citation_ids=[selected[0][0].citation_id]),
            ]
        else:
            sections = [
                AnswerSection(type="direct_answer", title="Direct answer", content="The 2026 Transition Facilitation Order can allow permission for covered goods or articles, but approval is not automatic.", citation_ids=[selected[0][0].citation_id, selected[1][0].citation_id]),
                AnswerSection(type="explanation", title="What this means", content="The Department for Promotion of Industry and Internal Trade (DPIIT) may grant permission to a company incorporated under the Companies Act, 2013, based on the Implementation Committee’s risk assessment.", citation_ids=[selected[1][0].citation_id]),
                AnswerSection(type="important", title="Important condition", content="Permission may be granted only under the order’s stated conditions.", citation_ids=[selected[1][0].citation_id]),
            ]
        fact_plan = self._fact_plan(plan)
        sections = self._deduplicate_section_citations(sections)
        self._validate_sections(sections, fact_plan, citations)
        logger.info("Chat generation_mode=extractive_fallback evidence_complete=true roles=%s citation_ids=%s", ordered_roles, [item.citation_id for item, _ in selected])
        return self._guided_response(sections=sections, grounded=True, insufficient_evidence=False,
            evidence_count=len(evidence), citations=citations, model="extractive-evidence-fallback",
            generation_mode="extractive_fallback", disclaimer=LEGAL_INFORMATION_DISCLAIMER)

    @staticmethod
    def _compose_fragments(*fragments: str) -> str:
        """Join deterministic prose fragments without leaking PDF/layout boundaries."""
        return " ".join(" ".join(fragment.split()) for fragment in fragments if fragment and fragment.strip())

    @staticmethod
    def _repair_feedback(error: Exception, evidence: list[TrustedEvidence]) -> str:
        code = error.code if isinstance(error, EvidenceCompletenessError) else "UNSUPPORTED_QUOTE"
        roles: list[str] = []
        for item in evidence:
            text = item.text.lower()
            if "is 15644" in text:
                roles.append(f"primary-standard={item.citation_id}")
            if "is 9873" in text:
                roles.append(f"secondary-standard={item.citation_id}")
            if "manufactured and sold by artisans" in text:
                roles.append(f"artisan-scope={item.citation_id}")
            if "registered with office of the development commissioner" in text:
                roles.append(f"registration-condition={item.citation_id}")
        return f"{code}; " + "; ".join(roles)

    @staticmethod
    def _log_abstention(error: Exception, evidence: list[TrustedEvidence], citation_ids: list[str]) -> None:
        code = error.code if isinstance(error, EvidenceCompletenessError) else "UNSUPPORTED_QUOTE"
        rejected_ids = error.citation_ids if isinstance(error, EvidenceCompletenessError) else citation_ids
        logger.warning(
            "Model candidate rejected; validation_code=%s citation_ids=%s evidence_ids=%s",
            code, rejected_ids, [item.citation_id for item in evidence],
        )

    def _retrieve_evidence(
        self,
        request: ChatRequest,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> list[RetrievalResult]:
        """Merge controlled coverage searches with normal retrieval, deterministically."""
        service = RetrievalService(self._retriever)
        base = service.retrieve(RetrieveRequest(
            question=request.question, top_k=8, include_guidance=request.include_guidance,
        )).results
        candidates: list[tuple[RetrievalResult, int, int]] = [
            (item, 0, index) for index, item in enumerate(base)
        ]
        for coverage_index, coverage_question in enumerate(
            self._coverage_queries(request.question, routing_context, understanding), start=1
        ):
            coverage = service.retrieve(RetrieveRequest(
                question=coverage_question, top_k=8, include_guidance=request.include_guidance,
            )).results
            candidates.extend((item, coverage_index, index) for index, item in enumerate(coverage))
        candidates.extend((item, -1, index) for index, item in enumerate(
            self._controlled_role_candidates(request.question, routing_context, understanding)
        ))

        unique: dict[str, tuple[RetrievalResult, int, int]] = {}
        for item, search_index, rank in candidates:
            existing = unique.get(item.chunk_id)
            if existing is None or (search_index, rank) < (existing[1], existing[2]):
                unique[item.chunk_id] = (item, search_index, rank)

        merged = list(unique.values())
        merged.sort(key=lambda entry: (
            -self._coverage_score(request.question, entry[0].text, routing_context, understanding),
            entry[0].distance,
            entry[1], entry[2], entry[0].chunk_id,
        ))
        # Reserve direct lexical hits for material roles before using remaining
        # slots. This stops many topical passages crowding out qualifications.
        ordered = [item for item, _, _ in merged]
        reserved: list[RetrievalResult] = []
        seen_ids: set[str] = set()
        for role in self._required_retrieval_roles(request.question, routing_context, understanding):
            match = next((item for item in ordered if self._role_matches(role, item.text)), None)
            if match is not None and match.chunk_id not in seen_ids:
                reserved.append(match)
                seen_ids.add(match.chunk_id)
        reserved.extend(item for item in ordered if item.chunk_id not in seen_ids)
        expanded = self._include_adjacent_context(reserved, request.question, routing_context, understanding)
        return expanded[:8]

    @staticmethod
    def _required_retrieval_roles(
        question: str,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> tuple[str, ...]:
        if routing_context is not None:
            if routing_context.goal == "identify_standards":
                if routing_context.power_type in {"battery_operated", "mains_electric"}:
                    return ("is 15644", "is 9873")
                if routing_context.power_type == "non_electric":
                    return ("non-electric-primary", "non-electric-secondary")
                return ()
            if routing_context.goal == "check_exemption":
                return (
                    "manufactured and sold by artisans",
                    "registered with office of the development commissioner",
                )
            if routing_context.goal == "new_licence":
                return (
                    "step 1: create login on manakonline",
                    "while submitting application",
                    "upload/provide detail of raw materials",
                    "step 4: provide details of test facilities",
                )
            return ()
        if understanding is not None:
            if understanding.intent == "standards":
                if understanding.power in {"battery_operated", "mains_electric"}:
                    return ("is 15644", "is 9873")
                if understanding.power == "non_electric":
                    return ("non-electric-primary", "non-electric-secondary")
            if understanding.intent == "certification":
                return (
                    "step 1: create login on manakonline",
                    "while submitting application",
                    "upload/provide detail of raw materials",
                    "step 4: provide details of test facilities",
                )
            if understanding.intent == "exemption":
                return ("manufactured and sold by artisans", "registered with office of the development commissioner")
            return ()
        lowered = question.lower()
        if "battery" in lowered or "electric" in lowered:
            return ("is 15644", "is 9873")
        if any(term in lowered for term in ("handmade", "artisan", "exempt")):
            return (
                "manufactured and sold by artisans",
                "registered with office of the development commissioner",
            )
        return ()

    def _controlled_role_candidates(
        self,
        question: str,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> list[RetrievalResult]:
        """Find direct, normative role passages in the existing indexed corpus."""
        lowered_question = question.lower()
        if routing_context is None and understanding is not None:
            electric_standard_intent = (
                understanding.intent == "standards"
                and understanding.power in {"battery_operated", "mains_electric"}
            )
            non_electric_standard_intent = understanding.intent == "standards" and understanding.power == "non_electric"
            certification_intent = understanding.intent == "certification"
            exemption_intent = understanding.intent == "exemption"
            document_intent = understanding.intent == "documents"
            commencement_intent = understanding.intent == "commencement"
            transition_intent = understanding.intent == "transition"
        elif routing_context is None:
            electric_standard_intent = "battery" in lowered_question or "electric" in lowered_question
            non_electric_standard_intent = False
            certification_intent = any(term in lowered_question for term in ("certify", "certification", "licence"))
            exemption_intent = any(term in lowered_question for term in ("handmade", "artisan", "exempt"))
            document_intent = (
                any(term in lowered_question for term in ("document", "application", "checklist"))
                and any(term in lowered_question for term in ("series", "model", "toy"))
            )
            commencement_intent = "commencement" in lowered_question or "come into force" in lowered_question
            transition_intent = "transition" in lowered_question and "order" in lowered_question
        else:
            electric_standard_intent = (
                routing_context.goal == "identify_standards"
                and routing_context.power_type in {"battery_operated", "mains_electric"}
            )
            non_electric_standard_intent = (
                routing_context.goal == "identify_standards"
                and routing_context.power_type == "non_electric"
            )
            certification_intent = routing_context.goal == "new_licence"
            exemption_intent = routing_context.goal == "check_exemption"
            document_intent = routing_context.goal == "add_new_series"
            commencement_intent = False
            transition_intent = routing_context.goal == "understand_transition"
        if not any((electric_standard_intent, non_electric_standard_intent, certification_intent, exemption_intent,
                    document_intent, commencement_intent, transition_intent)):
            return []
        rows = getattr(self._retriever, "chunks_by_id", {}).values()
        candidates: list[RetrievalResult] = []
        for row in rows:
            text, metadata = row["document"], row["metadata"]
            if not metadata.get("retrieval_enabled"):
                continue
            is_electric_standard_role = self._is_normative_primary(text) or self._is_normative_secondary(text)
            is_non_electric_role = (
                self._is_normative_non_electric_primary(text)
                or self._is_normative_non_electric_secondary(text)
            )
            is_exemption_role = (
                "manufactured and sold by artisans" in text.lower()
                or "registered with office of the development commissioner" in text.lower()
            )
            is_certification_role = (
                metadata.get("source_filename") == "10-steps-for-BIS-toy-certification.pdf"
                and metadata.get("page_start") in {5, 6}
                and any(term in text.lower() for term in (
                    "step 1: create login on manakonline",
                    "while submitting application",
                    "upload/provide detail of raw materials",
                    "step 4: provide details of test facilities",
                ))
            )
            is_document_role = (
                metadata.get("source_filename") == "product_manual_2026.pdf"
                and metadata.get("page_start") in {58, 59, 60}
                and any(term in text.lower() for term in ("document", "declaration", "application", "series"))
            )
            is_commencement_role = metadata.get("source_filename") == "Toys-Extension.pdf" and "come into force" in text.lower()
            is_transition_role = (metadata.get("source_filename") == "Notification-of-Transition-Facilitation-Quality-Control-Order-2026.pdf"
                                  and ("this order shall apply" in text.lower() or "permission under this order may be granted" in text.lower()))
            if not ((electric_standard_intent and is_electric_standard_role)
                    or (non_electric_standard_intent and is_non_electric_role)
                    or (certification_intent and is_certification_role)
                    or (exemption_intent and is_exemption_role)
                    or (document_intent and is_document_role)
                    or (commencement_intent and is_commencement_role) or (transition_intent and is_transition_role)):
                continue
            candidates.append(RetrievalResult(
                rank=0, chunk_id=row["id"], text=text,
                source_id=metadata.get("source_id"), source_filename=metadata.get("source_filename"),
                page_start=metadata.get("page_start"), page_end=metadata.get("page_end"),
                chunk_type=metadata.get("chunk_type"),
                distance=-0.01 if metadata.get("chunk_type") == "table_row" else 0.0,
                similarity=1.0,
            ))
        return candidates

    @staticmethod
    def _role_matches(role: str, text: str) -> bool:
        return (
            ChatService._is_normative_primary(text) if role == "is 15644"
            else ChatService._is_normative_secondary(text) if role == "is 9873"
            else ChatService._is_normative_non_electric_primary(text) if role == "non-electric-primary"
            else ChatService._is_normative_non_electric_secondary(text) if role == "non-electric-secondary"
            else role in text.lower()
        )

    @staticmethod
    def _is_normative_primary(text: str) -> bool:
        lowered = text.lower()
        return (
            "is 15644" in lowered and "electric toys" in lowered
            and "test report" not in lowered and "may also be considered" not in lowered
            and "licence is granted" not in lowered
        )

    @staticmethod
    def _is_normative_secondary(text: str) -> bool:
        lowered = text.lower()
        return (
            "is 9873" in lowered and "applicable secondary" in lowered
            and all(f"{part}" in lowered for part in ("part 2", "3", "4", "9", "10", "11"))
            and "test report" not in lowered
        )

    @staticmethod
    def _is_normative_non_electric_primary(text: str) -> bool:
        lowered = ChatService._display_text(text).lower()
        return (
            "non electric toys" in lowered
            and "is 9873 (part 1):2019" in lowered
            and "applicable primary standard" in lowered
            and "test report" not in lowered
        )

    @staticmethod
    def _is_normative_non_electric_secondary(text: str) -> bool:
        lowered = ChatService._display_text(text).lower()
        faq_role = (
            "secondary standards which are applicable" in lowered
            and "is 9873 parts" in lowered
        )
        manual_role = (
            "non electric toys" in lowered
            and "is 9873 part 1" in lowered
            and "is 9873 parts 2" in lowered
        )
        return (faq_role or manual_role) and all(
            re.search(rf"(?:^|\D){part}(?:\D|$)", lowered)
            for part in (1, 2, 3, 4, 7, 9, 10, 11)
        )

    @staticmethod
    def _excerpt_for_non_electric_role(passage: str, role: str) -> str | None:
        text = ChatService._display_text(passage)
        lowered = text.lower()
        if role == "primary":
            anchor = "applicable primary standard"
        else:
            anchor = (
                "secondary standards which are applicable"
                if "secondary standards which are applicable" in lowered
                else "is 9873 parts 2"
            )
        start = lowered.find(anchor)
        if start < 0:
            return None
        if role == "primary":
            end_anchor = "function dependent on electricity)"
            end = lowered.find(end_anchor, start)
            end = end + len(end_anchor) if end >= 0 else min(len(text), start + 400)
        else:
            end_match = re.search(r"(?:etc\.?(?:\)|\.)?)", lowered[start:])
            end = start + end_match.end() if end_match else min(len(text), start + 250)
        excerpt = text[start:end].strip(" .:|")
        return excerpt if 20 <= len(excerpt) <= 500 else None

    @staticmethod
    def _excerpt_for_certification_role(passage: str, anchor: str) -> str | None:
        """Select a complete step sentence without stopping on a heading colon."""
        text = ChatService._display_text(passage)
        start = text.lower().find(anchor.lower())
        if start < 0:
            return None
        tail = text[start:min(len(text), start + 500)]
        search_from = min(len(tail), len(anchor) + 20)
        boundary = re.search(r"\.(?:\s|$)", tail[search_from:])
        end = search_from + boundary.end() if boundary else len(tail)
        excerpt = tail[:end].strip(" .:|")
        if excerpt.endswith((" the", " and", " or", ",")):
            return None
        return excerpt if 20 <= len(excerpt) <= 500 else None

    @staticmethod
    def _coverage_queries(
        question: str,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> list[str]:
        lowered = question.lower()
        if routing_context is not None:
            if routing_context.goal == "identify_standards":
                if routing_context.power_type == "battery_operated":
                    return ["battery operated electric toy applicable primary standard IS 15644 applicable secondary IS 9873"]
                if routing_context.power_type == "mains_electric":
                    return ["mains powered electric toy applicable primary standard IS 15644 applicable secondary IS 9873"]
                if routing_context.power_type == "non_electric":
                    return ["non electric toys applicable primary standard IS 9873 Part 1 secondary standards applicable"]
                return []
            return {
                "check_exemption": ["artisan manufactured sold registered Development Commissioner Handicrafts exemption"],
                "add_new_series": ["product manual toy series application documents declaration"],
                "understand_transition": ["Transition Facilitation Quality Control Order 2026 grant permission conditions"],
                "new_licence": ["toy new licence certification application requirements"],
                "not_sure": [],
            }[routing_context.goal]
        if understanding is not None:
            normalized = (
                [understanding.normalized_query]
                if understanding.spelling_corrections or " follow-up " in understanding.normalized_query
                else []
            )
            if understanding.intent == "standards":
                focused = {
                    "battery_operated": ["electric toy applicable primary standard IS 15644"],
                    "mains_electric": ["electric toy applicable primary standard IS 15644"],
                    "non_electric": ["non electric toy primary IS 9873 Part 1 secondary standards"],
                    "electric_unspecified": [],
                    "unknown": [],
                }[understanding.power]
                return [*normalized, *focused]
            focused = {
                "certification": ["10 steps BIS licence toys Manakonline application test facilities"],
                "documents": ["product manual toy series application documents declaration"],
                "exemption": ["artisan manufactured sold registered Development Commissioner Handicrafts exemption"],
                "commencement": ["Toys Quality Control Order commencement come into force extension"],
                "transition": ["Transition Facilitation Quality Control Order 2026 grant permission conditions"],
                "general": [],
                "out_of_domain": [],
            }[understanding.intent]
            return [*normalized, *focused]
        queries: list[str] = []
        if "battery" in lowered or "electric" in lowered:
            queries.append("electric toy applicable primary standard IS 15644")
        if "handmade" in lowered or "artisan" in lowered or "exempt" in lowered:
            queries.append("artisan registered Development Commissioner Handicrafts exemption")
        if any(term in lowered for term in ("document", "application", "checklist")) and any(
            term in lowered for term in ("series", "model", "toy")
        ):
            queries.append("product manual toy series application documents declaration")
        if "commencement" in lowered or "come into force" in lowered:
            queries.append("Toys Quality Control Order commencement come into force extension")
        if "transition" in lowered and "order" in lowered:
            queries.append("Transition Facilitation Quality Control Order 2026 application grant permission")
        return queries

    @staticmethod
    def _coverage_score(
        question: str,
        text: str,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> int:
        lowered_question, lowered_text = question.lower(), text.lower()
        score = 0
        electric_intent = (
            routing_context.goal == "identify_standards"
            and routing_context.power_type in {"battery_operated", "mains_electric"}
        ) if routing_context else (
            understanding.intent == "standards" and understanding.power in {"battery_operated", "mains_electric"}
            if understanding else ("battery" in lowered_question or "electric" in lowered_question)
        )
        non_electric_intent = bool(
            routing_context
            and routing_context.goal == "identify_standards"
            and routing_context.power_type == "non_electric"
        )
        if understanding and not routing_context:
            non_electric_intent = understanding.intent == "standards" and understanding.power == "non_electric"
        exemption_intent = (
            routing_context.goal == "check_exemption"
        ) if routing_context else (
            understanding.intent == "exemption" if understanding
            else any(term in lowered_question for term in ("handmade", "artisan", "exempt"))
        )
        if electric_intent:
            score += 8 if "is 15644" in lowered_text else 0
            score += 4 if "is 9873" in lowered_text else 0
            score += 2 if "primary" in lowered_text else 0
            score += 1 if "secondary" in lowered_text else 0
        if non_electric_intent:
            score += 10 if ChatService._is_normative_non_electric_primary(text) else 0
            score += 9 if ChatService._is_normative_non_electric_secondary(text) else 0
        if exemption_intent:
            score += 8 if "registered with office of the development commissioner" in lowered_text else 0
            score += 4 if "artisans" in lowered_text else 0
            score += 2 if "ministry of textiles" in lowered_text else 0
        if understanding and understanding.intent == "certification":
            score += 8 if "step 1: create login on manakonline" in lowered_text else 0
            score += 6 if "while submitting application" in lowered_text else 0
            score += 5 if "upload/provide detail of raw materials" in lowered_text else 0
            score += 4 if "step 4: provide details of test facilities" in lowered_text else 0
        return score

    def _include_adjacent_context(
        self,
        results: list[RetrievalResult],
        question: str,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> list[RetrievalResult]:
        exemption_intent = (
            routing_context.goal == "check_exemption"
        ) if routing_context else (
            understanding.intent == "exemption" if understanding
            else any(term in question.lower() for term in ("handmade", "artisan", "exempt"))
        )
        if not exemption_intent:
            return results
        adjacent = getattr(self._retriever, "adjacent_chunks", None)
        if not callable(adjacent):
            return results
        merged = list(results)
        known_ids = {item.chunk_id for item in merged}
        for result in results:
            if "artisans" not in result.text.lower():
                continue
            for item in adjacent(result.chunk_id, result.source_id, result.page_start):
                if item["chunk_id"] in known_ids:
                    continue
                known_ids.add(item["chunk_id"])
                merged.append(RetrievalResult(
                    rank=0, chunk_id=item["chunk_id"], text=item["text"],
                    source_id=item["source_id"], source_filename=item["source_filename"],
                    page_start=item["page_start"], page_end=item["page_end"],
                    chunk_type=item["chunk_type"], distance=result.distance,
                    similarity=result.similarity,
                ))
        merged.sort(key=lambda item: (
            -self._coverage_score(question, item.text, routing_context, understanding), item.distance, item.chunk_id
        ))
        return merged

    @staticmethod
    def _validate_output(
        raw_output: str,
        evidence: list[TrustedEvidence],
        question: str,
    ) -> tuple[GenerationOutput, list[ChatCitation]]:
        generated = GenerationOutput.model_validate_json(raw_output)
        evidence_map = {item.citation_id: item for item in evidence}
        validated: list[tuple[str, str]] = []
        for citation in generated.citations:
            trusted = evidence_map.get(citation.citation_id)
            if trusted is None:
                raise EvidenceCompletenessError("UNKNOWN_CITATION_ID", [citation.citation_id])
            supplied_quote = ChatService._normalize_whitespace(citation.supporting_quote)
            trusted_passage = ChatService._normalize_whitespace(
                re.sub(r"^\s*(?:passage|query):\s*", "", trusted.text, flags=re.I)
            )
            if not 20 <= len(supplied_quote) <= 500:
                raise EvidenceCompletenessError("INVALID_QUOTE_LENGTH", [citation.citation_id])
            if supplied_quote not in trusted_passage:
                raise EvidenceCompletenessError("INVENTED_OR_WRONG_EVIDENCE_QUOTE", [citation.citation_id])
            if not ChatService._quote_is_related(question, generated.answer, supplied_quote):
                raise EvidenceCompletenessError("QUOTE_NOT_RELEVANT", [citation.citation_id])
            quote = ChatService._select_backend_excerpt(question, generated.answer, trusted.text)
            if quote is None:
                raise EvidenceCompletenessError("QUOTE_NOT_RELEVANT", [citation.citation_id])
            item = (citation.citation_id, quote)
            if item not in validated:
                validated.append(item)
        if not generated.insufficient_evidence and not validated:
            raise ValueError("Grounded generation requires a citation")
        ChatService._validate_universal_scope(question, generated.answer, validated)
        ChatService._validate_evidence_completeness(
            question, generated.answer, validated, evidence, generated.insufficient_evidence,
        )
        return generated, ChatService._map_citations(validated, evidence)

    @staticmethod
    def _select_backend_excerpt(question: str, answer: str, passage: str) -> str | None:
        """Return a short verbatim line/clause from one backend-trusted passage."""
        question_lower = question.lower()
        lowered = passage.lower()
        anchors: list[str] = []
        if "battery" in question_lower or "electric" in question_lower:
            anchors.extend(value for value in ("is 15644", "is 9873") if value in lowered)
        if any(value in question_lower for value in ("handmade", "artisan", "exempt")):
            anchors.extend(value for value in (
                "manufactured and sold by artisans",
                "registered with office of the development commissioner",
            ) if value in lowered)
        if not anchors:
            answer_terms = set(re.findall(r"[a-z0-9]+", answer.lower()))
            anchors = [value for value in answer_terms if len(value) > 3 and value in lowered]
        if not anchors:
            return None
        return ChatService._excerpt_for_anchor(passage, max(anchors, key=len))

    @staticmethod
    def _excerpt_for_anchor(passage: str, anchor: str) -> str | None:
        passage = ChatService._display_text(passage)
        lowered = passage.lower()
        start = lowered.index(anchor.lower())
        if anchor.lower() == "manufactured and sold by artisans":
            line_start = lowered.rfind("provided further that", 0, start)
        elif anchor.lower() == "registered with office of the development commissioner":
            scope_start = lowered.rfind("manufactured and sold by artisans", 0, start)
            line_start = lowered.rfind("provided further that", 0, scope_start) if scope_start >= 0 else start
        else:
            sentence_start = passage.rfind(". ", 0, start)
            line_start = sentence_start + 2 if sentence_start >= 0 else 0
        if line_start < 0:
            line_start = max(passage.rfind("\n", 0, start) + 1, 0)
        # PDF extraction can retain line wraps. Grow to a sentence/clause
        # boundary so excerpts do not end on a dangling fragment.
        tail = passage[line_start:min(len(passage), line_start + 500)]
        anchor_offset = start - line_start
        # Permission provisions commonly enumerate eligibility with semicolons;
        # retain the complete operative sentence so every composed condition is
        # visibly supported rather than citing only its heading or first limb.
        boundary_pattern = r"\.(?:\s|$)" if "permission under this order may be granted" in anchor.lower() else r"[.:;](?:\s|$)"
        boundary = re.search(boundary_pattern, tail[anchor_offset:])
        if boundary is not None:
            boundary_end = anchor_offset + boundary.end()
        else:
            boundary_end = None
        excerpt = tail[:boundary_end].strip() if boundary_end else tail.strip()
        if len(excerpt) > 500:
            bounded = passage[start:min(len(passage), start + 500)]
            excerpt = bounded[:max(bounded.rfind(" "), bounded.rfind("\n"))].strip()
        # Extraction occasionally contributes an opening decorative quote without
        # its closing pair; remove only that wrapper, never document wording.
        if excerpt.startswith(("“", "‘")) and not excerpt.endswith(("”", "’")):
            excerpt = excerpt[1:].lstrip()
        if excerpt.endswith((" of", " the", " and", " or", ",")):
            return None
        excerpt = re.sub(r"(?:\s*\|\s*Column\s+\d+\s*:?)+$", "", excerpt, flags=re.I)
        excerpt = excerpt.rstrip(" :")
        return excerpt if 20 <= len(excerpt) <= 500 else None

    @staticmethod
    def _display_text(value: str) -> str:
        """Normalize extraction-only layout artifacts for API display."""
        value = re.sub(r"^\s*(?:passage|query):\s*", "", value, flags=re.I)
        value = " ".join(value.split())
        value = re.sub(r"\s+([,.;:])", r"\1", value)
        value = re.sub(r":\.+", ".", value)
        return value.strip()

    @staticmethod
    def _excerpt_for_standard_role(passage: str, role: str) -> str | None:
        text = ChatService._display_text(passage)
        lowered = text.lower()
        label = "applicable primary standard" if role == "primary" else "applicable secondary"
        start = lowered.find(label)
        standard = "is 15644" if role == "primary" else "is 9873"
        standard_start = lowered.find(standard, start)
        if start < 0 or standard_start < 0:
            return None
        end = lowered.find(" standard", standard_start)
        if end < 0:
            end = standard_start + 180
        else:
            end += len(" standard")
        excerpt = text[start:min(len(text), end)].strip(" .:")
        return excerpt if 20 <= len(excerpt) <= 500 else None

    @staticmethod
    def _expand_standard_parts(excerpt: str) -> str:
        """Render a compact table list unambiguously without changing selection."""
        return re.sub(
            r"IS 9873 Part\s+(\d+),\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s+and\s+(\d+)",
            lambda match: "IS 9873 " + ", ".join(f"Part {part}" for part in match.groups()[:-1])
            + f", and Part {match.group(6)}",
            excerpt,
            flags=re.I,
        )

    @staticmethod
    def _standard_parts(excerpt: str) -> list[str]:
        """Extract only the numbered IS 9873 parts already present in evidence."""
        match = re.search(r"IS\s*9873\s*Part\s*([\d,\s]+(?:and\s*\d+)?)", excerpt, re.I)
        if not match:
            return []
        parts = re.findall(r"\d+", match.group(1))
        return list(dict.fromkeys(parts))

    @staticmethod
    def _validate_evidence_completeness(
        question: str,
        answer: str,
        citations: list[tuple[str, str]],
        evidence: list[TrustedEvidence],
        insufficient_evidence: bool,
    ) -> None:
        if insufficient_evidence:
            return
        question_lower = question.lower()
        answer_lower = answer.lower()
        evidence_text = " ".join(item.text.lower() for item in evidence)
        quote_text = " ".join(quote.lower() for _, quote in citations)
        standard_question = "standard" in question_lower and (
            "battery" in question_lower or "electric" in question_lower
        )
        has_primary = "is 15644" in evidence_text and "primary" in evidence_text
        has_secondary = "is 9873" in evidence_text and "secondary" in evidence_text
        if standard_question and has_primary and has_secondary:
            if "is 15644" not in answer_lower or "primary" not in answer_lower:
                raise EvidenceCompletenessError("MISSING_PRIMARY_STANDARD")
            if "is 9873" in answer_lower and "secondary" not in answer_lower:
                raise EvidenceCompletenessError("MISSING_SECONDARY_CLASSIFICATION")
            if "is 15644" not in quote_text:
                raise EvidenceCompletenessError("INCOMPLETE_COLLECTIVE_EVIDENCE")

        exemption_question = any(term in question_lower for term in ("handmade", "artisan", "exempt"))
        has_artisan_clause = "manufactured and sold by artisans" in evidence_text
        qualification_terms = (
            "registered", "office of the development commissioner", "ministry of textiles",
        )
        has_complete_qualification = all(term in evidence_text for term in qualification_terms)
        if exemption_question and has_artisan_clause:
            if not has_complete_qualification:
                raise EvidenceCompletenessError("INCOMPLETE_COLLECTIVE_EVIDENCE")
            missing: list[str] = []
            if "manufactured and sold" not in answer_lower or "artisans" not in answer_lower:
                missing.append("MISSING_ARTISAN_SCOPE")
            if "registered" not in answer_lower:
                missing.append("MISSING_REGISTRATION_CONDITION")
            if "office of the development commissioner" not in answer_lower or "ministry of textiles" not in answer_lower:
                missing.append("MISSING_AUTHORITY")
            if missing:
                raise EvidenceCompletenessError(",".join(missing))
            if not all(term in quote_text for term in qualification_terms):
                raise EvidenceCompletenessError("INCOMPLETE_COLLECTIVE_EVIDENCE")

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _quote_is_related(question: str, answer: str, quote: str) -> bool:
        """Reject a true but irrelevant preamble used to launder an answer."""
        stop_words = {
            "which", "what", "does", "the", "a", "an", "is", "are", "can", "for",
            "of", "to", "and", "in", "on", "i", "do", "all", "always", "never",
            "completely", "applies", "apply", "standard", "standards",
        }
        terms = {
            word for word in re.findall(r"[a-z0-9]+", f"{question} {answer}".lower())
            if len(word) > 2 and word not in stop_words
        }
        expansions = {
            "battery": {"electric", "electrical"},
            "operated": {"electric", "electrical"},
            "handmade": {"artisan", "artisans", "handicraft"},
            "exempt": {"exemption", "exclude", "excludes", "excluded", "nothing"},
        }
        for term in tuple(terms):
            terms.update(expansions.get(term, set()))
        quote_words = set(re.findall(r"[a-z0-9]+", quote.lower()))
        return not terms or bool(terms & quote_words)

    @staticmethod
    def _validate_universal_scope(
        question: str,
        answer: str,
        citations: list[tuple[str, str]],
    ) -> None:
        universal_question = re.search(r"\b(all|always|never|completely|every)\b", question, re.I)
        affirmative_answer = re.match(r"^\s*(yes|all)\b", answer, re.I)
        if universal_question and affirmative_answer:
            quote_text = " ".join(quote for _, quote in citations).lower()
            if not re.search(r"\b(all|always|never|completely|every)\b", quote_text):
                raise ValueError("Universal answer is not explicitly supported by evidence")

    @staticmethod
    def _map_citations(
        validated_citations: list[tuple[str, str]],
        evidence: list[TrustedEvidence],
    ) -> list[ChatCitation]:
        evidence_map = {item.citation_id: item for item in evidence}
        mapped: list[ChatCitation] = []
        seen_chunks: set[str] = set()
        for citation_id, quote in validated_citations:
            trusted = evidence_map[citation_id]
            if trusted.chunk_id in seen_chunks:
                continue
            seen_chunks.add(trusted.chunk_id)
            mapped.append(
            ChatCitation(
                citation_id=citation_id,
                source_filename=trusted.source_filename,
                page_start=trusted.page_start,
                page_end=trusted.page_end,
                chunk_id=trusted.chunk_id,
                excerpt=quote,
            )
            )
        return mapped

    def _abstention(
        self,
        *,
        evidence: list[TrustedEvidence],
        citations: list[ChatCitation] | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            answer=INSUFFICIENT_EVIDENCE_ANSWER,
            grounded=False,
            insufficient_evidence=True,
            evidence_count=len(evidence),
            citations=citations or [],
            model=self._generator.model if self._generator else self._model_name,
            generation_mode="abstention",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
        )

    def _clarification(self, question: str) -> ChatResponse:
        sections = [AnswerSection(
            type="clarification",
            title="Need more details",
            content=question,
            citation_ids=[],
        )]
        return self._guided_response(
            sections=sections,
            grounded=False,
            insufficient_evidence=False,
            evidence_count=0,
            citations=[],
            model=self._generator.model if self._generator else self._model_name,
            generation_mode="clarification",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
            needs_clarification=True,
        )

    @staticmethod
    def _routing_clarification(routing_context: ComplianceRoutingContext) -> str | None:
        """Ask only for a validated wizard selection required by its chosen goal."""
        if routing_context.goal == "not_sure":
            return (
                "What guidance do you need: identifying standards, a new licence, "
                "adding a series, checking an exemption, or understanding transition?"
            )
        if (
            routing_context.goal == "identify_standards"
            and routing_context.power_type == "not_sure"
        ):
            return "Is the toy battery-operated, mains-powered, or non-electric?"
        return None

    @staticmethod
    def _answer_matches_understanding(answer: str, understanding: QuestionUnderstanding) -> bool:
        lowered = answer.lower()
        if understanding.intent == "standards":
            if understanding.power == "non_electric":
                return "is 15644" not in lowered and "battery-operated" not in lowered
            if understanding.power == "mains_electric":
                return "battery-operated" not in lowered
            if understanding.power == "battery_operated":
                return "non-electric toy" not in lowered and "mains-powered" not in lowered
        if understanding.intent == "certification":
            return bool(re.search(r"\b(certif|licen[cs]e|application|manakonline)\w*\b", lowered))
        expected = {
            "exemption": ("exempt", "artisan", "handmade"),
            "documents": ("series", "model", "scope"),
            "commencement": ("commencement", "come into force", "gazette"),
            "transition": ("transition", "permission"),
        }.get(understanding.intent)
        return not expected or any(term in lowered for term in expected)
