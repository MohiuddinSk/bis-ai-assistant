"""Typed request and response contracts for the retrieval API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


Question = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=1000),
]


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    top_k: int = Field(default=5, ge=1, le=10)
    include_guidance: bool = False


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    top_k: int = Field(default=8, ge=1, le=8)
    include_guidance: bool = False
    audience: Literal["general", "manufacturer", "consumer"] = "general"
    clarification_context: "ClarificationContext | None" = None
    assistant_context: "AssistantContext | None" = None


class ClarificationContext(BaseModel):
    """Bounded, untrusted context for resolving one prior clarification."""

    model_config = ConfigDict(extra="forbid")
    original_question: Question


ClarificationSlot = Literal[
    "role", "product_description", "product_scope", "power_type", "age_group",
    "application_stage", "goal",
]


class AssistantContext(BaseModel):
    """Frontend-held, bounded user context; never a source of BIS facts."""

    model_config = ConfigDict(extra="forbid")
    original_question: Question | None = None
    expected_slots: list[ClarificationSlot] = Field(default_factory=list, max_length=7)
    role: Literal["manufacturer", "importer", "artisan", "consumer", "not_sure"] | None = None
    product_description: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=300)] = None
    power_type: Literal[
        "battery_operated", "mains_electric", "non_electric", "electric_unspecified", "not_sure"
    ] | None = None
    age_group: Literal["under_3", "3_to_8", "over_8", "multiple", "not_sure"] | None = None
    application_stage: Literal[
        "researching", "preparing_application", "existing_licence", "scope_extension", "not_sure"
    ] | None = None
    current_goal: Literal[
        "identify_standards", "new_licence", "add_new_series", "check_exemption",
        "understand_transition", "complete_roadmap", "not_sure",
    ] | None = None


class ComplianceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["manufacturer", "importer", "artisan", "consumer", "not_sure"]
    product_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)]
    power_type: Literal["battery_operated", "mains_electric", "non_electric", "not_sure"]
    intended_age_group: Literal["under_3", "3_to_8", "over_8", "multiple", "not_sure"]
    goal: Literal["identify_standards", "new_licence", "add_new_series", "check_exemption", "understand_transition", "complete_roadmap", "not_sure"]
    application_stage: Literal["researching", "preparing_application", "existing_licence", "scope_extension", "not_sure"]
    additional_context: Annotated[str | None, StringConstraints(max_length=500)] = None


class RetrievalResult(BaseModel):
    rank: int
    chunk_id: str
    text: str
    source_id: str | None = None
    source_filename: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_type: str | None = None
    distance: float
    similarity: float


class RetrieveResponse(BaseModel):
    question: str
    result_count: int
    results: list[RetrievalResult]


class HealthResponse(BaseModel):
    status: str
    service: str
    collection_count: int | None
    detail: str | None = None


class GeneratedCitation(BaseModel):
    """A model-selected trusted ID paired with its verbatim supporting quote."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    supporting_quote: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]


class GenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    citations: list[GeneratedCitation] = Field(max_length=8)
    insufficient_evidence: bool


class ChatCitation(BaseModel):
    citation_id: str
    source_filename: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_id: str
    excerpt: str


class AnswerSection(BaseModel):
    """Backend-composed, citation-bound guidance for a safe chat presentation."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["direct_answer", "explanation", "next_steps", "important", "clarification"]
    title: str
    content: str | None = None
    items: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list, max_length=8)


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    insufficient_evidence: bool
    evidence_count: int
    citations: list[ChatCitation]
    model: str | None
    generation_mode: str
    disclaimer: str
    answer_sections: list[AnswerSection] = Field(default_factory=list)
    needs_clarification: bool = False
    suggested_replies: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = Field(default_factory=list, max_length=8)
    assistant_context: AssistantContext | None = None


class ComplianceGuideResponse(BaseModel):
    profile: ComplianceProfile
    guidance: ChatResponse
