"""Typed request and response contracts for the retrieval API."""

from typing import Annotated

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
