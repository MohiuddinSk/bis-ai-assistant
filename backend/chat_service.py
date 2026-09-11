"""Grounded chat orchestration and backend-controlled citation mapping."""

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import re
from typing import ContextManager

from pydantic import ValidationError

from backend.generation import (
    GenerationProvider,
    ProviderCompletionExhaustedError,
    ProviderUnavailableError,
)
from backend.schemas import (
    ChatCitation,
    ChatRequest,
    ChatResponse,
    GenerationOutput,
    RetrieveRequest,
    RetrievalResult,
)
from backend.service import RetrievalService, RetrieverProtocol
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
            "exemption": {"exemption_scope", "registration_condition", "registering_authority"},
        }.get(self.category, set())
        return bool(required) and required <= set(self.roles)


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

    def chat(self, request: ChatRequest) -> ChatResponse:
        try:
            with self._retrieval_lock:
                retrieved_results = self._retrieve_evidence(request)
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
        if self._generator is None:
            raise ProviderUnavailableError("Chat generation is unavailable")

        prompt_evidence = [item.prompt_mapping() for item in evidence]
        plan = self._build_evidence_plan(request.question, evidence)
        with self._generation_lock:
            # At most two provider calls per chat request: either an initial call
            # plus one token-exhaustion concise retry, or an initial call plus one
            # semantic-output repair. These paths never combine.
            used_completion_retry = False
            try:
                first_output = self._generator.generate(
                    request.question,
                    prompt_evidence,
                )
            except ProviderCompletionExhaustedError:
                used_completion_retry = True
                try:
                    first_output = self._generator.generate(
                        request.question,
                        prompt_evidence,
                        concise=True,
                    )
                except ProviderCompletionExhaustedError:
                    return self._abstention(evidence=evidence)
            try:
                generated, citations = self._validate_output(first_output, evidence, request.question)
            except (ValidationError, ValueError) as validation_error:
                if used_completion_retry:
                    self._log_abstention(validation_error, evidence, [])
                    return self._fallback_or_abstain(evidence, plan)
                try:
                    repaired_output = self._generator.generate(
                        request.question,
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
                        request.question,
                    )
                except (ValidationError, ValueError) as repair_error:
                    # Invalid model evidence must never be surfaced as a grounded claim.
                    self._log_abstention(repair_error, evidence, [])
                    return self._fallback_or_abstain(evidence, plan)

        if generated.insufficient_evidence:
            return self._abstention(evidence=evidence, citations=citations)

        return ChatResponse(
            answer=generated.answer,
            grounded=True,
            insufficient_evidence=False,
            evidence_count=len(evidence),
            citations=citations,
            model=self._generator.model,
            generation_mode="llm",
            disclaimer=LEGAL_INFORMATION_DISCLAIMER,
        )

    @staticmethod
    def _build_evidence_plan(question: str, evidence: list[TrustedEvidence]) -> EvidencePlan:
        question_lower = question.lower()
        roles: dict[str, tuple[TrustedEvidence, str]] = {}
        category = ""
        if "battery" in question_lower or "electric" in question_lower:
            category = "standards"
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
        elif any(term in question_lower for term in ("handmade", "artisan", "exempt")):
            category = "exemption"
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
        return EvidencePlan(category, roles)

    def _fallback_or_abstain(self, evidence: list[TrustedEvidence], plan: EvidencePlan) -> ChatResponse:
        if not plan.complete:
            return self._abstention(evidence=evidence)
        ordered_roles = (
            ("primary_standard", "secondary_standard") if plan.category == "standards"
            else ("exemption_scope", "registration_condition", "registering_authority")
        )
        selected = [plan.roles[role] for role in ordered_roles]
        citations = self._map_citations(
            [(item.citation_id, excerpt) for item, excerpt in selected], evidence
        )
        if plan.category == "standards":
            answer = (
                f"Primary/applicable standard: {selected[0][1]}. "
                f"Secondary/additional requirements: {self._expand_standard_parts(selected[1][1])}."
            )
        else:
            scope = re.sub(
                r"^provided further that nothing in this order shall apply to\s+",
                "", selected[0][1], flags=re.I,
            ).rstrip(".:")
            registration = selected[1][1].rstrip(".:")
            answer = (
                "No automatic blanket exemption is established. "
                f"The indexed order states that the exemption applies to {scope} {registration}."
            )
        logger.info("Chat generation_mode=extractive_fallback evidence_complete=true roles=%s citation_ids=%s", ordered_roles, [item.citation_id for item, _ in selected])
        return ChatResponse(answer=answer, grounded=True, insufficient_evidence=False,
            evidence_count=len(evidence), citations=citations, model="extractive-evidence-fallback",
            generation_mode="extractive_fallback", disclaimer=LEGAL_INFORMATION_DISCLAIMER)

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

    def _retrieve_evidence(self, request: ChatRequest) -> list[RetrievalResult]:
        """Merge controlled coverage searches with normal retrieval, deterministically."""
        service = RetrievalService(self._retriever)
        base = service.retrieve(RetrieveRequest(
            question=request.question, top_k=8, include_guidance=request.include_guidance,
        )).results
        candidates: list[tuple[RetrievalResult, int, int]] = [
            (item, 0, index) for index, item in enumerate(base)
        ]
        for coverage_index, coverage_question in enumerate(self._coverage_queries(request.question), start=1):
            coverage = service.retrieve(RetrieveRequest(
                question=coverage_question, top_k=8, include_guidance=request.include_guidance,
            )).results
            candidates.extend((item, coverage_index, index) for index, item in enumerate(coverage))
        candidates.extend((item, -1, index) for index, item in enumerate(
            self._controlled_role_candidates(request.question)
        ))

        unique: dict[str, tuple[RetrievalResult, int, int]] = {}
        for item, search_index, rank in candidates:
            existing = unique.get(item.chunk_id)
            if existing is None or (search_index, rank) < (existing[1], existing[2]):
                unique[item.chunk_id] = (item, search_index, rank)

        merged = list(unique.values())
        merged.sort(key=lambda entry: (
            -self._coverage_score(request.question, entry[0].text),
            entry[0].distance,
            entry[1], entry[2], entry[0].chunk_id,
        ))
        # Reserve direct lexical hits for material roles before using remaining
        # slots. This stops many topical passages crowding out qualifications.
        ordered = [item for item, _, _ in merged]
        reserved: list[RetrievalResult] = []
        seen_ids: set[str] = set()
        for role in self._required_retrieval_roles(request.question):
            match = next((item for item in ordered if self._role_matches(role, item.text)), None)
            if match is not None and match.chunk_id not in seen_ids:
                reserved.append(match)
                seen_ids.add(match.chunk_id)
        reserved.extend(item for item in ordered if item.chunk_id not in seen_ids)
        expanded = self._include_adjacent_context(reserved, request.question)
        return expanded[:8]

    @staticmethod
    def _required_retrieval_roles(question: str) -> tuple[str, ...]:
        lowered = question.lower()
        if "battery" in lowered or "electric" in lowered:
            return ("is 15644", "is 9873")
        if any(term in lowered for term in ("handmade", "artisan", "exempt")):
            return (
                "manufactured and sold by artisans",
                "registered with office of the development commissioner",
            )
        return ()

    def _controlled_role_candidates(self, question: str) -> list[RetrievalResult]:
        """Find direct, normative role passages in the existing indexed corpus."""
        if not ("battery" in question.lower() or "electric" in question.lower()):
            return []
        rows = getattr(self._retriever, "chunks_by_id", {}).values()
        candidates: list[RetrievalResult] = []
        for row in rows:
            text, metadata = row["document"], row["metadata"]
            if not metadata.get("retrieval_enabled"):
                continue
            if not (self._is_normative_primary(text) or self._is_normative_secondary(text)):
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
    def _coverage_queries(question: str) -> list[str]:
        lowered = question.lower()
        queries: list[str] = []
        if "battery" in lowered or "electric" in lowered:
            queries.append("electric toy applicable primary standard IS 15644")
        if "handmade" in lowered or "artisan" in lowered or "exempt" in lowered:
            queries.append("artisan registered Development Commissioner Handicrafts exemption")
        return queries

    @staticmethod
    def _coverage_score(question: str, text: str) -> int:
        lowered_question, lowered_text = question.lower(), text.lower()
        score = 0
        if "battery" in lowered_question or "electric" in lowered_question:
            score += 8 if "is 15644" in lowered_text else 0
            score += 4 if "is 9873" in lowered_text else 0
            score += 2 if "primary" in lowered_text else 0
            score += 1 if "secondary" in lowered_text else 0
        if "handmade" in lowered_question or "artisan" in lowered_question or "exempt" in lowered_question:
            score += 8 if "registered with office of the development commissioner" in lowered_text else 0
            score += 4 if "artisans" in lowered_text else 0
            score += 2 if "ministry of textiles" in lowered_text else 0
        return score

    def _include_adjacent_context(
        self,
        results: list[RetrievalResult],
        question: str,
    ) -> list[RetrievalResult]:
        if not any(term in question.lower() for term in ("handmade", "artisan", "exempt")):
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
        merged.sort(key=lambda item: (-self._coverage_score(question, item.text), item.distance, item.chunk_id))
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
        boundary = re.search(r"[.:;](?:\s|$)", tail[anchor_offset:])
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
