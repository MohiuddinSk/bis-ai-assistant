"""Deterministic, conservative understanding for untrusted chat questions."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal


Intent = Literal[
    "standards", "certification", "documents", "exemption", "commencement",
    "transition", "general", "out_of_domain",
]
PowerClassification = Literal[
    "battery_operated", "mains_electric", "non_electric",
    "electric_unspecified", "unknown",
]


@dataclass(frozen=True)
class QuestionUnderstanding:
    normalized_query: str
    intent: Intent
    product_signals: tuple[str, ...]
    power: PowerClassification
    missing_required_details: tuple[str, ...]
    ambiguity_reasons: tuple[str, ...]
    spelling_corrections: tuple[str, ...]
    clarification_required: bool
    clarification_question: str | None


_TOKEN_CORRECTIONS = {
    "standrad": "standard",
    "standrads": "standards",
    "certfy": "certify",
    "certifiy": "certify",
    "certifed": "certified",
    "eletric": "electric",
    "eletrical": "electrical",
    "liecence": "licence",
    "lisence": "licence",
    "license": "licence",
    "toies": "toys",
    "toyes": "toys",
}


def normalize_question(value: str) -> tuple[str, tuple[str, ...]]:
    """Normalize layout and only high-confidence, auditable domain typos."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-")
    normalized = re.sub(r"[^\w\s./():+-]", " ", normalized.lower(), flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    corrections: list[str] = []
    for wrong, right in _TOKEN_CORRECTIONS.items():
        pattern = rf"\b{re.escape(wrong)}\b"
        if re.search(pattern, normalized):
            normalized = re.sub(pattern, right, normalized)
            corrections.append(f"{wrong}->{right}")
    if re.search(r"\bmt\s+toys?\b", normalized):
        normalized = re.sub(r"\bmt(?=\s+toys?\b)", "my", normalized)
        corrections.append("mt->my")
    normalized = re.sub(r"\bnon\s*-?\s*electrical\b", "non-electric", normalized)
    normalized = re.sub(r"\bnon\s*-?\s*electric\b", "non-electric", normalized)
    normalized = re.sub(r"\bbattery\s*-?\s*(?:operated|powered)\b", "battery-operated", normalized)
    normalized = re.sub(r"\bmains\s*-?\s*powered\b", "mains-powered", normalized)
    normalized = re.sub(r"\bac\s*-?\s*powered\b", "ac-powered", normalized)
    return normalized, tuple(corrections)


def _intent(query: str) -> Intent:
    # What the user asks takes precedence over product/power mentions.
    if re.search(r"\b(industrial inverter|solar inverter|refrigerator|washing machine|actual household)\b", query):
        return "out_of_domain"
    if re.search(r"\btransition\b", query):
        return "transition"
    if re.search(r"\b(commencement|effective date|come into force|came into force)\b", query):
        return "commencement"
    if re.search(r"\b(exempt|exemption|artisan|handmade)\b", query):
        return "exemption"
    if (
        re.search(r"\b(add|addition|include|inclusion|extend|extension|scope)\b", query)
        and re.search(r"\b(series|model|variety|licence)\b", query)
    ):
        return "documents"
    if (
        re.search(r"\b(certify|certified|certification|licence|application)\b", query)
        or re.search(r"\bapply(?:ing)?\s+for\s+(?:a\s+)?(?:licence|certification)\b", query)
    ):
        return "certification"
    if re.search(r"\bstandards?\b", query):
        return "standards"
    return "general"


def _power(query: str) -> PowerClassification:
    if re.search(
        r"\b(non-electric|manual toy|manual(?:ly)?[- ](?:powered|operated)|no batter(?:y|ies)|without (?:an? )?electric(?:al)? power)\b",
        query,
    ):
        return "non_electric"
    if re.search(r"\bbattery-operated\b", query):
        return "battery_operated"
    if re.search(r"\b(mains-powered|plug[ -]?in|ac-powered)\b", query):
        return "mains_electric"
    if re.search(r"\b(electric|electrical)\b", query):
        return "electric_unspecified"
    return "unknown"


def _product_signals(query: str) -> tuple[str, ...]:
    signals: list[str] = []
    if re.search(r"\b(toy|toys|play set|playset)\b", query):
        signals.append("toy")
    if "kitchen set" in query:
        signals.append("kitchen_set")
    if re.search(r"\b(child|children|aged?\s+\w+|for play|play set|playset)\b", query):
        signals.append("children_play")
    return tuple(signals)


def understand_question(question: str, original_question: str | None = None) -> QuestionUnderstanding:
    """Classify current plus optional prior text; neither is treated as evidence."""
    current, corrections = normalize_question(question)
    if original_question:
        original, original_corrections = normalize_question(original_question)
        combined = f"{original} follow-up {current}"
        corrections = tuple(dict.fromkeys((*original_corrections, *corrections)))
    else:
        combined = current

    intent = _intent(combined)
    power = _power(combined)
    signals = _product_signals(combined)
    missing: list[str] = []
    ambiguity: list[str] = []
    clarification: str | None = None

    ambiguous_kitchen = "kitchen_set" in signals and "children_play" not in signals
    if ambiguous_kitchen:
        ambiguity.append("kitchen_set_may_not_be_a_toy")
        missing.append("product_scope")
        clarification = "Is this a children's toy intended for play, or an actual household kitchen product?"
    elif intent == "standards" and power in {"unknown", "electric_unspecified"}:
        missing.append("power_type")
        if power == "electric_unspecified":
            ambiguity.append("electric_power_source_unspecified")
        clarification = "Is the toy battery-operated, mains-powered, or non-electric?"
    elif intent == "certification":
        if "toy" not in signals and "children_play" not in signals:
            missing.append("product_type")
        elif re.search(r"\b(?:my\s+)?toys?\b", combined) and not re.search(
            r"\b(car|doll|rattle|puzzle|game|set|vehicle|ball|plush|figure|blocks?)\b",
            combined,
        ):
            missing.append("product_description")
        if power in {"unknown", "electric_unspecified"}:
            missing.append("power_type")
        if not re.search(r"\b(manufacturer|importer|artisan|consumer)\b", combined):
            missing.append("applicant_role")
        if not re.search(r"\b(new licence|first licence|existing licence|scope extension|adding (?:a )?model)\b", combined):
            missing.append("application_stage")
        if missing:
            labels = {
                "product_type": "the product and whether it is a children's toy",
                "product_description": "what kind of toy you want to certify",
                "power_type": "whether it is battery-operated, mains-powered, or non-electric",
                "applicant_role": "whether you are the manufacturer, importer, or artisan",
                "application_stage": "whether this is a new licence or an addition to an existing licence",
            }
            clarification = "Please tell me " + "; ".join(labels[item] for item in missing) + "."

    return QuestionUnderstanding(
        normalized_query=combined,
        intent=intent,
        product_signals=signals,
        power=power,
        missing_required_details=tuple(missing),
        ambiguity_reasons=tuple(ambiguity),
        spelling_corrections=corrections,
        clarification_required=clarification is not None,
        clarification_question=clarification,
    )
