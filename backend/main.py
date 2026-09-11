"""FastAPI application for local BIS Toys evidence retrieval."""

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
import logging
from threading import Lock
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.schemas import HealthResponse, RetrieveRequest, RetrieveResponse
from backend.service import RetrievalService
from backend.settings import (
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    ALLOWED_ORIGINS,
    SERVICE_NAME,
)
from retrieval.search import Retriever


logger = logging.getLogger(__name__)
RetrieverFactory = Callable[[], Any]


def create_app(retriever_factory: RetrieverFactory = Retriever) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> Iterator[None]:
        logger.info("Starting retrieval service")
        application.state.retriever = None
        application.state.retrieval_lock = Lock()
        application.state.collection_count = None
        application.state.startup_error = None

        try:
            retriever = retriever_factory()
            collection_count = int(retriever.collection.count())
            application.state.retriever = retriever
            application.state.collection_count = collection_count
            logger.info(
                "Retriever initialized successfully; collection_count=%d",
                collection_count,
            )
        except Exception:
            application.state.startup_error = "Retrieval service is unavailable."
            logger.exception("Retriever initialization failed")

        yield
        logger.info("Retrieval service stopped")

    application = FastAPI(
        title="BIS Toys Retrieval API",
        description=(
            "Retrieves evidence candidates from the local BIS Toys corpus. "
            "Similarity is retrieval closeness, not legal certainty, factual "
            "confidence, or the probability that an answer is correct."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=list(ALLOWED_METHODS),
        allow_headers=list(ALLOWED_HEADERS),
    )

    @application.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
    )
    def health(request: Request) -> HealthResponse | JSONResponse:
        if request.app.state.retriever is None:
            response = HealthResponse(
                status="degraded",
                service=SERVICE_NAME,
                collection_count=None,
                detail="Retrieval service is unavailable.",
            )
            return JSONResponse(status_code=503, content=response.model_dump())

        return HealthResponse(
            status="ready",
            service=SERVICE_NAME,
            collection_count=request.app.state.collection_count,
        )

    @application.post(
        "/api/retrieve",
        response_model=RetrieveResponse,
        responses={503: {"description": "Retrieval service unavailable"}},
    )
    def retrieve(
        payload: RetrieveRequest,
        request: Request,
    ) -> RetrieveResponse:
        retriever = request.app.state.retriever
        if retriever is None:
            raise HTTPException(
                status_code=503,
                detail="Retrieval service is unavailable.",
            )

        started = time.perf_counter()
        try:
            with request.app.state.retrieval_lock:
                response = RetrievalService(retriever).retrieve(payload)
        except Exception:
            logger.exception("Retrieval request failed")
            raise HTTPException(
                status_code=500,
                detail="Retrieval request failed.",
            ) from None

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Retrieval request completed; duration_ms=%.2f result_count=%d",
            elapsed_ms,
            response.result_count,
        )
        return response

    return application


app = create_app()
