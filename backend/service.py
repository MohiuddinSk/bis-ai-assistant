"""Mapping layer between the existing Retriever and the public API."""

from collections.abc import Mapping, Sequence
import math
from typing import Any

from backend.retrieval_provider import RetrievalHit, RetrieverProtocol
from backend.schemas import RetrieveRequest, RetrieveResponse, RetrievalResult


class RetrievalService:
    def __init__(self, retriever: RetrieverProtocol):
        self._retriever = retriever

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        hits = self._retriever.search(
            question=request.question,
            k=request.top_k,
            include_guidance=request.include_guidance,
        )

        if not isinstance(hits, Sequence) or isinstance(hits, (str, bytes)):
            raise ValueError("Retriever returned invalid results")
        if not hits:
            return RetrieveResponse(
                question=request.question,
                result_count=0,
                results=[],
            )

        results: list[RetrievalResult] = []
        for rank, hit in enumerate(hits, start=1):
            if not isinstance(hit, RetrievalHit):
                raise ValueError("Retriever returned invalid results")
            chunk_id = hit.chunk_id
            document = hit.text
            metadata = hit.metadata
            distance_value = hit.distance
            if not isinstance(chunk_id, str) or not chunk_id or not isinstance(document, str) or not document:
                raise ValueError("Retriever returned invalid results")
            if not isinstance(metadata, Mapping):
                raise ValueError("Retriever returned invalid results")
            if not isinstance(distance_value, (int, float)) or isinstance(distance_value, bool):
                raise ValueError("Retriever returned invalid results")

            distance = float(distance_value)
            if not math.isfinite(distance):
                raise ValueError("Retriever returned invalid results")
            for name in ("source_id", "source_filename", "chunk_type"):
                if metadata.get(name) is not None and not isinstance(metadata.get(name), str):
                    raise ValueError("Retriever returned invalid results")
            for name in ("page_start", "page_end"):
                if metadata.get(name) is not None and (not isinstance(metadata.get(name), int) or isinstance(metadata.get(name), bool) or metadata.get(name) < 1):
                    raise ValueError("Retriever returned invalid results")
            if metadata.get("page_start") is not None and metadata.get("page_end") is not None and metadata["page_end"] < metadata["page_start"]:
                raise ValueError("Retriever returned invalid results")
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
