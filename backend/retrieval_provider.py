"""Provider-neutral retrieval contracts and the local Chroma adapter."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from retrieval.search import Retriever


@dataclass(frozen=True)
class RetrievalHit:
    """One ordered retrieval result, independent of provider wire formats."""

    chunk_id: str
    text: str
    metadata: Mapping[str, Any]
    distance: float


class RetrieverProtocol(Protocol):
    def search(
        self,
        question: str,
        k: int = 5,
        include_guidance: bool = False,
    ) -> Sequence[RetrievalHit]: ...

    def count(self) -> int: ...


class LocalChromaRetriever:
    """Normalize the existing local Chroma retriever without changing its logic."""

    def __init__(self, retriever: Retriever | None = None):
        self._retriever = retriever or Retriever()

    @staticmethod
    def _row(raw: Mapping[str, Any], name: str) -> list[Any]:
        value = raw.get(name)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
            raise ValueError("Local retrieval provider returned invalid results")
        return value[0]

    @classmethod
    def _hits(cls, raw: object) -> list[RetrievalHit]:
        if not isinstance(raw, Mapping):
            raise ValueError("Local retrieval provider returned invalid results")
        ids = cls._row(raw, "ids")
        documents = cls._row(raw, "documents")
        metadatas = cls._row(raw, "metadatas")
        distances = cls._row(raw, "distances")
        if not (len(ids) == len(documents) == len(metadatas) == len(distances)):
            raise ValueError("Local retrieval provider returned invalid results")
        hits: list[RetrievalHit] = []
        for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
            if not isinstance(chunk_id, str) or not isinstance(text, str) or not isinstance(metadata, Mapping):
                raise ValueError("Local retrieval provider returned invalid results")
            hits.append(RetrievalHit(chunk_id=chunk_id, text=text, metadata=metadata, distance=distance))
        return hits

    def count(self) -> int:
        return self._retriever.collection.count()

    def search(self, question: str, k: int = 5, include_guidance: bool = False) -> Sequence[RetrievalHit]:
        return self._hits(self._retriever.search(question, k=k, include_guidance=include_guidance))

    def adjacent_chunks(self, chunk_id: str, source_id: str | None, page_start: int | None) -> Sequence[RetrievalHit]:
        raw = self._retriever.adjacent_chunks(chunk_id, source_id, page_start)
        if not isinstance(raw, list):
            raise ValueError("Local retrieval provider returned invalid results")
        hits: list[RetrievalHit] = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise ValueError("Local retrieval provider returned invalid results")
            metadata = {
                "source_id": item.get("source_id"),
                "source_filename": item.get("source_filename"),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
                "chunk_type": item.get("chunk_type"),
            }
            chunk = item.get("chunk_id")
            text = item.get("text")
            if not isinstance(chunk, str) or not isinstance(text, str):
                raise ValueError("Local retrieval provider returned invalid results")
            hits.append(RetrievalHit(chunk_id=chunk, text=text, metadata=metadata, distance=0.0))
        return hits
