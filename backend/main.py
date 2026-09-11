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

from backend.chat_service import ChatRetrievalError, ChatService
from backend.generation import (
    GenerationProvider,
    GroqGenerator,
    MalformedGenerationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from backend.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from backend.service import RetrievalService
from backend.settings import (
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    ALLOWED_ORIGINS,
    DEFAULT_GROQ_MODEL,
    SERVICE_NAME,
)
from retrieval.search import Retriever


logger = logging.getLogger(__name__)
RetrieverFactory = Callable[[], Any]
GeneratorFactory = Callable[[], GenerationProvider]


def create_app(
    retriever_factory: RetrieverFactory = Retriever,
    generator_factory: GeneratorFactory = GroqGenerator.from_environment,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> Iterator[None]:
        logger.info("Starting retrieval service")
        application.state.retriever = None
        application.state.retrieval_lock = Lock()
        application.state.generation_lock = Lock()
        application.state.collection_count = None
        application.state.startup_error = None
        application.state.generator = None
        application.state.generator_error = None
        application.state.chat_model = DEFAULT_GROQ_MODEL

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

        try:
            generator = generator_factory()
            application.state.generator = generator
            application.state.chat_model = generator.model
            logger.info("Chat generator initialized; model=%s", generator.model)
        except Exception as exc:
            application.state.generator_error = "Chat generation is unavailable."
            logger.info(
                "Chat generator unavailable; error_type=%s",
                type(exc).__name__,
            )

        yield
        logger.info("Retrieval service stopped")

    application = FastAPI(
        title="BIS Toys Retrieval and Grounded Chat API",
        description=(
            "Retrieves evidence candidates and produces backend-cited grounded answers. "
            "Similarity is retrieval closeness, not legal certainty, factual "
            "confidence, or the probability that an answer is correct."
        ),
        version="1.1.0",
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

    @application.post(
        "/api/chat",
        response_model=ChatResponse,
        responses={
            502: {"description": "Generation output invalid"},
            503: {"description": "Retrieval or generation unavailable"},
            504: {"description": "Generation timed out"},
        },
    )
    def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        retriever = request.app.state.retriever
        if retriever is None:
            raise HTTPException(
                status_code=503,
                detail="Retrieval service is unavailable.",
            )

        started = time.perf_counter()
        service = ChatService(
            retriever=retriever,
            generator=request.app.state.generator,
            retrieval_lock=request.app.state.retrieval_lock,
            generation_lock=request.app.state.generation_lock,
            model_name=request.app.state.chat_model,
        )
        try:
            response = service.chat(payload)
        except ChatRetrievalError:
            logger.error("Chat retrieval failed")
            raise HTTPException(
                status_code=500,
                detail="Chat retrieval failed.",
            ) from None
        except ProviderUnavailableError:
            logger.warning("Chat generation unavailable")
            raise HTTPException(
                status_code=503,
                detail="Chat generation is unavailable.",
            ) from None
        except ProviderTimeoutError:
            logger.warning("Chat generation timed out")
            raise HTTPException(
                status_code=504,
                detail="Chat generation timed out.",
            ) from None
        except ProviderRateLimitError as exc:
            logger.warning("Chat generation rate limited")
            headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
            raise HTTPException(
                status_code=503,
                detail="Chat generation is temporarily unavailable.",
                headers=headers,
            ) from None
        except MalformedGenerationError:
            logger.error("Chat generation returned invalid structured output")
            raise HTTPException(
                status_code=502,
                detail="Chat generation returned invalid output.",
            ) from None
        except ProviderResponseError:
            logger.error("Chat generation provider request failed")
            raise HTTPException(
                status_code=502,
                detail="Chat generation failed.",
            ) from None
        except Exception as exc:
            logger.error(
                "Unexpected chat failure; error_type=%s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="Chat request failed.",
            ) from None

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Chat request completed; duration_ms=%.2f evidence_count=%d citation_count=%d grounded=%s",
            elapsed_ms,
            response.evidence_count,
            len(response.citations),
            response.grounded,
        )
        return response

    return application


app = create_app()
