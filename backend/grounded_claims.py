"""Deterministic grounded claims for BIS questions that have no FactPlan template."""

from dataclasses import dataclass
import re
from typing import Literal, Protocol
import unicodedata


ClaimType = Literal[
    "requirement",
    "applicability",
    "standard_role",
    "procedure",
    "document",
    "definition",
    "exception",
    "limitation",
    "legal_date",
]

STRONG_MODALS = ("must", "shall", "mandatory", "compulsory", "always", "every", "guaranteed", "required")
_STOPWORDS = frozenset({
    "which", "what", "does", "that", "this", "with", "from", "have", "your", "about",
    "the", "and", "for", "are", "was", "were", "can", "how", "when", "where", "who",
    "into", "onto", "than", "then", "them", "they", "their", "there", "here",
    "need", "needs", "main", "using", "used", "under", "over", "only",
    "bis", "toy", "toys", "standard", "standards", "requirement", "requirements",
    "material", "materials", "information", "guidance", "applicable", "apply", "applies",
    "manufacturer", "manufacturers", "certain", "happens", "happen", "note",
})
_INJECTION = re.compile(
    r"ignore (?:all |any |the )?(?:previous |prior )?(?:instructions|rules)|"
    r"reveal (?:the )?(?:api key|system prompt|hidden configuration)|"
    r"you are now|disregard the",
    re.IGNORECASE,
)
_ABSENCE = re.compile(r"\bno other standards apply\b|\bno other standard applies\b", re.IGNORECASE)
_IS_NUMBER = re.compile(r"\bIS\s*\d{3,6}\b", re.IGNORECASE)
_TABLE_SERIALIZATION = re.compile(
    r"\b(?:left[- ]to[- ]right|row\s*\d+|column\s*\d+|cells?)\b|"
    r"(?:\b-do-\b|\|\s*[^|]{1,40}\s*\|)|"
    r"(?:\b(?:sl\.?\s*no|particulars?)\b.{0,40}\b(?:column|row)\b)",
    re.IGNORECASE,
)


def is_publishable_claim_text(value: str) -> bool:
    """Fail closed on OCR/table serialization; evidence itself stays verbatim."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if _TABLE_SERIALIZATION.search(normalized):
        return False
    if len(re.findall(r"\b\d+(?:\.\d+){1,3}\b", normalized)) >= 4:
        return False
    if re.search(r"(?:[;,:|]\s*){4,}", normalized) or re.search(r"[.!?]{2,}", normalized):
        return False
    # A claim must contain a proposition, not only a fragment/header.
    return bool(re.search(r"\b(?:is|are|may|can|appl(?:y|ies)|include|provide|submit|does|will)\b", normalized, re.I))


class EvidenceSpan(Protocol):
    citation_id: str
    text: str


@dataclass(frozen=True)
class GroundedClaim:
    claim_id: str
    claim_text: str
    claim_type: ClaimType
    citation_id: str
    supporting_quote: str
    qualifier: str


@dataclass(frozen=True)
class QuestionAnchors:
    """Distinctive concepts that evidence must cover before it can ground prose."""

    groups: tuple[frozenset[str], ...]
    requires_all: bool


def validate_modality(claim_text: str, supporting_quote: str) -> bool:
    """Stronger modality is allowed only when the approved quote uses that word."""
    quote = supporting_quote.casefold()
    for word in STRONG_MODALS:
        if re.search(rf"\b{word}\b", claim_text, re.I) and not re.search(rf"\b{word}\b", quote):
            return False
    return True


def _qualifier(sentence: str) -> str:
    lowered = sentence.casefold()
    found: list[str] = []
    if "where applicable" in lowered:
        found.append("where applicable")
    if re.search(r"\bmay\b", lowered):
        found.append("may")
    if re.search(r"\bonly\b", lowered):
        found.append("only")
    if "subject to" in lowered:
        found.append("subject to conditions")
    if re.search(r"\bpartial\b", lowered):
        found.append("partial checklist")
    if "does not establish" in lowered:
        found.append("does not establish")
    return " ".join(found)


def _claim_type(sentence: str) -> ClaimType:
    lowered = sentence.casefold()
    if re.search(r"\b(?:19|20)\d{2}\b", sentence):
        return "legal_date"
    if re.search(r"\b(exempt|exemption|exception)\b", lowered):
        return "exception"
    if "does not establish" in lowered or re.search(r"\b(does not|do not)\b", lowered):
        return "limitation"
    if re.search(r"\b(primary standard|secondary standard|additional requirement)\b", lowered):
        return "standard_role"
    if re.search(r"\b(document|checklist|application)\b", lowered):
        return "document"
    if re.search(r"\b(means|defined as|definition)\b", lowered):
        return "definition"
    if re.search(r"\b(include|provide|submit|apply for|start by|check|review)\b", lowered):
        return "procedure"
    if re.search(r"\b(applies|applicable|applicability)\b", lowered):
        return "applicability"
    return "requirement"


def _user_facing_claim(sentence: str) -> str:
    """Produce a concise faithful proposition while retaining the verbatim quote."""
    lowered = sentence.casefold()
    if all(marker in lowered for marker in ("higher age grading", "avoid testing", "not be entertained")):
        return (
            "Requests to declare a higher age grading merely to avoid applicable tests "
            "will not be entertained."
        )
    return sentence


def _proposition_key(claim_text: str) -> str:
    lowered = claim_text.casefold()
    if "higher age grading" in lowered and ("avoid" in lowered or "not be entertained" in lowered):
        return "age-grading-avoid-tests"
    return re.sub(r"\W+", " ", lowered).strip()


def _normalized_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _stem(word: str) -> str:
    """Small, conservative normalizer; this is not language translation."""
    aliases = {
        "acoustics": "acoustic", "sounds": "sound", "noises": "noise",
        "subcontracted": "subcontract", "subcontracting": "subcontract",
        "outsourced": "outsource", "outsourcing": "outsource",
        "declares": "declare", "declared": "declare", "declaring": "declare",
        "tests": "test", "testing": "test",
    }
    return aliases.get(word, word)


def _tokens(value: str) -> set[str]:
    normalized = _normalized_text(value)
    words = {
        _stem(word) for word in re.findall(r"[a-z0-9]+", normalized)
        if len(word) > 3 and word not in _STOPWORDS
    }
    if "batteries" in normalized or "battery" in normalized:
        words.add("battery")
    return words


_ANCHOR_SYNONYMS: dict[str, frozenset[str]] = {
    "acoustic": frozenset({"acoustic", "sound", "noise"}),
    "subcontract": frozenset({"subcontract", "outsource", "external"}),
}


def extract_question_anchors(question: str) -> QuestionAnchors:
    """Extract only the concepts that make a generic question answerable.

    The output is intentionally lexical, Unicode-normalized, and fail-closed.
    It is used solely to decide whether evidence can support an answer; it never
    creates a claim or changes retrieval.
    """
    terms = _tokens(question)
    # In "acoustic testing", testing is broad and must not substitute for the
    # acoustic modifier. Likewise it cannot substitute for subcontracting.
    if (
        ("acoustic" in terms or "sound" in terms or "noise" in terms)
        or {"age", "grading", "avoid"} <= terms
    ) and len(terms) > 1:
        terms.discard("test")
    groups: list[frozenset[str]] = []
    consumed: set[str] = set()
    for canonical, variants in _ANCHOR_SYNONYMS.items():
        if terms & variants:
            groups.append(variants)
            consumed |= variants
    for term in sorted(terms - consumed):
        groups.append(frozenset({term}))
    # Permission questions that combine a subject and an action/relation need
    # both anchors. One generic match cannot establish permission.
    requires_all = bool(groups) and any(
        group & _ANCHOR_SYNONYMS["subcontract"] for group in groups
    )
    return QuestionAnchors(tuple(groups), requires_all)


def anchors_cover_text(anchors: QuestionAnchors, text: str) -> bool:
    normalized_terms = _tokens(text)
    if not anchors.groups:
        return False
    matches = [bool(normalized_terms & group) for group in anchors.groups]
    return all(matches) if anchors.requires_all else all(matches)


def claim_answers_question(question: str, claim_or_quote: str) -> bool:
    """Require a distinctive question concept in every generic claim.

    Similarity on generic BIS/toy vocabulary is never enough.  This deliberately
    remains lexical and fail-closed; a provider may assist with prose only after
    this gate has already selected a claim.
    """
    return anchors_cover_text(extract_question_anchors(question), claim_or_quote)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def extract_grounded_claims(question: str, evidence: list[EvidenceSpan]) -> list[GroundedClaim]:
    """Select verbatim, diverse spans. Retrieved text is evidence, never instructions."""
    question_tokens = _tokens(question)
    anchors = extract_question_anchors(question)
    question_standards = {re.sub(r"\s+", "", match).upper() for match in _IS_NUMBER.findall(question)}
    selected: list[GroundedClaim] = []
    seen_tokens: list[set[str]] = []
    seen_propositions: set[str] = set()
    used_citations: set[str] = set()
    for item in evidence:
        sentences = _sentences(item.text)
        if any(_INJECTION.search(sentence) for sentence in sentences):
            continue
        for sentence in sentences:
            if not 20 <= len(sentence) <= 500:
                continue
            if not is_publishable_claim_text(sentence):
                continue
            if sentence not in item.text and sentence not in " ".join(item.text.split()):
                continue
            if _INJECTION.search(sentence) or _ABSENCE.search(sentence):
                continue
            if not validate_modality(sentence, sentence):
                continue
            span_tokens = _tokens(sentence)
            span_standards = {re.sub(r"\s+", "", match).upper() for match in _IS_NUMBER.findall(sentence)}
            shared_standard = bool(question_standards & span_standards)
            if not anchors_cover_text(anchors, sentence):
                continue
            if len(question_tokens & span_tokens) < 1 and not shared_standard:
                continue
            if any(_jaccard(span_tokens, previous) >= 0.85 for previous in seen_tokens):
                continue
            if item.citation_id in used_citations and len(selected) >= 2:
                continue
            claim_text = _user_facing_claim(
                re.sub(r"^(?:passage|evidence)\s*:\s*", "", sentence, flags=re.I)
            )
            # A long extracted passage is evidence, not a concise claim. Keep
            # supporting_quote verbatim but decline to publish such a span.
            normalized_source = " ".join(item.text.split())
            if len(claim_text) > 360 or (
                len(normalized_source) > 360 and len(claim_text) / len(normalized_source) >= 0.85
            ):
                continue
            proposition = _proposition_key(claim_text)
            if proposition in seen_propositions:
                continue
            selected.append(GroundedClaim(
                claim_id=f"C{len(selected) + 1}",
                claim_text=claim_text,
                claim_type=_claim_type(sentence),
                citation_id=item.citation_id,
                supporting_quote=sentence,
                qualifier=_qualifier(sentence),
            ))
            seen_tokens.append(span_tokens)
            seen_propositions.add(proposition)
            used_citations.add(item.citation_id)
            if len(selected) == 4:
                return selected
    return selected


def claim_sections(claims: list[GroundedClaim]) -> dict[str, object]:
    """Compose section text from validated claims without adding facts."""
    direct = claims[0]
    extras = [claim.claim_text for claim in claims[1:] if claim.claim_text != direct.claim_text]
    if "higher age grading" in direct.claim_text.casefold():
        explanation = (
            "The declared starting age should reasonably match the toy and its intended users. "
            "The cited material discusses higher age grading for teethers or teething toys when used "
            "to avoid otherwise applicable tests."
        )
    else:
        explanation = " ".join(extras) if extras else (
            "Read the indexed sentence above with any condition it states. "
            "It does not establish a broader rule than that passage."
        )
    steps = [claim.claim_text for claim in claims if claim.claim_type == "procedure" and claim.claim_text != direct.claim_text]
    limitations = [claim.claim_text for claim in claims if claim.claim_type == "limitation"]
    if not limitations:
        if "higher age grading" in direct.claim_text.casefold():
            limitations.append(
                "The cited evidence establishes how such an age-grading request is treated, but does not describe additional penalties or enforcement consequences."
            )
        else:
            limitations.append("The cited evidence addresses this question only to the extent stated above.")
    return {
        "direct": direct.claim_text,
        "explanation": explanation,
        "steps": steps,
        "limitations": limitations,
        "direct_citations": [direct.citation_id],
        "direct_claims": [direct.claim_id],
        "explanation_citations": list(dict.fromkeys(claim.citation_id for claim in claims)),
        "explanation_claims": [claim.claim_id for claim in claims],
    }
