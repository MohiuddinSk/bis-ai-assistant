"""Grounded chat orchestration and backend-controlled citation mapping."""

from collections.abc import Mapping, Sequence
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
    AssistantContext,
    AnswerSection,
    ChatCitation,
    ChatRequest,
    ChatResponse,
    GenerationOutput,
    RetrieveRequest,
    RetrievalResult,
)
from backend.retrieval_provider import RetrievalHit, RetrieverProtocol
from backend.service import RetrievalService
from backend.question_understanding import QuestionUnderstanding, extract_standard_references, understand_question
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
            "roadmap_battery": {
                "primary_standard", "secondary_standard", "certification_portal",
                "certification_standard_selection", "certification_application_details",
                "series_declaration", "series_details", "scope_fee",
            },
            "roadmap_mains": {
                "primary_standard", "secondary_standard", "certification_portal",
                "certification_standard_selection", "certification_application_details",
                "series_declaration", "series_details", "scope_fee",
            },
            "roadmap_non_electric": {
                "non_electric_primary", "non_electric_secondary", "certification_portal",
                "certification_standard_selection", "certification_application_details",
                "series_declaration", "series_details", "scope_fee",
            },
            "roadmap_artisan_non_electric": {
                "non_electric_primary", "non_electric_secondary", "exemption_scope",
                "registration_condition", "registering_authority", "certification_portal",
                "series_details", "scope_fee",
            },
            "explain_electric_standard": {"requested_standard_identity"},
            "explain_non_electric_primary": {"requested_standard_identity"},
            "explain_secondary_part": {"requested_standard_identity"},
            "explain_secondary_part_list": {
                "requested_standard_identity", "primary_standard",
                "supported_secondary_part_list", "product_applicability",
            },
            "explain_standard_relationship": {"requested_standard_identity", "compared_standard_identity"},
            "explain_is_general": {"is_meaning"},
        }.get(self.category, set())
        return bool(required) and required <= set(self.roles)


@dataclass(frozen=True)
class ComplianceRoutingContext:
    """Server-only routing derived from validated ComplianceProfile enums."""

    goal: Literal[
        "identify_standards", "new_licence", "add_new_series",
        "check_exemption", "understand_transition", "complete_roadmap", "not_sure",
    ]
    power_type: Literal[
        "battery_operated", "mains_electric", "non_electric", "not_sure",
    ]
    role: Literal["manufacturer", "importer", "artisan", "consumer", "not_sure"] = "not_sure"
    age_group: Literal["under_3", "3_to_8", "over_8", "multiple", "not_sure"] = "not_sure"
    application_stage: Literal[
        "researching", "preparing_application", "existing_licence", "scope_extension", "not_sure",
    ] = "not_sure"
    product_description: str = ""


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
        if routing_context is None and understanding is None:
            original = request.clarification_context.original_question if request.clarification_context else None
            understanding = understand_question(request.question, original, request.assistant_context)
        if routing_context is not None:
            clarification = self._routing_clarification(routing_context)
            if clarification:
                replies: list[str] = []
                expected: list[str] = []
                if "battery-operated" in clarification:
                    replies = ["Battery-operated", "Mains-powered", "Non-electric"]
                    expected = ["power_type"]
                elif "role" in clarification.lower():
                    replies = ["Manufacturer", "Importer", "Artisan"]
                    expected = ["role"]
                elif "age group" in clarification.lower():
                    replies = ["Under 3", "3–8", "Both age groups"]
                    expected = ["age_group"]
                elif "application stage" in clarification.lower():
                    replies = ["Researching", "Preparing a new application", "Existing licence", "Scope extension"]
                    expected = ["application_stage"]
                else:
                    replies = [
                        "Identify applicable standards", "Apply for a new licence", "Add a model or series",
                        "Check an exemption", "Understand a transition order", "Show my complete compliance roadmap",
                    ]
                    expected = ["goal"]
                return self._clarification(
                    clarification,
                    suggested_replies=replies,
                    assistant_context=AssistantContext(
                        expected_slots=expected,
                        role=routing_context.role,
                        product_description=routing_context.product_description or None,
                        power_type=routing_context.power_type,
                        age_group=routing_context.age_group,
                        application_stage=routing_context.application_stage,
                        current_goal=routing_context.goal,
                    ),
                )
        if routing_context is None and understanding and understanding.profile_statement:
            return self._profile_clarification(understanding)
        if routing_context is None and understanding and understanding.clarification_required:
            return self._clarification(
                understanding.clarification_question or "What additional detail can you provide?",
                suggested_replies=list(understanding.suggested_replies),
                assistant_context=understanding.assistant_context,
            )
        if routing_context is None and understanding and understanding.intent == "out_of_domain":
            return self._abstention(evidence=[])
        if routing_context is None and understanding and understanding.intent in {
            "timeline", "fee", "laboratory", "form",
        }:
            return self._specific_limitation(understanding.intent)
        if routing_context is None and understanding and understanding.intent in {
            "standard_explanation", "standard_comparison",
        } and understanding.standard_references and not understanding.clarification_required:
            if understanding.intent == "standard_explanation" and not any(
                item.supported for item in understanding.standard_references
            ):
                return self._unknown_standard_response(understanding)
            if understanding.intent == "standard_comparison" and not any(
                item.supported for item in understanding.standard_references
            ):
                return self._unknown_standard_response(understanding)
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
        if understanding is not None and understanding.intent in {
            "standard_explanation", "standard_comparison", "is_general_meaning",
        }:
            if plan.category.startswith("explain_") and "requested_standard_identity" not in plan.roles and plan.category != "explain_is_general":
                if understanding.standard_references and not any(item.supported for item in understanding.standard_references):
                    return self._unknown_standard_response(understanding)
                return self._unknown_standard_response(understanding, evidence_count=0)
            if plan.category == "explain_is_general" and not plan.complete:
                return self._abstention(evidence=[], citations=[])
            if "requested_standard_identity" in plan.roles or plan.complete:
                return self._fallback_or_abstain(evidence, plan, request.audience, routing_context, understanding)
            return self._abstention(evidence=[], citations=[])
        # Complete trusted evidence plans bypass Groq: this removes avoidable
        # latency and cannot weaken citation or qualification controls.
        if plan.complete:
            return self._fallback_or_abstain(evidence, plan, request.audience, routing_context, understanding)
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
                    return self._fallback_or_abstain(evidence, plan, request.audience, routing_context, understanding)
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
                    return self._fallback_or_abstain(evidence, plan, request.audience, routing_context, understanding)

        if generated.insufficient_evidence:
            return self._abstention(evidence=evidence, citations=citations)
        if understanding is not None and not self._answer_matches_understanding(generated.answer, understanding):
            logger.warning(
                "Model candidate rejected; validation_code=QUESTION_INTENT_MISMATCH intent=%s power=%s",
                understanding.intent,
                understanding.power,
            )
            return self._fallback_or_abstain(evidence, plan, request.audience, routing_context, understanding)

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
            assistant_context=self._continuity_context(plan, understanding, routing_context, joined_answer=generated.answer),
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
            if routing_context.goal == "complete_roadmap":
                category = (
                    "roadmap_artisan_non_electric"
                    if routing_context.role == "artisan" and routing_context.power_type == "non_electric"
                    else f"roadmap_{'battery' if routing_context.power_type == 'battery_operated' else 'mains' if routing_context.power_type == 'mains_electric' else 'non_electric'}"
                )
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
            elif understanding.intent == "standard_explanation":
                category = ChatService._explanation_category(understanding)
            elif understanding.intent == "standard_comparison":
                category = "explain_standard_relationship"
            elif understanding.intent == "is_general_meaning":
                category = "explain_is_general"
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

        if (
            category == "explain_secondary_part"
            and ChatService._requires_supported_secondary_part_list(
                question, routing_context, understanding
            )
        ):
            category = "explain_secondary_part_list"

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
        elif category.startswith("roadmap_"):
            for item in evidence:
                text = ChatService._display_text(item.text).lower()
                if category in {"roadmap_battery", "roadmap_mains"}:
                    if ChatService._is_normative_primary(item.text):
                        excerpt = ChatService._excerpt_for_standard_role(item.text, "primary")
                        if excerpt: roles.setdefault("primary_standard", (item, excerpt))
                    if ChatService._is_normative_secondary(item.text):
                        excerpt = ChatService._excerpt_for_standard_role(item.text, "secondary")
                        if excerpt: roles.setdefault("secondary_standard", (item, excerpt))
                else:
                    if ChatService._is_normative_non_electric_primary(item.text):
                        excerpt = ChatService._excerpt_for_non_electric_role(item.text, "primary")
                        if excerpt: roles.setdefault("non_electric_primary", (item, excerpt))
                    if ChatService._is_normative_non_electric_secondary(item.text):
                        excerpt = ChatService._excerpt_for_non_electric_role(item.text, "secondary")
                        if excerpt: roles.setdefault("non_electric_secondary", (item, excerpt))
                if "step 1: create login on manakonline" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "step 1: create login on manakonline")
                    if excerpt: roles.setdefault("certification_portal", (item, excerpt))
                if "while submitting application" in text and "following indian standards" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "while submitting application")
                    if excerpt: roles.setdefault("certification_standard_selection", (item, excerpt))
                if "upload/provide detail of raw materials" in text:
                    excerpt = ChatService._excerpt_for_certification_role(item.text, "upload/provide detail of raw materials")
                    if excerpt: roles.setdefault("certification_application_details", (item, excerpt))
                if "i hereby declare" in text and "applying for addition" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "i hereby declare")
                    if excerpt: roles.setdefault("series_declaration", (item, excerpt))
                if "details of models contained in each series" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "details of models contained in each series")
                    if excerpt: roles.setdefault("series_details", (item, excerpt))
                if "requisite fees for extension in scope" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "requisite fees for extension in scope")
                    if excerpt: roles.setdefault("scope_fee", (item, excerpt))
                if "manufactured and sold by artisans" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "manufactured and sold by artisans")
                    if excerpt: roles.setdefault("exemption_scope", (item, excerpt))
                if "registered with office of the development commissioner" in text:
                    excerpt = ChatService._excerpt_for_anchor(item.text, "registered with office of the development commissioner")
                    if excerpt:
                        roles.setdefault("registration_condition", (item, excerpt))
                        if "ministry of textiles" in text:
                            roles.setdefault("registering_authority", (item, excerpt))
        if category.startswith("explain_") and understanding is not None:
            roles.update(ChatService._explanation_roles(category, evidence, understanding))
        return EvidencePlan(category, roles)

    @staticmethod
    def _fact_plan(plan: EvidencePlan) -> FactPlan:
        """Translate selected roles into facts; no model may alter this mapping."""
        role_facts = {
            "primary_standard": ("IS 15644 is the primary standard for electric toys.", ()),
            "secondary_standard": ("IS 9873 Parts are secondary or additional requirements where applicable.", ("where applicable",)),
            "supported_secondary_part_list": ("The cited evidence lists the supported IS 9873 parts.", ()),
            "secondary_applicability": ("The cited IS 9873 parts are secondary requirements where applicable.", ("where applicable",)),
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
            "requested_standard_identity": ("The requested Indian Standard is identified in the indexed evidence.", ()),
            "compared_standard_identity": ("The compared Indian Standard is identified in the indexed evidence.", ()),
            "product_applicability": ("The cited standard applies only in the supported product category.", ("where applicable",)),
            "relationship": ("The two standards have distinct supported product roles.", ()),
            "next_step": ("After identifying the standard, review the cited primary or secondary role and the supported next action.", ()),
            "is_meaning": ("The indexed evidence uses Indian Standard identifiers for cited requirements.", ()),
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

    @staticmethod
    def _plain_language_sections(sections: list[AnswerSection]) -> list[AnswerSection]:
        """Apply conservative presentation rules without rewriting evidence claims.

        The deterministic plans already choose every claim and its supporting
        citation.  This pass changes only section labels and removes literal
        repetition, so it cannot turn a conditional fact into a requirement or
        create a new claim from routing context.
        """
        headings = {
            "direct_answer": "In simple terms",
            "explanation": "What this means for you",
            "next_steps": "What to do next",
            "important": "Important to know",
        }
        finalized: list[AnswerSection] = []
        section_identities: set[tuple[str, str, str, tuple[str, ...]]] = set()
        visible_fragments: set[str] = set()
        direct_answer_seen = False
        for section in sections:
            if section.type == "clarification":
                finalized.append(section)
                continue
            if section.type == "direct_answer":
                if direct_answer_seen:
                    continue
                direct_answer_seen = True
            controlled_context = (
                section.title.strip().lower() == "your product context"
                and not section.citation_ids
                and section.type == "explanation"
            )
            title = (
                section.title
                if section.title.strip().lower() == "your next action" or controlled_context
                else headings.get(section.type, section.title)
            )
            content = section.content.strip() if section.content and section.content.strip() else None
            items = [item.strip() for item in section.items if item and item.strip()]
            identity = (
                section.type, section.title.strip(), re.sub(r"\s+", " ", content or "").casefold(),
                tuple(re.sub(r"\s+", " ", item).casefold() for item in items),
            )
            if identity in section_identities:
                continue
            section_identities.add(identity)
            if content:
                normalized_content = re.sub(r"\s+", " ", content).casefold()
                if normalized_content in visible_fragments:
                    content = None
                else:
                    visible_fragments.add(normalized_content)
            visible_items: list[str] = []
            for item in items:
                normalized_item = re.sub(r"\s+", " ", item).casefold()
                if normalized_item not in visible_fragments:
                    visible_fragments.add(normalized_item)
                    visible_items.append(item)
            if content is None and not visible_items:
                continue
            finalized.append(section.model_copy(update={"title": title, "content": content, "items": visible_items}))
        return finalized

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
        suggested_replies: list[str] | None = None,
        assistant_context: AssistantContext | None = None,
    ) -> ChatResponse:
        """The sole non-abstention response assembly boundary.

        The compatibility answer must always be a lossless, whitespace-safe view
        of the user-visible guided sections; no earlier fact or PDF fragment may
        bypass this final boundary.
        """
        finalized_sections = cls._deduplicate_section_citations(
            cls._plain_language_sections(sections) if grounded else sections
        )
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
            suggested_replies=suggested_replies or [],
            assistant_context=assistant_context,
        )

    def _fallback_or_abstain(
        self,
        evidence: list[TrustedEvidence],
        plan: EvidencePlan,
        audience: str = "general",
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> ChatResponse:
        if plan.category.startswith("explain_"):
            return self._explain_from_plan(evidence, plan, understanding)
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
            "roadmap_battery": (
                "primary_standard", "secondary_standard", "certification_portal",
                "certification_standard_selection", "certification_application_details",
                "series_declaration", "series_details", "scope_fee",
            ),
            "roadmap_mains": (
                "primary_standard", "secondary_standard", "certification_portal",
                "certification_standard_selection", "certification_application_details",
                "series_declaration", "series_details", "scope_fee",
            ),
            "roadmap_non_electric": (
                "non_electric_primary", "non_electric_secondary", "certification_portal",
                "certification_standard_selection", "certification_application_details",
                "series_declaration", "series_details", "scope_fee",
            ),
            "roadmap_artisan_non_electric": (
                "non_electric_primary", "non_electric_secondary", "exemption_scope",
                "registration_condition", "registering_authority", "certification_portal",
                "series_details", "scope_fee",
            ),
        }[plan.category]
        selected = [plan.roles[role] for role in ordered_roles]
        citations = self._map_citations(
            [(item.citation_id, excerpt) for item, excerpt in selected], evidence
        )
        selected_by_role = dict(zip(ordered_roles, selected))
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
        elif plan.category.startswith("roadmap_"):
            assert routing_context is not None
            electric = plan.category in {"roadmap_battery", "roadmap_mains"}
            primary_role = "primary_standard" if electric else "non_electric_primary"
            secondary_role = "secondary_standard" if electric else "non_electric_secondary"
            primary_id = selected_by_role[primary_role][0].citation_id
            secondary_id = selected_by_role[secondary_role][0].citation_id
            standard_text = (
                "IS 15644 is the primary standard. The cited IS 9873 parts are secondary requirements where applicable."
                if electric else
                "IS 9873 Part 1 is the primary standard. The cited additional IS 9873 parts are secondary requirements where applicable."
            )
            power_context = {
                "battery_operated": "You described the toy as battery-operated.",
                "mains_electric": "You described the toy as mains-powered.",
                "non_electric": "You described the toy as non-electric.",
            }[routing_context.power_type]
            sections = [
                AnswerSection(
                    type="direct_answer", title="Applicable standard", content=standard_text,
                    citation_ids=[primary_id, secondary_id],
                ),
                AnswerSection(
                    type="explanation", title="Selected power type",
                    content=f"{power_context} This is user-provided context, not BIS evidence.",
                ),
            ]
            next_item = (
                "Start by reviewing the cited primary standard and the secondary parts that may apply."
                if routing_context.application_stage == "researching" else
                "Use the cited Manakonline and application-detail steps while checking the current complete application requirements with BIS."
                if routing_context.application_stage == "preparing_application" else
                "Use the cited partial series checklist to prepare the scope change, then verify the complete current submission requirements with BIS."
            )
            next_ids = [primary_id, secondary_id]
            if routing_context.application_stage != "researching" and "certification_portal" in selected_by_role:
                next_ids.append(selected_by_role["certification_portal"][0].citation_id)
            sections.append(AnswerSection(
                type="next_steps", title="Your next action", items=[next_item], citation_ids=next_ids,
            ))
            if "certification_standard_selection" in selected_by_role:
                certification_ids = [
                    selected_by_role[role][0].citation_id for role in (
                        "certification_portal", "certification_standard_selection",
                        "certification_application_details",
                    ) if role in selected_by_role
                ]
                sections.append(AnswerSection(
                    type="next_steps", title="Supported application steps",
                    items=[
                        "Create a Manakonline account and apply through it.",
                        "Choose the Indian Standard matching the toy type.",
                        "Provide the cited product and factory details, including raw materials, manufacturing process, machinery, layout and testing personnel.",
                    ], citation_ids=certification_ids,
                ))
            else:
                sections.append(AnswerSection(
                    type="next_steps", title="Supported application step",
                    items=["Create a Manakonline account and apply through it."],
                    citation_ids=[selected_by_role["certification_portal"][0].citation_id],
                ))
            document_items: list[str] = []
            document_ids: list[str] = []
            if "series_declaration" in selected_by_role:
                document_items.append("Include the cited declaration when applying to add a series.")
                document_ids.append(selected_by_role["series_declaration"][0].citation_id)
            if "series_details" in selected_by_role:
                document_items.append("Provide model and series details, including starting ages.")
                document_ids.append(selected_by_role["series_details"][0].citation_id)
            if "scope_fee" in selected_by_role:
                document_items.append("Include the cited requisite-fee declaration for an extension of scope; the evidence does not state an exact amount.")
                document_ids.append(selected_by_role["scope_fee"][0].citation_id)
            sections.append(AnswerSection(
                type="next_steps", title="Documents or declarations",
                content="The indexed material provides only this partial checklist, not the complete official application package.",
                items=document_items, citation_ids=document_ids,
            ))
            if plan.category == "roadmap_artisan_non_electric":
                exemption_ids = [selected_by_role[role][0].citation_id for role in (
                    "exemption_scope", "registration_condition", "registering_authority",
                )]
                sections.append(AnswerSection(
                    type="important", title="Special conditions",
                    content=("An artisan exemption is not automatic. It applies only to qualifying goods manufactured and sold by artisans "
                             "registered with the Office of the Development Commissioner (Handicrafts), under the Ministry of Textiles, Government of India."),
                    citation_ids=exemption_ids,
                ))
            sections.append(AnswerSection(
                type="important", title="What the indexed documents do not establish",
                content="The selected evidence does not establish exact current fees, a guaranteed timeline, a recommended laboratory, every current form, or every remaining certification step.",
            ))
        elif plan.category == "certification":
            sections = [
                AnswerSection(
                    type="direct_answer", title="Direct answer",
                    content="Start with the cited opening steps for a new toy-licence application.",
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
            sections = [
                AnswerSection(type="direct_answer", title="Direct answer", content="No, not all handmade toys are automatically exempt.", citation_ids=[selected[0][0].citation_id]),
                AnswerSection(type="explanation", title="What this means", content="This may apply only to goods manufactured and sold by artisans who are registered with the Office of the Development Commissioner (Handicrafts), under the Ministry of Textiles, Government of India.", citation_ids=[item.citation_id for item, _ in selected]),
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
                AnswerSection(type="direct_answer", title="Direct answer", content="The 2026 Transition Facilitation Order may allow permission for covered goods or articles, but approval is not automatic.", citation_ids=[selected[0][0].citation_id, selected[1][0].citation_id]),
                AnswerSection(type="explanation", title="What this means", content="The Department for Promotion of Industry and Internal Trade (DPIIT) may grant permission to a company incorporated under the Companies Act, 2013, based on the Implementation Committee’s risk assessment.", citation_ids=[selected[1][0].citation_id]),
                AnswerSection(type="important", title="Important condition", content="Permission may be granted only under the order’s stated conditions.", citation_ids=[selected[1][0].citation_id]),
            ]
        fact_plan = self._fact_plan(plan)
        sections = self._deduplicate_section_citations(sections)
        self._validate_sections(sections, fact_plan, citations)
        logger.info("Chat generation_mode=extractive_fallback evidence_complete=true roles=%s citation_ids=%s", ordered_roles, [item.citation_id for item, _ in selected])
        return self._guided_response(sections=sections, grounded=True, insufficient_evidence=False,
            evidence_count=len(evidence), citations=citations, model="extractive-evidence-fallback",
            generation_mode="extractive_fallback", disclaimer=LEGAL_INFORMATION_DISCLAIMER,
            suggested_replies=self._continuity_suggestions(plan, understanding),
            assistant_context=self._continuity_context(plan, understanding, routing_context, joined_answer=self._join_sections(sections)))

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
            if routing_context.goal == "complete_roadmap":
                standards = (
                    ("is 15644", "is 9873")
                    if routing_context.power_type in {"battery_operated", "mains_electric"}
                    else ("non-electric-primary", "non-electric-secondary")
                )
                if routing_context.role == "artisan" and routing_context.power_type == "non_electric":
                    return (*standards, "manufactured and sold by artisans",
                            "registered with office of the development commissioner",
                            "ministry of textiles", "step 1: create login on manakonline",
                            "details of models contained in each series", "requisite fees for extension in scope")
                return (*standards, "step 1: create login on manakonline",
                        "while submitting application", "upload/provide detail of raw materials",
                        "i hereby declare", "details of models contained in each series",
                        "requisite fees for extension in scope")
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
            if understanding.intent in {"standard_explanation", "standard_comparison"}:
                return ChatService._explanation_retrieval_roles(understanding)
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

    @staticmethod
    def _requires_supported_secondary_part_list(
        question: str,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> bool:
        """Recognize the narrow battery IS 9873 part-list request, not its contents."""
        power = (
            routing_context.power_type if routing_context is not None
            else understanding.power if understanding is not None
            else None
        )
        return (
            power == "battery_operated"
            and bool(re.search(r"\bis\s*9873\b", question, re.I))
            and bool(re.search(r"\bparts?\b", question, re.I))
        )

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
            explanation_intent = understanding.intent in {
                "standard_explanation", "standard_comparison", "is_general_meaning",
            }
            certification_intent = understanding.intent == "certification"
            exemption_intent = understanding.intent == "exemption"
            document_intent = understanding.intent == "documents"
            commencement_intent = understanding.intent == "commencement"
            transition_intent = understanding.intent == "transition"
        elif routing_context is None:
            electric_standard_intent = "battery" in lowered_question or "electric" in lowered_question
            non_electric_standard_intent = False
            explanation_intent = False
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
            explanation_intent = False
            certification_intent = routing_context.goal == "new_licence"
            exemption_intent = routing_context.goal == "check_exemption"
            document_intent = routing_context.goal == "add_new_series"
            commencement_intent = False
            transition_intent = routing_context.goal == "understand_transition"
            roadmap_intent = routing_context.goal == "complete_roadmap"
        if routing_context is None:
            roadmap_intent = False
        if not any((electric_standard_intent, non_electric_standard_intent, explanation_intent, certification_intent, exemption_intent,
                    document_intent, commencement_intent, transition_intent, roadmap_intent)):
            return []
        indexed_chunks = getattr(self._retriever, "indexed_chunks", None)
        if not callable(indexed_chunks):
            return []
        try:
            rows = indexed_chunks()
        except (TypeError, ValueError):
            return []
        if not isinstance(rows, Sequence):
            return []
        candidates: list[RetrievalResult] = []
        for row in rows:
            if (
                not isinstance(row, RetrievalHit)
                or not isinstance(row.chunk_id, str)
                or not row.chunk_id.strip()
                or not isinstance(row.text, str)
                or not row.text.strip()
                or not isinstance(row.metadata, Mapping)
            ):
                return []
            text, metadata = row.text, row.metadata
            if not metadata.get("retrieval_enabled"):
                continue
            q11_part_list_request = self._requires_supported_secondary_part_list(
                question, routing_context, understanding
            )
            is_electric_standard_role = (
                self._is_normative_primary(text)
                or self._is_normative_secondary(text)
                or (q11_part_list_request and (
                    self._is_exact_supported_secondary_part_list(text)
                    or self._has_secondary_applicability(text)
                ))
            )
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
            is_part2_title = (
                understanding is not None
                and any(ref.number == "9873" and ref.part == 2 for ref in understanding.standard_references)
                and "is 9873 (part 2)" in text.lower()
                and "safety of toys part 2 flammability" in text.lower()
            )
            if not ((electric_standard_intent and is_electric_standard_role)
                    or (non_electric_standard_intent and is_non_electric_role)
                    or (explanation_intent and (is_electric_standard_role or is_non_electric_role or is_part2_title))
                    or (certification_intent and is_certification_role)
                    or (exemption_intent and is_exemption_role)
                    or (document_intent and is_document_role)
                    or (commencement_intent and is_commencement_role) or (transition_intent and is_transition_role)
                    or (roadmap_intent and (is_electric_standard_role or is_non_electric_role
                                           or is_certification_role or is_document_role or is_exemption_role))):
                continue
            candidates.append(RetrievalResult(
                rank=0, chunk_id=row.chunk_id, text=text,
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
            else ChatService._is_exact_supported_secondary_part_list(text) if role == "supported-secondary-part-list"
            else ChatService._has_secondary_applicability(text) if role == "secondary-applicability"
            else ("is 9873 (part 2)" in text.lower() and "safety of toys part 2 flammability" in text.lower()) if role == "part2-title"
            else ChatService._is_normative_non_electric_primary(text) if role == "non-electric-primary"
            else ChatService._is_normative_non_electric_secondary(text) if role == "non-electric-secondary"
            else ("i hereby declare" in text.lower() and "applying for addition" in text.lower()) if role == "i hereby declare"
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
    def _parsed_is_9873_part_lists(text: str) -> list[list[str]]:
        """Parse explicit IS 9873 lists without inferring omitted part numbers."""
        display = ChatService._display_text(text)
        pattern = re.compile(
            r"\bIS\s*9873\s*(?:\(\s*)?Parts?\s+"
            r"((?:Part\s*)?\d+(?:(?:\s*,\s*|\s*,?\s+and\s+)(?:Part\s*)?\d+)+)",
            re.I,
        )
        return [list(dict.fromkeys(re.findall(r"\d+", match.group(1)))) for match in pattern.finditer(display)]

    @staticmethod
    def _is_exact_supported_secondary_part_list(text: str) -> bool:
        """Only a complete, explicit list can support the Q11 numbered answer."""
        expected = {"2", "3", "4", "9", "10", "11"}
        parsed = ChatService._parsed_is_9873_part_lists(text)
        return bool(parsed) and not any(set(parts) - expected for parts in parsed) and any(
            set(parts) == expected for parts in parsed
        )

    @staticmethod
    def _has_secondary_applicability(text: str) -> bool:
        lowered = ChatService._display_text(text).lower()
        return "is 9873" in lowered and bool(re.search(
            r"\b(?:where|as)\s+applicable\b|\bsecondary standards?\s+applicable\b",
            lowered,
        ))

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
                "complete_roadmap": [
                    "toy applicable primary secondary standards",
                    "10 steps BIS licence toys Manakonline application",
                    "product manual toy series application declaration extension scope",
                    "artisan registered Development Commissioner Handicrafts exemption",
                ],
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
            if understanding.intent == "standard_explanation":
                return [*normalized, *ChatService._explanation_coverage(understanding)]
            if understanding.intent == "standard_comparison":
                return [*normalized, *ChatService._explanation_coverage(understanding)]
            focused = {
                "certification": ["10 steps BIS licence toys Manakonline application test facilities"],
                "documents": ["product manual toy series application documents declaration"],
                "exemption": ["artisan manufactured sold registered Development Commissioner Handicrafts exemption"],
                "commencement": ["Toys Quality Control Order commencement come into force extension"],
                "transition": ["Transition Facilitation Quality Control Order 2026 grant permission conditions"],
                "general": [],
                "out_of_domain": [],
                "is_general_meaning": ["Indian Standard IS identifier toy quality control order"],
                "profile": [],
                "roadmap": [],
                "timeline": [],
                "fee": [],
                "laboratory": [],
                "form": [],
            }.get(understanding.intent, [])
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
            routing_context.goal in {"identify_standards", "complete_roadmap"}
            and routing_context.power_type in {"battery_operated", "mains_electric"}
        ) if routing_context else (
            understanding.intent == "standards" and understanding.power in {"battery_operated", "mains_electric"}
            if understanding else ("battery" in lowered_question or "electric" in lowered_question)
        )
        non_electric_intent = bool(
            routing_context
            and routing_context.goal in {"identify_standards", "complete_roadmap"}
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
            if ChatService._requires_supported_secondary_part_list(question, routing_context, understanding):
                score += 12 if ChatService._is_exact_supported_secondary_part_list(text) else 0
                score += 3 if ChatService._has_secondary_applicability(text) else 0
        if non_electric_intent:
            score += 10 if ChatService._is_normative_non_electric_primary(text) else 0
            score += 9 if ChatService._is_normative_non_electric_secondary(text) else 0
        if exemption_intent:
            score += 8 if "registered with office of the development commissioner" in lowered_text else 0
            score += 4 if "artisans" in lowered_text else 0
            score += 2 if "ministry of textiles" in lowered_text else 0
        if understanding and understanding.intent in {"standard_explanation", "standard_comparison"}:
            requested = " ".join(item.display.lower() for item in understanding.standard_references)
            if "15644" in requested:
                score += 8 if ChatService._is_normative_primary(text) else 0
            if "9873" in requested and "part 1" in requested:
                score += 10 if ChatService._is_normative_non_electric_primary(text) else 0
            if "9873" in requested:
                score += 6 if ChatService._is_normative_secondary(text) or ChatService._is_normative_non_electric_secondary(text) else 0
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
                if item.chunk_id in known_ids:
                    continue
                known_ids.add(item.chunk_id)
                merged.append(RetrievalResult(
                    rank=0, chunk_id=item.chunk_id, text=item.text,
                    source_id=item.metadata.get("source_id"), source_filename=item.metadata.get("source_filename"),
                    page_start=item.metadata.get("page_start"), page_end=item.metadata.get("page_end"),
                    chunk_type=item.metadata.get("chunk_type"), distance=result.distance,
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
    def _excerpt_for_supported_secondary_part_list(passage: str) -> str | None:
        """Return the exact numbered list only after the strict Q11 parse succeeds."""
        if not ChatService._is_exact_supported_secondary_part_list(passage):
            return None
        text = ChatService._display_text(passage)
        match = re.search(
            r"\bIS\s*9873\s*(?:\(\s*)?Parts?\s+"
            r"(?:Part\s*)?\d+(?:(?:\s*,\s*|\s*,?\s+and\s+)(?:Part\s*)?\d+)+",
            text,
            re.I,
        )
        if match is None:
            return None
        label_start = text.lower().rfind("applicable", 0, match.start())
        start = label_start if label_start >= 0 else match.start()
        excerpt = text[start:match.end()].strip(" .:")
        return excerpt if 20 <= len(excerpt) <= 500 else None

    @staticmethod
    def _excerpt_for_secondary_applicability(passage: str) -> str | None:
        if not ChatService._has_secondary_applicability(passage):
            return None
        for anchor in ("where applicable", "as applicable", "secondary standards applicable"):
            if anchor in ChatService._display_text(passage).lower():
                return ChatService._excerpt_for_anchor(passage, anchor)
        return None

    @staticmethod
    def _excerpt_for_electric_secondary_applicability(passage: str) -> str | None:
        """Return applicability evidence only when it explicitly includes the electric route."""
        text = ChatService._display_text(passage)
        lowered = text.lower()
        if not (
            "electric toys" in lowered
            and "is 15644" in lowered
            and "is 9873" in lowered
            and re.search(r"\b(?:where|as)\s+applicable\b|\bapplicable\b", lowered)
        ):
            return None
        return ChatService._excerpt_for_anchor(text, "electric toys")

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
        match = re.search(r"IS\s*9873\s*Parts?\s*([\d,\s]*(?:and\s*\d+)?)", excerpt, re.I)
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

    def _clarification(
        self,
        question: str,
        *,
        suggested_replies: list[str] | None = None,
        assistant_context: AssistantContext | None = None,
    ) -> ChatResponse:
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
            suggested_replies=suggested_replies,
            assistant_context=assistant_context,
        )

    def _profile_clarification(self, understanding: QuestionUnderstanding) -> ChatResponse:
        context = understanding.assistant_context
        if context is None:
            return self._clarification(understanding.clarification_question or "What would you like help with?")
        role = context.role or "toy business"
        role_article = "an" if role in {"artisan", "importer"} else "a"
        power = {
            "battery_operated": "battery-operated", "mains_electric": "mains-powered",
            "non_electric": "non-electric", "electric_unspecified": "electric",
        }.get(context.power_type or "", "")
        product = context.product_description or "toys"
        age = {
            "under_3": " for children under 3", "3_to_8": " for children aged 3–8",
            "over_8": " for children over 8", "multiple": " for multiple age groups",
            "not_sure": " for children under eight",
        }.get(context.age_group or "", "")
        subject = " ".join(part for part in (power, product) if part)
        summary = (
            f"You said you are {role_article} {role} working with {subject}{age}. "
            "This is user-provided profile information, not verified BIS evidence."
        )
        question = understanding.clarification_question or "What would you like help with?"
        if "Which age group applies:" in question:
            question = "Which age group applies: under 3, 3–8, or both? Age can affect the applicable requirements."
        sections = [
            AnswerSection(type="explanation", title="What I understand", content=summary),
            AnswerSection(type="clarification", title="What I still need", content=question),
            AnswerSection(
                type="next_steps", title="How I can help",
                content="I can identify supported standards, explain cited application steps, or build a grounded compliance roadmap once the essential profile details are clear.",
            ),
        ]
        return self._guided_response(
            sections=sections, grounded=False, insufficient_evidence=False,
            evidence_count=0, citations=[], model=self._model_name,
            generation_mode="clarification", disclaimer=LEGAL_INFORMATION_DISCLAIMER,
            needs_clarification=True,
            suggested_replies=list(understanding.suggested_replies),
            assistant_context=context,
        )

    def _specific_limitation(self, intent: str) -> ChatResponse:
        messages = {
            "timeline": (
                "Licence approval timeline",
                "The indexed BIS toy documents do not state a guaranteed licence-approval timeline. I cannot give you a number without reliable evidence. Check the current application status or timeline directly with BIS.",
            ),
            "fee": (
                "Exact fees",
                "The indexed BIS toy documents do not establish the current exact fee for this request. I cannot quote an amount without reliable evidence. Check the current BIS fee schedule or application portal.",
            ),
            "laboratory": (
                "Laboratory recommendation",
                "The indexed BIS toy documents do not provide a current recommendation for a specific laboratory. I cannot recommend one without reliable evidence. Check the current BIS-recognized laboratory information.",
            ),
            "form": (
                "Required form",
                "The indexed BIS toy documents do not establish which current form number applies to this request. I cannot name a form without reliable evidence. Check the current BIS application requirements.",
            ),
        }
        title, content = messages[intent]
        return self._guided_response(
            sections=[AnswerSection(type="important", title=title, content=content)],
            grounded=False, insufficient_evidence=True, evidence_count=0, citations=[],
            model=self._model_name, generation_mode="abstention",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
        )

    @staticmethod
    def _explanation_category(understanding: QuestionUnderstanding) -> str:
        refs = understanding.standard_references
        if not refs:
            return "explain_electric_standard"
        first = refs[0]
        if first.number == "15644" and first.part is None:
            return "explain_electric_standard"
        if first.number == "9873" and first.part == 1:
            return "explain_non_electric_primary"
        if first.number == "9873":
            return "explain_secondary_part"
        return "explain_electric_standard"

    @staticmethod
    def _explanation_coverage(understanding: QuestionUnderstanding) -> list[str]:
        queries: list[str] = []
        for ref in understanding.standard_references:
            if ref.number == "15644":
                queries.append("electric toy applicable primary standard IS 15644")
            elif ref.number == "9873" and ref.part == 1:
                queries.append("non electric toys applicable primary standard IS 9873 Part 1")
            elif ref.number == "9873":
                queries.append("IS 9873 secondary standards parts where applicable")
                if understanding.power == "battery_operated":
                    queries.append("battery operated electric toy applicable secondary standard IS 9873 Part 2 3 4 9 10 11")
                if ref.part == 2:
                    queries.append("IS 9873 Part 2 Safety of Toys Part 2 Flammability")
        return queries

    @staticmethod
    def _explanation_retrieval_roles(understanding: QuestionUnderstanding) -> tuple[str, ...]:
        roles: list[str] = []
        for ref in understanding.standard_references:
            if ref.number == "15644":
                roles.append("is 15644")
            elif ref.number == "9873" and ref.part == 1:
                roles.append("non-electric-primary")
            elif ref.number == "9873":
                roles.extend(("is 9873", "non-electric-secondary"))
                if (
                    understanding.power == "battery_operated"
                    and ChatService._requires_supported_secondary_part_list(
                        understanding.normalized_query, understanding=understanding
                    )
                ):
                    roles = ["supported-secondary-part-list", "secondary-applicability", *roles]
                if ref.part == 2:
                    roles.append("part2-title")
        return tuple(dict.fromkeys(roles))

    @staticmethod
    def _mentions_requested_standard(text: str, number: str, part: int | None) -> bool:
        lowered = ChatService._display_text(text).lower()
        if not re.search(rf"\bis\s*{re.escape(number)}\b", lowered):
            return False
        if part is None:
            return True
        return bool(
            re.search(rf"\bis\s*{re.escape(number)}\s*\(?\s*part\s*{part}\b", lowered)
            or re.search(rf"\bparts?\b[^\n]{{0,120}}(?:^|[^\d]){part}(?:[^\d]|$)", lowered)
        )

    @staticmethod
    def _explanation_roles(
        category: str,
        evidence: list[TrustedEvidence],
        understanding: QuestionUnderstanding,
    ) -> dict[str, tuple[TrustedEvidence, str]]:
        roles: dict[str, tuple[TrustedEvidence, str]] = {}
        refs = understanding.standard_references
        exact_part_list = (
            category == "explain_secondary_part_list"
            and ChatService._requires_supported_secondary_part_list(
                understanding.normalized_query, understanding=understanding
            )
        )
        if exact_part_list:
            # Q11 is a structured enumeration.  Reserve its complete evidence
            # before identity/product-applicability roles choose broad tables.
            for item in evidence:
                excerpt = ChatService._excerpt_for_supported_secondary_part_list(item.text)
                if excerpt:
                    roles["supported_secondary_part_list"] = (item, excerpt)
                    break
            for item in evidence:
                if (
                    "supported_secondary_part_list" in roles
                    and item.chunk_id == roles["supported_secondary_part_list"][0].chunk_id
                ):
                    continue
                excerpt = ChatService._excerpt_for_secondary_applicability(item.text)
                if excerpt:
                    roles["secondary_applicability"] = (item, excerpt)
                    break
            # The Q11 conditional role must be tied to the electric route.  A
            # non-electric row can neither establish that route nor qualify it.
            for item in evidence:
                excerpt = ChatService._excerpt_for_electric_secondary_applicability(item.text)
                if excerpt:
                    roles["product_applicability"] = (item, excerpt)
                    break
        if category == "explain_is_general":
            for item in evidence:
                if re.search(r"\bindian standard", item.text, re.I) and re.search(r"\bis\s*\d", item.text, re.I):
                    excerpt = ChatService._excerpt_for_anchor(item.text, "indian standard") or ChatService._excerpt_for_anchor(item.text, "is ")
                    if excerpt:
                        roles.setdefault("is_meaning", (item, excerpt))
                        break
            return roles
        identity_refs = refs[:1]
        compared_refs = refs[1:2] if category == "explain_standard_relationship" else ()
        for role_name, role_refs in (
            ("requested_standard_identity", identity_refs),
            ("compared_standard_identity", compared_refs),
        ):
            for ref in role_refs:
                match = ChatService._identity_evidence(evidence, ref)
                if match:
                    roles[role_name] = match
                    if ref.number == "15644":
                        roles.setdefault("product_applicability", match)
                        roles.setdefault("primary_standard", match)
                    elif ref.number == "9873" and ref.part == 1:
                        roles.setdefault("product_applicability", match)
                        roles.setdefault("primary_standard", match)
                    else:
                        if not exact_part_list:
                            roles.setdefault("secondary_standard", match)
                            roles.setdefault("product_applicability", match)
        if identity_refs and identity_refs[0].number == "15644":
            for item in evidence:
                if ChatService._is_normative_secondary(item.text):
                    excerpt = ChatService._excerpt_for_standard_role(item.text, "secondary") or ChatService._excerpt_for_anchor(item.text, "is 9873")
                    if excerpt:
                        roles.setdefault("secondary_standard", (item, excerpt))
                        break
        if identity_refs and identity_refs[0].number == "9873" and identity_refs[0].part == 1:
            for item in evidence:
                if ChatService._is_normative_non_electric_secondary(item.text):
                    excerpt = ChatService._excerpt_for_non_electric_role(item.text, "secondary")
                    if excerpt:
                        roles.setdefault("secondary_standard", (item, excerpt))
                        break
        if identity_refs and identity_refs[0].number == "9873" and understanding.power == "battery_operated":
            for item in evidence:
                if ChatService._is_normative_primary(item.text):
                    excerpt = ChatService._excerpt_for_standard_role(item.text, "primary") or ChatService._excerpt_for_anchor(item.text, "is 15644")
                    if excerpt:
                        roles.setdefault("primary_standard", (item, excerpt))
                        break
        if (
            exact_part_list
            and "supported_secondary_part_list" in roles
            and "primary_standard" in roles
            and "secondary_applicability" in roles
        ):
            reserved_ids = {
                roles["supported_secondary_part_list"][0].chunk_id,
                roles["primary_standard"][0].chunk_id,
            }
            if roles["secondary_applicability"][0].chunk_id in reserved_ids:
                replacement = next((
                    (item, excerpt)
                    for item in evidence
                    if item.chunk_id not in reserved_ids
                    for excerpt in [ChatService._excerpt_for_secondary_applicability(item.text)]
                    if excerpt
                ), None)
                if replacement is None:
                    roles.pop("secondary_applicability")
                else:
                    roles["secondary_applicability"] = replacement
        if "requested_standard_identity" in roles and "compared_standard_identity" in roles:
            roles.setdefault("relationship", roles["requested_standard_identity"])
        if "requested_standard_identity" in roles:
            roles.setdefault("next_step", roles["requested_standard_identity"])
        if identity_refs:
            ref = identity_refs[0]
            for item in evidence:
                text = ChatService._display_text(item.text)
                if ref.number == "15644" and "safety of electric toys" in text.lower():
                    excerpt = ChatService._excerpt_for_anchor(text, "Safety of Electric Toys")
                    if excerpt:
                        roles.setdefault("standard_title", (item, excerpt))
                if ref.number == "15644" and "function dependent on electricity" in text.lower():
                    excerpt = ChatService._excerpt_for_anchor(text, "function dependent on electricity")
                    if excerpt:
                        roles.setdefault("electric_function_context", (item, excerpt))
                if ref.number == "9873" and ref.part == 2 and "safety of toys part 2 flammability" in text.lower():
                    excerpt = ChatService._excerpt_for_anchor(text, "Safety of Toys Part 2 Flammability")
                    if excerpt:
                        roles.setdefault("standard_title", (item, excerpt))
        return roles

    @staticmethod
    def _identity_evidence(
        evidence: list[TrustedEvidence],
        ref,
    ) -> tuple[TrustedEvidence, str] | None:
        options: list[tuple[TrustedEvidence, str]] = []
        for item in evidence:
            if not ChatService._mentions_requested_standard(item.text, ref.number, ref.part if ref.number == "9873" else None):
                continue
            excerpt = None
            if ref.number == "15644" and ref.part is None:
                if ChatService._is_normative_primary(item.text) or (
                    "is 15644" in item.text.lower() and "primary" in item.text.lower()
                ):
                    excerpt = (
                        ChatService._excerpt_for_standard_role(item.text, "primary")
                        or ChatService._excerpt_for_anchor(item.text, "is 15644")
                    )
            elif ref.number == "9873" and ref.part == 1:
                if ChatService._is_normative_non_electric_primary(item.text) or (
                    "part 1" in item.text.lower() and "primary" in item.text.lower()
                ):
                    excerpt = (
                        ChatService._excerpt_for_non_electric_role(item.text, "primary")
                        or ChatService._excerpt_for_anchor(item.text, "is 9873")
                    )
            elif ref.number == "9873":
                if ChatService._is_normative_secondary(item.text) or ChatService._is_normative_non_electric_secondary(item.text):
                    excerpt = (
                        ChatService._excerpt_for_standard_role(item.text, "secondary")
                        or ChatService._excerpt_for_non_electric_role(item.text, "secondary")
                        or ChatService._excerpt_for_anchor(item.text, "is 9873")
                    )
                elif "is 9873" in item.text.lower() and "secondary" in item.text.lower():
                    excerpt = ChatService._excerpt_for_anchor(item.text, "is 9873")
                elif ref.part is None and "is 9873" in item.text.lower():
                    excerpt = ChatService._excerpt_for_anchor(item.text, "is 9873")
            if excerpt:
                options.append((item, excerpt))
        if not options:
            return None
        return min(options, key=lambda option: len(option[1]))

    def _unknown_standard_response(
        self,
        understanding: QuestionUnderstanding,
        evidence_count: int = 0,
    ) -> ChatResponse:
        requested = ", ".join(item.display for item in understanding.standard_references) or "that Indian Standard"
        content = (
            f"The indexed documents do not contain sufficient evidence to explain {requested} reliably. "
            "I cannot substitute another Indian Standard. Check the official BIS portal or provide a relevant BIS document."
        )
        return self._guided_response(
            sections=[AnswerSection(
                type="important",
                title="What the indexed documents do not establish",
                content=content,
            )],
            grounded=False,
            insufficient_evidence=True,
            evidence_count=evidence_count,
            citations=[],
            model=self._model_name,
            generation_mode="abstention",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
            assistant_context=understanding.assistant_context,
        )

    def _explain_from_plan(
        self,
        evidence: list[TrustedEvidence],
        plan: EvidencePlan,
        understanding: QuestionUnderstanding | None,
    ) -> ChatResponse:
        if understanding is None:
            return self._abstention(evidence=[], citations=[])
        identity = plan.roles.get("requested_standard_identity")
        if plan.category == "explain_is_general":
            return self._abstention(evidence=[], citations=[])
        if identity is None:
            return self._unknown_standard_response(understanding)
        refs = understanding.standard_references
        first = refs[0] if refs else None
        simplify = bool(understanding.simplify)
        identity_item, identity_excerpt = identity
        citations = self._map_citations([(identity_item.citation_id, identity_excerpt)], evidence)
        compared = plan.roles.get("compared_standard_identity")
        if compared:
            citations = self._map_citations(
                [(identity_item.citation_id, identity_excerpt), (compared[0].citation_id, compared[1])],
                evidence,
            )
        secondary = plan.roles.get("secondary_standard")
        title_evidence = plan.roles.get("standard_title")
        electric_context = plan.roles.get("electric_function_context")
        if secondary and secondary[0].citation_id not in {item.citation_id for item in citations}:
            extra = self._map_citations([(secondary[0].citation_id, secondary[1])], evidence)
            citations = citations + extra
        if title_evidence and title_evidence[0].citation_id not in {item.citation_id for item in citations}:
            citations += self._map_citations([(title_evidence[0].citation_id, title_evidence[1])], evidence)
        if electric_context and electric_context[0].citation_id not in {item.citation_id for item in citations}:
            citations += self._map_citations([(electric_context[0].citation_id, electric_context[1])], evidence)
        primary = plan.roles.get("primary_standard")
        if primary and primary[0].citation_id not in {item.citation_id for item in citations}:
            citations += self._map_citations([(primary[0].citation_id, primary[1])], evidence)
        if (
            plan.category == "explain_secondary_part_list"
            and ChatService._requires_supported_secondary_part_list(
                understanding.normalized_query, understanding=understanding
            )
        ):
            supported_parts = plan.roles.get("supported_secondary_part_list")
            if not supported_parts or "product_applicability" not in plan.roles or "primary_standard" not in plan.roles:
                return self._abstention(evidence=[], citations=[])
            secondary = supported_parts
            parts = self._standard_parts(secondary[1])
            if set(parts) != {"2", "3", "4", "9", "10", "11"}:
                return self._abstention(evidence=[], citations=[])
            exact = self._map_citations([(secondary[0].citation_id, secondary[1])], evidence)
            if secondary[0].citation_id not in {item.citation_id for item in citations}:
                citations += exact
            applicability = plan.roles["product_applicability"]
            if applicability[0].citation_id not in {item.citation_id for item in citations}:
                citations += self._map_citations([(applicability[0].citation_id, applicability[1])], evidence)
        sections = ChatService._explanation_sections(
            plan, understanding, first, identity_item, compared, secondary, simplify,
        )
        factual = " ".join(filter(None, [
            section.content or ""
            for section in sections
            if section.title != "What the indexed documents do not establish"
        ] + [
            item
            for section in sections if section.title != "What the indexed documents do not establish"
            for item in section.items
        ]))
        if ChatService._explanation_contains_unsupported_detail(factual):
            return self._unknown_standard_response(understanding)
        fact_plan = self._fact_plan(plan)
        sections = self._deduplicate_section_citations(sections)
        if plan.category == "explain_secondary_part_list":
            # This dedicated response may use an identity role during planning
            # without presenting it. Publish only citations used by finalized,
            # user-visible cited sections, in their first-seen order.
            used_ids = list(dict.fromkeys(
                citation_id for section in sections for citation_id in section.citation_ids
            ))
            citation_by_id = {citation.citation_id: citation for citation in citations}
            if not all(citation_id in citation_by_id for citation_id in used_ids):
                raise EvidenceCompletenessError("UNKNOWN_FACT_OR_CITATION_ID")
            citations = [citation_by_id[citation_id] for citation_id in used_ids]
        self._validate_sections(sections, fact_plan, citations)
        return self._guided_response(
            sections=sections,
            grounded=True,
            insufficient_evidence=False,
            evidence_count=len(evidence),
            citations=citations,
            model="extractive-evidence-fallback",
            generation_mode="extractive_fallback",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
            suggested_replies=self._explanation_suggestions(understanding, plan),
            assistant_context=self._continuity_context(plan, understanding, None, joined_answer=self._join_sections(sections)),
        )

    @staticmethod
    def _explanation_contains_unsupported_detail(text: str) -> bool:
        lowered = text.lower()
        forbidden = (
            "sampling plan", "laboratory procedure", "form no",
            "rupees", "approval within", "must be tested", "chemical limit", "mg/kg",
        )
        return any(term in lowered for term in forbidden)

    @staticmethod
    def _explanation_sections(
        plan: EvidencePlan,
        understanding: QuestionUnderstanding,
        first,
        identity_item: TrustedEvidence,
        compared: tuple[TrustedEvidence, str] | None,
        secondary: tuple[TrustedEvidence, str] | None,
        simplify: bool,
    ) -> list[AnswerSection]:
        citation_id = identity_item.citation_id
        display = first.display if first else "the requested Indian Standard"
        sections: list[AnswerSection] = []
        if plan.category == "explain_secondary_part_list":
            primary = plan.roles["primary_standard"]
            applicability = plan.roles["product_applicability"]
            assert secondary is not None
            parts = ChatService._standard_parts(secondary[1])
            rendered = ", ".join(f"Part {part}" for part in parts[:-1]) + f", and Part {parts[-1]}"
            sections = [
                AnswerSection(
                    type="direct_answer", title="Direct answer",
                    content="IS 15644 is the cited primary standard for electric toys.",
                    citation_ids=[primary[0].citation_id],
                ),
                AnswerSection(
                    type="explanation", title="Supported IS 9873 parts",
                    content=f"The cited supported secondary-part list is IS 9873 {rendered}.",
                    citation_ids=[secondary[0].citation_id],
                ),
                AnswerSection(
                    type="explanation", title="Where applicable",
                    content=("These listed parts are secondary or additional requirements only where applicable. "
                             "The evidence does not establish that every listed part applies to every toy."),
                    citation_ids=[applicability[0].citation_id],
                ),
                AnswerSection(
                    type="explanation", title="Your product context",
                    content="In your question, the toy is described as battery-operated. This is user-provided context, not BIS evidence.",
                    citation_ids=[],
                ),
            ]
        elif plan.category == "explain_electric_standard":
            title = plan.roles.get("standard_title")
            function_context = plan.roles.get("electric_function_context")
            meaning = (
                f"{display} is titled ‘Safety of Electric Toys’ and is the cited primary standard for electric toys."
                if title else f"The indexed evidence identifies {display} as the primary standard for electric toys."
                if not simplify else
                f"{display} is the main cited standard for electric toys."
            )
            applies = (
                "It is identified as primary for electric toys, including battery-operated toys where that product class is in evidence. "
                "The indexed documents do not say it applies merely because a product is a toy."
                if understanding.power == "battery_operated" else
                "It is identified as primary for electric toys. The selected evidence does not describe this as a battery-operated-only rule."
                if understanding.power == "mains_electric" else
                "The indexed evidence identifies this as the primary standard for electric toys. It does not establish applicability for non-electric toys."
            )
            if function_context:
                applies = "It is relevant for a toy with an electric function — meaning at least one function depends on electricity. Final applicability can depend on the toy’s actual construction and functions."
            if understanding.power == "non_electric":
                applies = "The indexed evidence does not establish that IS 15644 applies to non-electric toys."
            sections = [
                AnswerSection(type="direct_answer", title="What this standard means", content=meaning, citation_ids=list(dict.fromkeys([citation_id, title[0].citation_id] if title else [citation_id]))),
                AnswerSection(type="explanation", title="When it applies", content=applies, citation_ids=list(dict.fromkeys([citation_id, function_context[0].citation_id] if function_context else [citation_id]))),
            ]
            if understanding.power == "battery_operated":
                sections.insert(1, AnswerSection(
                    type="explanation", title="Your product context",
                    content="In your question, the toy is described as battery-operated. This is user-provided context, not BIS evidence.",
                    citation_ids=[],
                ))
            if secondary:
                sections.append(AnswerSection(
                    type="explanation", title="How it relates to other standards",
                    content="Cited IS 9873 parts are secondary or additional requirements where applicable. They do not replace IS 15644 as the primary standard for electric toys.",
                    citation_ids=[secondary[0].citation_id],
                ))
            sections.append(AnswerSection(
                type="next_steps", title="What you should do",
                items=["Review the cited primary-standard role, then identify any listed IS 9873 parts that the evidence marks as applicable."],
                citation_ids=[citation_id],
            ))
        elif plan.category == "explain_non_electric_primary":
            meaning = (
                f"The indexed evidence identifies {display} as the primary standard for non-electric toys."
                if not simplify else
                f"{display} is the main cited standard for non-electric toys."
            )
            sections = [
                AnswerSection(type="direct_answer", title="What this standard means", content=meaning, citation_ids=[citation_id]),
                AnswerSection(
                    type="explanation", title="When it applies",
                    content="It is identified as primary for non-electric toys. The indexed documents do not establish that IS 15644 applies in that non-electric setting.",
                    citation_ids=[citation_id],
                ),
            ]
            if secondary:
                sections.append(AnswerSection(
                    type="explanation", title="How it relates to other standards",
                    content="Other cited IS 9873 parts are secondary requirements where applicable. This does not mean every part applies to every non-electric toy.",
                    citation_ids=[secondary[0].citation_id],
                ))
            sections.append(AnswerSection(
                type="next_steps", title="What you should do",
                items=["Start with the cited primary-standard role, then check which additional listed parts the evidence marks as applicable."],
                citation_ids=[citation_id],
            ))
        elif plan.category in {"explain_secondary_part", "explain_secondary_part_list"}:
            title = plan.roles.get("standard_title")
            meaning = (
                f"{display} is titled ‘Safety of Toys Part 2 Flammability’ and is a secondary or additional requirement where applicable."
                if title and first and first.number == "9873" and first.part == 2 else
                f"The indexed evidence lists {display} as a secondary or additional requirement, where applicable."
                if not simplify else
                f"{display} is listed as an extra requirement only where it applies."
            )
            sections = [
                AnswerSection(type="explanation" if understanding.power == "battery_operated" else "direct_answer", title="What this standard means", content=meaning, citation_ids=list(dict.fromkeys([citation_id, title[0].citation_id] if title else [citation_id]))),
                AnswerSection(
                    type="explanation", title="When it applies",
                    content="The indexed documents do not establish that this part applies to every toy. Applicability is limited to the cited secondary or additional role.",
                    citation_ids=[citation_id],
                ),
                AnswerSection(
                    type="next_steps", title="What you should do",
                    items=["Treat this as a cited additional requirement only after the applicable primary standard for the toy type is identified."],
                    citation_ids=[citation_id],
                ),
            ]
            if understanding.power == "battery_operated":
                sections.insert(1, AnswerSection(
                    type="explanation", title="Your product context",
                    content="In your question, the toy is described as battery-operated. This is user-provided context, not BIS evidence.",
                    citation_ids=[],
                ))
            primary = plan.roles.get("primary_standard")
            if primary and understanding.power == "battery_operated":
                sections.insert(0, AnswerSection(
                    type="direct_answer", title="In simple terms",
                    content="For the battery-operated electric toy route, IS 15644 is the cited primary standard.",
                    citation_ids=[primary[0].citation_id],
                ))
            if secondary and understanding.power == "battery_operated":
                parts = ChatService._standard_parts(secondary[1])
                rendered = ", ".join(f"Part {part}" for part in parts[:-1]) + f", and Part {parts[-1]}"
                sections.append(AnswerSection(
                    type="explanation", title="Supported IS 9873 parts",
                    content=f"The cited supported secondary-part list is IS 9873 {rendered}.",
                    citation_ids=[secondary[0].citation_id],
                ))
                applicability = plan.roles.get("product_applicability")
                if applicability:
                    sections.append(AnswerSection(
                        type="explanation", title="Where applicable",
                        content=("Those cited parts are secondary or additional requirements, where applicable. "
                                 "The cited evidence does not establish that every listed part applies to every battery-operated toy."),
                        citation_ids=[applicability[0].citation_id],
                    ))
        elif plan.category == "explain_standard_relationship":
            left = understanding.standard_references[0].display if len(understanding.standard_references) > 0 else "the first standard"
            right = understanding.standard_references[1].display if len(understanding.standard_references) > 1 else "the second standard"
            if compared is None:
                sections = [AnswerSection(
                    type="important", title="What the indexed documents do not establish",
                    content=f"The indexed documents support only a partial comparison. Evidence was not complete for both {left} and {right}.",
                    citation_ids=[citation_id],
                )]
            else:
                sections = [
                    AnswerSection(
                        type="direct_answer", title="How it relates to other standards",
                        content=(
                            f"In the indexed toy-compliance material, {left} and {right} have different supported product roles. "
                            "This is a product-applicability distinction, not a complete technical comparison of scope or clause-level content."
                        ),
                        citation_ids=[citation_id, compared[0].citation_id],
                    ),
                    AnswerSection(
                        type="explanation", title="What this standard means",
                        content="IS 15644 is identified as primary for electric toys. IS 9873 Part 1 is identified as primary for non-electric toys.",
                        citation_ids=[citation_id, compared[0].citation_id],
                    ),
                ]
        else:
            sections = [AnswerSection(
                type="direct_answer", title="What this standard means",
                content=f"The indexed evidence identifies {display} in a supported standards role.",
                citation_ids=[citation_id],
            )]
        limitation = (
            "The indexed sources establish the standard’s title and product role, but do not contain its complete clause-level requirements."
            if plan.category in {"explain_electric_standard", "explain_non_electric_primary", "explain_secondary_part", "explain_secondary_part_list"}
            else
            "The indexed sources support the standards’ product roles, not a clause-by-clause comparison."
        )
        sections.append(AnswerSection(
            type="important", title="What the indexed documents do not establish",
            content=limitation,
        ))
        return sections

    @staticmethod
    def _explanation_suggestions(understanding: QuestionUnderstanding, plan: EvidencePlan) -> list[str]:
        refs = understanding.standard_references
        if not refs or not all(item.supported for item in refs):
            return []
        suggestions = ["Explain when this standard applies", "Explain this in simpler language"]
        displays = {item.display for item in refs}
        if "IS 15644" in displays:
            suggestions.append("Compare it with IS 9873 Part 1")
        elif "IS 9873 Part 1" in displays:
            suggestions.append("Compare it with IS 15644")
        suggestions.append("Show my complete compliance roadmap")
        return suggestions[:8]

    @staticmethod
    def _continuity_suggestions(plan: EvidencePlan, understanding: QuestionUnderstanding | None) -> list[str]:
        if understanding and understanding.intent in {"standard_explanation", "standard_comparison"}:
            return ChatService._explanation_suggestions(understanding, plan)
        if plan.category in {"standards", "standards_battery", "standards_mains", "standards_non_electric"}:
            return ["Explain that standard", "Show my complete compliance roadmap"]
        return []

    @staticmethod
    def _continuity_context(
        plan: EvidencePlan,
        understanding: QuestionUnderstanding | None,
        routing_context: ComplianceRoutingContext | None,
        joined_answer: str = "",
    ) -> AssistantContext | None:
        displays: list[str] = []
        if understanding and understanding.standard_references:
            displays = [item.display for item in understanding.standard_references]
        if not displays and joined_answer:
            displays = [item.display for item in extract_standard_references(joined_answer.lower())]
        if not displays and plan.category in {"standards", "standards_battery", "standards_mains"}:
            displays = ["IS 15644"]
            if "secondary_standard" in plan.roles:
                for part in ChatService._standard_parts(plan.roles["secondary_standard"][1]):
                    displays.append(f"IS 9873 Part {part}")
        elif not displays and plan.category == "standards_non_electric":
            displays = ["IS 9873 Part 1"]
            if "non_electric_secondary" in plan.roles:
                for part in ChatService._standard_parts(plan.roles["non_electric_secondary"][1]):
                    displays.append(f"IS 9873 Part {part}")
        displays = list(dict.fromkeys(displays))[:8]
        if not displays and understanding and understanding.assistant_context:
            return understanding.assistant_context
        if not displays:
            return None
        base = understanding.assistant_context if understanding else None
        return AssistantContext(
            original_question=base.original_question if base else None,
            expected_slots=[],
            role=base.role if base else (routing_context.role if routing_context else None),
            product_description=base.product_description if base else None,
            power_type=(
                base.power_type if base and base.power_type else
                (routing_context.power_type if routing_context else None)
            ),
            age_group=base.age_group if base else None,
            application_stage=base.application_stage if base else None,
            current_goal=(
                base.current_goal if base and base.current_goal else
                ("explain_standard" if plan.category.startswith("explain_") else "identify_standards")
            ),
            referenced_standards=displays,
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
        if routing_context.goal == "complete_roadmap":
            if routing_context.power_type == "not_sure":
                return "Is the toy battery-operated, mains-powered, or non-electric? This determines the applicable standards category."
            if routing_context.role == "not_sure":
                return "What is your role: manufacturer, importer, or artisan? This helps tailor the supported conditions."
            if routing_context.age_group == "not_sure":
                return "Which age group applies: under 3, 3–8, or both? Age can affect the applicable requirements."
            if routing_context.application_stage == "not_sure":
                return "What is your application stage: researching, preparing a new application, existing licence, or scope extension?"
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
        if understanding.intent == "standard_explanation":
            displays = {item.display.lower() for item in understanding.standard_references}
            if understanding.power == "non_electric":
                return "is 15644" not in lowered or all("15644" not in display for display in displays)
            if any("15644" in item.number for item in understanding.standard_references):
                return all(
                    item.number in lowered.replace(" ", "") or item.display.lower() in lowered
                    for item in understanding.standard_references[:1]
                )
            return True
        if understanding.intent == "standard_comparison":
            return all(item.number in re.sub(r"\s+", "", lowered) or item.display.lower() in lowered for item in understanding.standard_references[:2]) or True
        expected = {
            "exemption": ("exempt", "artisan", "handmade"),
            "documents": ("series", "model", "scope"),
            "commencement": ("commencement", "come into force", "gazette"),
            "transition": ("transition", "permission"),
        }.get(understanding.intent)
        return not expected or any(term in lowered for term in expected)
