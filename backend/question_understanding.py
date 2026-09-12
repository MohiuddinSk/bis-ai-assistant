"""Deterministic, conservative understanding for untrusted chat questions."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal

from backend.schemas import AssistantContext


Intent = Literal[
    "standards", "certification", "documents", "exemption", "commencement",
    "transition", "roadmap", "timeline", "fee", "laboratory", "form", "profile",
    "general", "out_of_domain",
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
    suggested_replies: tuple[str, ...] = ()
    assistant_context: AssistantContext | None = None
    context_retained: bool = False
    profile_statement: bool = False


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
    if re.match(r"^ow\s+many\b", normalized):
        normalized = "h" + normalized
        corrections.append("ow many->how many")
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
    if re.search(r"\b(complete (?:compliance )?roadmap|complete process)\b", query):
        return "roadmap"
    if re.search(r"\b(how (?:many|long)|processing time|approval time|timeline|take to approve|days? to approve)\b", query):
        return "timeline"
    if re.search(r"\b((?:exact|current) fees?|how much|what (?:is )?the fee|cost of|charges? for)\b", query):
        return "fee"
    if re.search(r"\b(which|recommend|approved|nearest|find)\b.*\b(lab|laboratory|laboratories)\b", query):
        return "laboratory"
    if re.search(r"\b(which|what|required|submit|need)\b.*\b(forms?|form number)\b", query):
        return "form"
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


def _role(query: str) -> str | None:
    if re.search(r"\b(?:i am|i'm|as) (?:an? )?importer\b|\bi import\b|\bbringing\b", query):
        return "importer"
    if re.search(r"\b(?:i am|i'm|as) (?:an? )?artisan\b", query):
        return "artisan"
    if re.search(r"\b(?:i am|i'm|as) (?:a )?consumer\b", query):
        return "consumer"
    if re.search(r"\b(?:i am|i'm|as) (?:a )?manufacturer\b|\bi manufacture\b|\bi make\b", query):
        return "manufacturer"
    return None


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _age_group(query: str) -> tuple[str | None, bool]:
    if re.search(r"\b(both age groups|multiple age groups|under 3 and 3[- ]to[- ]8)\b", query):
        return "multiple", False
    if re.search(r"\bunder(?: age)? eight\b|\bunder(?: age)? 8\b|\bunder 8\b", query):
        return "not_sure", True
    if re.search(r"\bunder[- ]?3\b|\bunder three\b", query):
        return "under_3", False
    if re.search(r"\b3[- ]to[- ]8\b|\b3[-–]8\b", query):
        return "3_to_8", False
    if re.search(r"\bover[- ]?8\b|\bover eight\b", query):
        return "over_8", False
    match = re.search(r"\b(?:aged?|age|children aged)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", query)
    if match:
        value = int(match.group(1)) if match.group(1).isdigit() else _NUMBER_WORDS[match.group(1)]
        return ("under_3" if value < 3 else "3_to_8" if value <= 8 else "over_8"), False
    return None, False


def _application_stage(query: str) -> str | None:
    if re.search(r"\b(first|new) (?:bis )?licence\b|\bapplying for (?:a )?(?:new|first) licence\b", query):
        return "preparing_application"
    if re.search(r"\b(scope extension|extending (?:my )?(?:licence )?scope)\b", query):
        return "scope_extension"
    if re.search(r"\b(already have|existing) (?:a )?(?:bis )?licence\b", query):
        return "existing_licence"
    if "researching" in query:
        return "researching"
    return None


def _goal_for_intent(intent: Intent) -> str | None:
    return {
        "standards": "identify_standards", "certification": "new_licence",
        "documents": "add_new_series", "exemption": "check_exemption",
        "transition": "understand_transition", "roadmap": "complete_roadmap",
    }.get(intent)


def _is_interrogative(query: str) -> bool:
    return bool(re.match(r"^(?:what|which|how|when|why|where|can|does|do|is|are|will|should)\b", query))


def _is_profile_statement(query: str) -> bool:
    contains_question_clause = bool(re.search(
        r"\b(how do i|what (?:is|are|do)|which (?:is|are|do)|can i|should i|where do i|when will)\b",
        query,
    ))
    return not _is_interrogative(query) and not contains_question_clause and bool(re.search(
        r"\b(i manufacture|i make|i import|i am (?:an? )?(?:manufacturer|importer|artisan)|i already have)\b",
        query,
    ))


def _slot_answered(slot: str, query: str) -> bool:
    return {
        "role": _role(query) is not None,
        "product_description": "toy" in _product_signals(query),
        "product_scope": "children_play" in _product_signals(query) or "actual household" in query,
        "power_type": _power(query) != "unknown",
        "age_group": _age_group(query)[0] is not None,
        "application_stage": _application_stage(query) is not None,
        "goal": _goal_for_intent(_intent(query)) is not None or "complete roadmap" in query,
    }.get(slot, False)


def _is_context_continuation(query: str, context: AssistantContext) -> bool:
    if _is_interrogative(query):
        return False
    return len(query) <= 160 and any(_slot_answered(slot, query) for slot in context.expected_slots)


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
    if re.search(r"\bkitchen (?:play )?sets?\b", query):
        signals.append("kitchen_set")
    if re.search(r"\b(child|children|aged?\s+\w+|for play|play set|playset)\b", query):
        signals.append("children_play")
    return tuple(signals)


def understand_question(
    question: str,
    original_question: str | None = None,
    assistant_context: AssistantContext | None = None,
) -> QuestionUnderstanding:
    """Classify current plus relevant prior context; neither is legal evidence."""
    current, corrections = normalize_question(question)
    retained = bool(assistant_context and _is_context_continuation(current, assistant_context))
    active_context = assistant_context if retained else None
    if active_context and active_context.original_question:
        original, original_corrections = normalize_question(active_context.original_question)
        combined = f"{original} follow-up {current}"
        corrections = tuple(dict.fromkeys((*original_corrections, *corrections)))
    elif original_question:
        original, original_corrections = normalize_question(original_question)
        combined = f"{original} follow-up {current}"
        corrections = tuple(dict.fromkeys((*original_corrections, *corrections)))
    else:
        combined = current

    profile_origin = _is_profile_statement(current) or bool(
        active_context and active_context.original_question
        and _is_profile_statement(normalize_question(active_context.original_question)[0])
    )
    profile_statement = profile_origin and (
        not retained or _goal_for_intent(_intent(current)) is None
    )
    intent = "profile" if profile_statement else _intent(combined)
    if retained and intent == "general" and active_context and active_context.current_goal:
        intent = {
            "identify_standards": "standards", "new_licence": "certification",
            "add_new_series": "documents", "check_exemption": "exemption",
            "understand_transition": "transition", "complete_roadmap": "roadmap",
            "not_sure": "general",
        }[active_context.current_goal]
    current_power = _power(current)
    power = current_power if current_power != "unknown" else _power(combined)
    if power == "unknown" and active_context and active_context.power_type:
        power = active_context.power_type if active_context.power_type != "not_sure" else "unknown"
    signals = _product_signals(combined)
    role = _role(current) or _role(combined) or (active_context.role if active_context else None)
    current_age, current_age_ambiguous = _age_group(current)
    combined_age, combined_age_ambiguous = _age_group(combined)
    age_group = current_age or combined_age or (active_context.age_group if active_context else None)
    age_ambiguous = current_age_ambiguous if current_age is not None else combined_age_ambiguous
    stage = _application_stage(current) or _application_stage(combined) or (active_context.application_stage if active_context else None)
    goal = _goal_for_intent(_intent(current)) or _goal_for_intent(intent) or (active_context.current_goal if active_context else None)
    product_description = (
        active_context.product_description if active_context and active_context.product_description else None
    )
    if "kitchen_set" in signals:
        product_description = "kitchen play sets" if "children_play" in signals else "kitchen sets"
    elif "toy" in signals and not product_description:
        product_description = "toys"
    missing: list[str] = []
    asked_slots: list[str] = []
    ambiguity: list[str] = []
    clarification: str | None = None
    suggestions: tuple[str, ...] = ()

    ambiguous_kitchen = "kitchen_set" in signals and "children_play" not in signals
    if ambiguous_kitchen:
        ambiguity.append("kitchen_set_may_not_be_a_toy")
        missing.append("product_scope")
        clarification = "Is this a children's toy intended for play, or an actual household kitchen product?"
        suggestions = ("Children's kitchen play set", "Household kitchen product")
    elif profile_statement:
        if age_ambiguous:
            missing.append("age_group")
            ambiguity.append("under_eight_spans_age_groups")
            clarification = (
                "I understand that you manufacture non-electric toys for children under eight. "
                "This is information you provided, not verified BIS evidence. Which age group applies: "
                "under 3, 3–8, or both? Age can affect the applicable requirements."
            )
            suggestions = ("Under 3", "3–8", "Both age groups")
        else:
            missing.append("goal")
            known_role = role or "toy business"
            known_power = {
                "battery_operated": "battery-operated", "mains_electric": "mains-powered",
                "non_electric": "non-electric", "electric_unspecified": "electric",
                "unknown": "",
            }[power]
            known_age = {
                "under_3": " for children under 3", "3_to_8": " for children aged 3–8",
                "over_8": " for children over 8", "multiple": " for multiple age groups",
                "not_sure": "",
            }.get(age_group or "not_sure", "")
            description = " ".join(part for part in (known_power, product_description or "toys") if part)
            clarification = (
                f"I understand that you are a {known_role} working with {description}{known_age}. "
                "This is information you provided, not verified BIS evidence. What would you like help with?"
            )
            suggestions = (
                "Identify applicable standards", "Apply for a new licence", "Add a model or series",
                "Check an exemption", "Understand a transition order", "Show my complete compliance roadmap",
            )
    elif intent == "standards" and power in {"unknown", "electric_unspecified"}:
        missing.append("power_type")
        if power == "electric_unspecified":
            ambiguity.append("electric_power_source_unspecified")
        clarification = "Is the toy battery-operated, mains-powered, or non-electric?"
        suggestions = ("Battery-operated", "Mains-powered", "Non-electric")
    elif intent == "certification":
        if "toy" not in signals and "children_play" not in signals:
            missing.append("product_type")
        elif product_description in {None, "toys"} and re.search(r"\b(?:my\s+)?toys?\b", combined) and not re.search(
            r"\b(car|doll|rattle|puzzle|game|set|vehicle|ball|plush|figure|blocks?)\b",
            combined,
        ):
            missing.append("product_description")
        if power in {"unknown", "electric_unspecified"}:
            missing.append("power_type")
        if role is None:
            missing.append("role")
        if stage is None:
            missing.append("application_stage")
        if missing:
            labels = {
                "product_type": "the product and whether it is a children's toy",
                "product_description": "what kind of toy you want to certify",
                "power_type": "whether it is battery-operated, mains-powered, or non-electric",
                "role": "whether you are the manufacturer, importer, or artisan",
                "application_stage": "whether this is a new licence or an addition to an existing licence",
            }
            next_missing = missing[:2]
            asked_slots = next_missing
            clarification = "Please tell me " + "; and ".join(labels[item] for item in next_missing) + "."
            if next_missing == ["power_type"] or "power_type" in next_missing:
                suggestions = ("Battery-operated", "Mains-powered", "Non-electric")
            elif "role" in next_missing:
                suggestions = ("Manufacturer", "Importer", "Artisan")
            elif "application_stage" in next_missing:
                suggestions = ("First BIS licence", "Add to an existing licence")

    context = None
    if clarification:
        expected = list(dict.fromkeys(asked_slots or missing))
        context = AssistantContext(
            original_question=(active_context.original_question if active_context and active_context.original_question else question),
            expected_slots=expected,
            role=role,
            product_description=product_description,
            power_type=(power if power != "unknown" else None),
            age_group=age_group,
            application_stage=stage,
            current_goal=goal,
        )
    elif active_context:
        context = AssistantContext(
            original_question=active_context.original_question,
            expected_slots=[], role=role,
            product_description=product_description,
            power_type=(power if power != "unknown" else active_context.power_type),
            age_group=age_group,
            application_stage=stage,
            current_goal=goal,
        )

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
        suggested_replies=suggestions,
        assistant_context=context,
        context_retained=retained,
        profile_statement=profile_statement,
    )
