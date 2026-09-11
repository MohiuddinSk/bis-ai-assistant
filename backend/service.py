"""Mapping layer between the existing Retriever and the public API."""

from collections.abc import Mapping
from typing import Any, Protocol

from backend.schemas import RetrieveRequest, RetrieveResponse, RetrievalResult


class RetrieverProtocol(Protocol):
    def search(
        self,
        question: str,
        k: int = 5,
        include_guidance: bool = False,
    ) -> Mapping[str, Any]: ...


def _first_result_row(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    return []


class RetrievalService:
    def __init__(self, retriever: RetrieverProtocol):
        self._retriever = retriever

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        raw = self._retriever.search(
            question=request.question,
            k=request.top_k,
            include_guidance=request.include_guidance,
        )

        ids = _first_result_row(raw.get("ids"))
        documents = _first_result_row(raw.get("documents"))
        metadatas = _first_result_row(raw.get("metadatas"))
        distances = _first_result_row(raw.get("distances"))

        if not ids and not documents:
            return RetrieveResponse(
                question=request.question,
                result_count=0,
                results=[],
            )

        if not (len(ids) == len(documents) == len(metadatas) == len(distances)):
            raise ValueError("Retriever returned inconsistent result lengths")

        results: list[RetrievalResult] = []
        for rank, (chunk_id, document, metadata, distance_value) in enumerate(
            zip(ids, documents, metadatas, distances),
            start=1,
        ):
            if not isinstance(chunk_id, str) or not isinstance(document, str):
                raise ValueError("Retriever returned an invalid chunk ID or document")
            if not isinstance(metadata, Mapping):
                raise ValueError("Retriever returned invalid metadata")
            if not isinstance(distance_value, (int, float)) or isinstance(distance_value, bool):
                raise ValueError("Retriever returned an invalid distance")

            distance = float(distance_value)
            results.append(
                RetrievalResult(
                    rank=rank,
                    chunk_id=chunk_id,
                    text=document,
                    source_id=metadata.get("source_id"),
                    source_filename=metadata.get("source_filename"),
                    page_start=metadata.get("page_start"),
                    page_end=metadata.get("page_end"),
                    chunk_type=metadata.get("chunk_type"),
                    distance=distance,
                    similarity=1.0 - distance,
                )
            )

        return RetrieveResponse(
            question=request.question,
            result_count=len(results),
            results=results,
        )
