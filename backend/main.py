"""FastAPI application for local BIS Toys evidence retrieval."""

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
import logging
import re
from threading import Lock
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.chat_service import ChatRetrievalError, ChatService, ComplianceRoutingContext
from backend.documents import SourceDocumentRegistry
from backend.question_understanding import QuestionUnderstanding, understand_question
from backend.generation import (
    GenerationProvider,
    MalformedGenerationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from backend.generation_factory import from_environment as generation_provider_from_environment
from backend.schemas import (
    ChatRequest,
    ChatResponse,
    ComplianceGuideResponse,
    ComplianceProfile,
    HealthResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from backend.service import RetrievalService
from backend.settings import (
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    DEFAULT_GROQ_MODEL,
    EXPOSED_HEADERS,
    INSUFFICIENT_EVIDENCE_ANSWER,
    LEGAL_INFORMATION_DISCLAIMER,
    SERVICE_NAME,
    get_allowed_origins,
)
from retrieval.search import Retriever


logger = logging.getLogger(__name__)
RetrieverFactory = Callable[[], Any]
GeneratorFactory = Callable[[], GenerationProvider]
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def select_request_id(value: str | None) -> str:
    """Preserve only safe caller correlation IDs; otherwise issue a UUID4."""
    if value is not None and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


def compliance_query(profile: ComplianceProfile) -> str:
    """Build neutral retrieval context; profile selections are never evidence."""
    context = " ".join((profile.additional_context or "").split())
    product = " ".join(profile.product_description.split())
    goal_fields = {
        "identify_standards": (
            f"product described as: {product}; power selection: {profile.power_type.replace('_', ' ')}; "
            "guidance sought: applicable standards"
        ),
        "new_licence": (
            f"product described as: {product}; role selection: {profile.role.replace('_', ' ')}; "
            f"application stage: {profile.application_stage.replace('_', ' ')}; guidance sought: new licence"
        ),
        "add_new_series": (
            f"product described as: {product}; application stage: {profile.application_stage.replace('_', ' ')}; "
            "guidance sought: addition of a new toy series"
        ),
        "check_exemption": (
            f"product described as: {product}; role selection: {profile.role.replace('_', ' ')}; "
            "guidance sought: exemption qualifications"
        ),
        "understand_transition": (
            f"product described as: {product}; guidance sought: transition-order conditions"
        ),
        "complete_roadmap": (
            f"product described as: {product}; role selection: {profile.role.replace('_', ' ')}; "
            f"power selection: {profile.power_type.replace('_', ' ')}; "
            f"age selection: {profile.intended_age_group.replace('_', ' ')}; "
            f"application stage: {profile.application_stage.replace('_', ' ')}; "
            "guidance sought: complete compliance roadmap"
        ),
        "not_sure": f"product described as: {product}; guidance goal is not specified",
    }
    fields = goal_fields[profile.goal]
    if context:
        fields += f"; additional user context: {context}"
    return f"UNTRUSTED USER CONTEXT (retrieval context only, not legal evidence): {fields}. Establish every compliance claim from indexed evidence."


def enforce_compliance_invariants(
    profile: ComplianceProfile,
    guidance: ChatResponse,
) -> ChatResponse:
    """Fail closed when guidance contradicts the validated wizard route."""
    if guidance.insufficient_evidence:
        return guidance
    profile_is_out_of_domain = (
        understand_question(profile.product_description).intent == "out_of_domain"
    )
    if guidance.needs_clarification:
        safe_clarification = (
            not guidance.grounded
            and guidance.generation_mode == "clarification"
            and not guidance.citations
        )
        if safe_clarification and not profile_is_out_of_domain:
            return guidance

    answer = guidance.answer.lower()
    mismatch = profile_is_out_of_domain
    if not mismatch and profile.goal == "identify_standards":
        if profile.power_type == "non_electric":
            mismatch = "is 15644" in answer or "battery-operated" in answer or "mains-powered" in answer
        elif profile.power_type == "mains_electric":
            mismatch = "battery-operated" in answer
        elif profile.power_type == "battery_operated":
            mismatch = "mains-powered" in answer or "non-electric toy" in answer
        else:
            mismatch = True
    elif not mismatch and profile.goal in {"check_exemption", "add_new_series", "understand_transition"}:
        mismatch = "primary standard is is 15644" in answer or "battery-operated electric toy" in answer
    elif not mismatch and profile.goal == "complete_roadmap":
        if profile.power_type == "non_electric":
            mismatch = "is 15644" in answer or "battery-operated electric toy" in answer
        elif profile.power_type == "mains_electric":
            mismatch = "battery-operated" in answer
        elif profile.power_type == "battery_operated":
            mismatch = "mains-powered" in answer or "non-electric toy" in answer
        else:
            mismatch = True
    elif not mismatch and profile.goal == "not_sure":
        mismatch = True
    elif not mismatch and profile.goal == "new_licence":
        mismatch = "battery-operated electric toy" in answer or "primary standard is is 15644" in answer

    if not mismatch:
        return guidance
    logger.warning(
        "Compliance guidance rejected; reason=PROFILE_ROUTE_MISMATCH goal=%s power_type=%s",
        profile.goal,
        profile.power_type,
    )
    return ChatResponse(
        answer=INSUFFICIENT_EVIDENCE_ANSWER,
        grounded=False,
        insufficient_evidence=True,
        evidence_count=guidance.evidence_count,
        citations=[],
        model=guidance.model,
        generation_mode="abstention",
        disclaimer=LEGAL_INFORMATION_DISCLAIMER,
        answer_sections=[],
    )


def create_app(
    retriever_factory: RetrieverFactory = Retriever,
    generator_factory: GeneratorFactory = generation_provider_from_environment,
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
        allow_origins=list(get_allowed_origins()),
        allow_credentials=False,
        allow_methods=list(ALLOWED_METHODS),
        allow_headers=list(ALLOWED_HEADERS),
        expose_headers=list(EXPOSED_HEADERS),
    )

    @application.middleware("http")
    async def request_correlation_id(request: Request, call_next: Callable[..., Any]) -> Any:
        request_id = select_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    document_registry = SourceDocumentRegistry()

    @application.get(
        "/api/documents/{source_filename}",
        summary="Open a registered source PDF",
        operation_id="get_source_document",
        responses={404: {"description": "Registered source document not found"}},
    )
    @application.get(
        "/api/v1/documents/{source_filename}",
        summary="Open a registered source PDF",
        operation_id="get_source_document_v1",
        responses={404: {"description": "Registered source document not found"}},
    )
    def source_document(source_filename: str) -> FileResponse:
        path = document_registry.resolve(source_filename)
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=path.name,
            content_disposition_type="inline",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache"},
        )

    @application.get(
        "/health",
        response_model=HealthResponse,
        operation_id="get_health",
        responses={503: {"model": HealthResponse}},
    )
    @application.get(
        "/api/v1/health",
        response_model=HealthResponse,
        operation_id="get_health_v1",
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
        operation_id="retrieve_evidence",
        responses={503: {"description": "Retrieval service unavailable"}},
    )
    @application.post(
        "/api/v1/retrieve",
        response_model=RetrieveResponse,
        operation_id="retrieve_evidence_v1",
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

    def run_chat(
        payload: ChatRequest,
        request: Request,
        routing_context: ComplianceRoutingContext | None = None,
        understanding: QuestionUnderstanding | None = None,
    ) -> ChatResponse:
        """Shared chat execution; routing_context is server-owned and never an API field."""
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
            response = service.chat(payload, routing_context, understanding)
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

    @application.post(
        "/api/chat",
        response_model=ChatResponse,
        operation_id="chat_with_evidence",
        responses={
            502: {"description": "Generation output invalid"},
            503: {"description": "Retrieval or generation unavailable"},
            504: {"description": "Generation timed out"},
        },
    )
    @application.post(
        "/api/v1/chat",
        response_model=ChatResponse,
        operation_id="chat_with_evidence_v1",
        responses={
            502: {"description": "Generation output invalid"},
            503: {"description": "Retrieval or generation unavailable"},
            504: {"description": "Generation timed out"},
        },
    )
    def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        original = payload.clarification_context.original_question if payload.clarification_context else None
        understanding = understand_question(payload.question, original, payload.assistant_context)
        routing_context = None
        context = understanding.assistant_context
        if understanding.intent == "roadmap" and context is not None:
            routing_context = ComplianceRoutingContext(
                goal="complete_roadmap",
                power_type=(context.power_type if context.power_type in {
                    "battery_operated", "mains_electric", "non_electric", "not_sure",
                } else "not_sure"),
                role=context.role or "not_sure",
                age_group=context.age_group or "not_sure",
                application_stage=context.application_stage or "not_sure",
                product_description=context.product_description or "toys",
            )
        return run_chat(payload, request, routing_context=routing_context, understanding=understanding)

    @application.post(
        "/api/compliance/guide",
        response_model=ComplianceGuideResponse,
        operation_id="get_compliance_guidance",
    )
    @application.post(
        "/api/v1/compliance/guide",
        response_model=ComplianceGuideResponse,
        operation_id="get_compliance_guidance_v1",
    )
    def compliance_guide(profile: ComplianceProfile, request: Request) -> ComplianceGuideResponse:
        """Grounded manufacturer guide; submitted profile is untrusted query context."""
        audience = "consumer" if profile.role == "consumer" else "manufacturer"
        routing_context = ComplianceRoutingContext(
            goal=profile.goal,
            power_type=profile.power_type,
            role=profile.role,
            age_group=profile.intended_age_group,
            application_stage=profile.application_stage,
            product_description=profile.product_description,
        )
        guidance = run_chat(ChatRequest(
            question=compliance_query(profile), top_k=8, include_guidance=False, audience=audience,
        ), request, routing_context)
        guidance = enforce_compliance_invariants(profile, guidance)
        return ComplianceGuideResponse(profile=profile, guidance=guidance)

    return application


app = create_app()
