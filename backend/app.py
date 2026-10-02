"""FastAPI transport composition for the V1 API contract."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from functools import lru_cache
import os
import logging
from typing import Any, Final, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from backend.auth.fastapi import verified_identity_dependency
from backend.auth.identity import AdmissionRepository, AdmittedIdentity, FirebaseIdTokenVerifier, TokenVerifier, FirestoreAdmissionRepository, RegisterAdmissionDenyFence
from backend.auth.workload import GoogleWorkloadTokenVerifier, WorkloadTokenVerifier, workload_identity_dependency
from backend.contracts.envelopes import ApiError, ErrorEnvelope, ResponseEnvelope, ResponseMeta
from backend.contracts.routes import (
    MeResource, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT,
)
from backend.openapi import (
    ChartPoint,
    ChartQuery,
    LongTermRankingsData,
    RecommendationQuery,
    RankingQuery,
    StockChartData,
    StockDetailData,
    StockQuery,
    SwingRecommendationsData,
)
from backend.publication.analysis import AnalyticalPublisher, PublicationError
from backend.read_api.analysis import AnalysisNotReady, InvalidAnalysisSymbol, read_chart, read_long_term, read_stock, read_swing
from backend.read_api.cursors import CursorError
from backend.read_api.readers import AnalysisPublisher
from backend.store.firestore_sdk import FirestoreSdkStore
from backend.store.repositories import Page
from backend.publication.analysis import ServingStock
from backend.workflow_dispatcher import WorkflowDispatchError, dispatch_and_wait

PRIVATE_NO_STORE: Final = "private, no-store"
MAX_BODY_BYTES: Final = 16 * 1024
LOGGER = logging.getLogger(__name__)
ERROR_MESSAGES: Final = {
    "unauthenticated": "Authentication is required.", "admission_denied": "Current invitation access is required.",
    "email_unverified": "Verify your email before accessing the workspace.",
    "admission_unavailable": "Admission could not be verified.", "service_unavailable": "The service is temporarily unavailable.",
    "analysis_not_ready": "Analysis is not ready for this request.", "validation_failed": "The request is invalid.",
    "body_too_large": "The request body is too large.", "not_found": "The requested resource was not found.",
    "rate_limited": "Too many requests.",
}


@lru_cache(maxsize=1)
def _production_admissions() -> AdmissionRepository:
    from google.cloud import firestore
    from google.cloud import storage  # type: ignore[attr-defined]
    from backend.recovery.register import GcsStorageAdapter

    client = firestore.Client()
    storage_client = storage.Client()
    if not storage_client.project:
        raise RuntimeError("recovery register project is unavailable")
    register = GcsStorageAdapter(storage_client.bucket(f"{storage_client.project}-v1-recovery-register"))
    return FirestoreAdmissionRepository(client, deny_fence=RegisterAdmissionDenyFence(register))


class _LazyAdmissionRepository:
    async def is_admitted(self, uid: str, email: str) -> bool:
        return await _production_admissions().is_admitted(uid, email)


@lru_cache(maxsize=1)
def _production_analysis_publisher() -> AnalyticalPublisher:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    cursor_secret = os.environ.get("FIRESTORE_CURSOR_SECRET", "")
    if not project or not cursor_secret:
        raise RuntimeError("analysis serving configuration is unavailable")
    return AnalyticalPublisher(
        FirestoreSdkStore(project_id=project, cursor_secret=cursor_secret)
    )


class _LazyAnalysisPublisher:
    def _publisher(self) -> AnalyticalPublisher:
        try:
            return _production_analysis_publisher()
        except Exception as error:
            raise PublicationError("analysis serving configuration is unavailable") from error

    def active_publication(self) -> Any:
        return self._publisher().active_publication()

    def read_batch(self, batch_id: str, *, limit: int, cursor: str | None = None) -> Page[ServingStock]:
        return self._publisher().read_batch(batch_id, limit=limit, cursor=cursor)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_id() -> str:
    return uuid4().hex


def _chart_query(
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    batch_id: str | None = Query(default=None),
    series: tuple[str, ...] | None = Query(default=None),
) -> ChartQuery:
    return ChartQuery.model_validate({
        "from": from_date,
        "to": to_date,
        "batch_id": batch_id,
        "series": series,
    })


def _market_chart_fallback(*, symbol: str, from_date: date, to_date: date, batch_id: str) -> StockChartData:
    """Serve close prices directly when the analytical chart output is unavailable."""
    from google.cloud import bigquery

    table = os.environ.get("MARKET_DATA_TABLE", "dev-tradvisor.stocks.shares").strip()
    if not table or "`" in table or ";" in table:
        raise PublicationError("market data serving configuration is unavailable")
    client = bigquery.Client()
    query = (
        f"SELECT date, close FROM `{table}` "
        "WHERE symbol = @symbol AND date BETWEEN @from_date AND @to_date "
        "ORDER BY date"
    )
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("symbol", "STRING", symbol),
        bigquery.ScalarQueryParameter("from_date", "DATE", from_date),
        bigquery.ScalarQueryParameter("to_date", "DATE", to_date),
    ])
    rows_by_date: dict[date, Any] = {}
    for row in client.query(query, job_config=config).result():
        session_date = row["date"]
        current = rows_by_date.get(session_date)
        if current is None or (current["close"] is None and row["close"] is not None):
            rows_by_date[session_date] = row
    rows = [rows_by_date[session_date] for session_date in sorted(rows_by_date)]
    points = tuple(ChartPoint.model_validate({
        "session_date": row["date"],
        "status": "traded" if row["close"] is not None else "missing_price",
        "open": None, "high": None, "low": None,
        "close": None if row["close"] is None else {"amount": str(row["close"]), "currency": "XOF"},
        "last_traded_close": None if row["close"] is None else {"amount": str(row["close"]), "currency": "XOF"},
        "analytical_carried_close": None,
        "volume": None, "indicators": {}, "source_evidence": (),
    }) for row in rows)
    return StockChartData.model_validate({
        "symbol": symbol, "from": from_date, "to": to_date,
        "batch_id": batch_id, "points": points,
    })


def _page_query(request: Request) -> dict[str, object]:
    raw_limit = request.query_params.get("limit")
    try:
        limit = DEFAULT_PAGE_LIMIT if raw_limit is None else int(raw_limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="validation_failed") from error
    if not 1 <= limit <= MAX_PAGE_LIMIT:
        raise HTTPException(status_code=422, detail="validation_failed")
    return {
        "limit": limit,
        "cursor": request.query_params.get("cursor"),
        "symbol": request.query_params.get("symbol"),
        "sector": request.query_params.get("sector"),
    }


def _recommendation_query(request: Request) -> RecommendationQuery:
    return RecommendationQuery.model_validate(_page_query(request))


def _ranking_query(request: Request) -> RankingQuery:
    objective = request.query_params.get("objective")
    if objective is None:
        raise HTTPException(status_code=422, detail="validation_failed")
    return RankingQuery.model_validate({"objective": objective, **_page_query(request)})


def _meta(request: Request, clock: Callable[[], datetime]) -> ResponseMeta:
    return ResponseMeta(request_id=cast(str, request.state.request_id), server_time=clock(), schema_version=1)


def create_app(
    *, verifier: TokenVerifier | None = None, admissions: AdmissionRepository | None = None,
    workload_verifier: WorkloadTokenVerifier | None = None,
    workload_audience: str | None = None,
    analysis_publisher: AnalyticalPublisher | None = None,
    analysis_cursor_secret: bytes | str | None = None,
    clock: Callable[[], datetime] = _utc_now,
    request_id_factory: Callable[[], str] = _request_id,
) -> FastAPI:
    selected_verifier = verifier if verifier is not None else FirebaseIdTokenVerifier()
    require_identity = verified_identity_dependency(selected_verifier)
    require_workload = workload_identity_dependency(workload_verifier or GoogleWorkloadTokenVerifier(), audience=workload_audience)
    selected_analysis: AnalysisPublisher = analysis_publisher or _LazyAnalysisPublisher()
    selected_analysis_secret: bytes | str = analysis_cursor_secret if analysis_cursor_secret is not None else os.environ.get("FIRESTORE_CURSOR_SECRET", "")
    if isinstance(selected_analysis_secret, str):
        selected_analysis_secret = selected_analysis_secret.encode("utf-8")
    application = FastAPI(title="Tradvisor API", version="0.13.0")
    allowed_origins = [origin.strip() for origin in os.environ.get("TRADVISOR_CORS_ORIGINS", "").split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "PATCH", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    from backend.openapi import build_openapi
    application.openapi = build_openapi  # type: ignore[method-assign]

    @application.middleware("http")
    async def request_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = request_id_factory()
        content_length = request.headers.get("content-length")
        if content_length and request.method in {"POST", "PATCH", "PUT"} and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"error": {"code": "body_too_large", "message": ERROR_MESSAGES["body_too_large"], "retryable": False, "request_id": request.state.request_id}}, headers={"Cache-Control": PRIVATE_NO_STORE})
        response = await call_next(request)
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = PRIVATE_NO_STORE
        return response

    async def contract_http_exception(request: Request, error: Exception) -> Response:
        if isinstance(error, HTTPException) and request.url.path.startswith("/v1/") and isinstance(error.detail, str) and error.detail in ERROR_MESSAGES:
            body = ErrorEnvelope(error=ApiError(code=error.detail, message=ERROR_MESSAGES[error.detail], retryable=error.status_code == 503, request_id=cast(str, request.state.request_id)))
            headers = dict(error.headers or {})
            headers["Cache-Control"] = PRIVATE_NO_STORE
            return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"), headers=headers)
        return await http_exception_handler(request, cast(HTTPException, error))

    application.add_exception_handler(HTTPException, contract_http_exception)

    async def contract_validation_exception(request: Request, error: RequestValidationError) -> Response:
        if request.url.path.startswith("/v1/"):
            body = ErrorEnvelope(error=ApiError(code="validation_failed", message=ERROR_MESSAGES["validation_failed"], retryable=False, request_id=cast(str, request.state.request_id)))
            return JSONResponse(status_code=422, content=body.model_dump(mode="json"), headers={"Cache-Control": PRIVATE_NO_STORE})
        from fastapi.exception_handlers import request_validation_exception_handler
        return await request_validation_exception_handler(request, error)

    application.add_exception_handler(RequestValidationError, cast(Any, contract_validation_exception))

    @application.get("/healthz", include_in_schema=False)
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/internal/workflows/{workflow_name}/dispatch", include_in_schema=False)
    async def dispatch_workflow(workflow_name: str, _: str = Depends(require_workload)) -> dict[str, str]:
        try:
            execution = await __import__("asyncio").to_thread(dispatch_and_wait, workflow_name, project=__import__("os").environ.get("GOOGLE_CLOUD_PROJECT", ""), region=__import__("os").environ.get("WORKFLOW_REGION", "europe-central2"))
        except WorkflowDispatchError as error:
            raise HTTPException(status_code=503, detail="service_unavailable") from error
        return {"execution": execution}

    @application.get("/v1/me", response_model=ResponseEnvelope[MeResource])
    async def get_me(request: Request, identity: AdmittedIdentity = Depends(require_identity)) -> ResponseEnvelope[MeResource]:
        return ResponseEnvelope(data=MeResource(uid=identity.uid, email=identity.email), meta=_meta(request, clock))

    def _analysis_failure(error: Exception) -> HTTPException:
        if isinstance(error, InvalidAnalysisSymbol):
            return HTTPException(status_code=422, detail="validation_failed")
        if isinstance(error, KeyError):
            return HTTPException(status_code=404, detail="not_found")
        if isinstance(error, CursorError):
            return HTTPException(status_code=409, detail="cursor_stale")
        return HTTPException(status_code=503, detail="analysis_not_ready")

    @application.get("/v1/swing/recommendations", response_model=ResponseEnvelope[SwingRecommendationsData])
    async def get_swing_recommendations(request: Request, query: RecommendationQuery = Depends(_recommendation_query), _identity: AdmittedIdentity = Depends(require_identity)) -> ResponseEnvelope[SwingRecommendationsData]:
        try:
            data = read_swing(selected_analysis, limit=query.limit, cursor=query.cursor, symbol=query.symbol, sector=query.sector, cursor_secret=selected_analysis_secret, now=clock)
        except Exception as error:
            raise _analysis_failure(error) from error
        return ResponseEnvelope(data=data, meta=_meta(request, clock))

    @application.get("/v1/long-term/rankings", response_model=ResponseEnvelope[LongTermRankingsData])
    async def get_long_term_rankings(request: Request, query: RankingQuery = Depends(_ranking_query), _identity: AdmittedIdentity = Depends(require_identity)) -> ResponseEnvelope[LongTermRankingsData]:
        try:
            data = read_long_term(selected_analysis, objective=query.objective, limit=query.limit, cursor=query.cursor, symbol=query.symbol, sector=query.sector, cursor_secret=selected_analysis_secret, now=clock)
        except Exception as error:
            raise _analysis_failure(error) from error
        return ResponseEnvelope(data=data, meta=_meta(request, clock))

    @application.get("/v1/stocks/{symbol}", response_model=ResponseEnvelope[StockDetailData])
    async def get_stock(request: Request, symbol: str, _query: StockQuery = Depends(), _identity: AdmittedIdentity = Depends(require_identity)) -> ResponseEnvelope[StockDetailData]:
        try:
            data = read_stock(selected_analysis, symbol=symbol, cursor_secret=selected_analysis_secret, now=clock)
        except Exception as error:
            raise _analysis_failure(error) from error
        return ResponseEnvelope(data=data, meta=_meta(request, clock))

    @application.get("/v1/stocks/{symbol}/chart", response_model=ResponseEnvelope[StockChartData])
    async def get_stock_chart(request: Request, symbol: str, query: ChartQuery = Depends(_chart_query), _identity: AdmittedIdentity = Depends(require_identity)) -> ResponseEnvelope[StockChartData]:
        try:
            data = read_chart(selected_analysis, symbol=symbol, from_date=query.from_date, to_date=query.to_date, series=query.series, cursor_secret=selected_analysis_secret, now=clock)
            if not data.points:
                data = _market_chart_fallback(
                    symbol=symbol,
                    from_date=query.from_date,
                    to_date=query.to_date,
                    batch_id=f"market-fallback:{query.to_date.isoformat()}",
                )
        except AnalysisNotReady:
            try:
                data = _market_chart_fallback(
                    symbol=symbol,
                    from_date=query.from_date,
                    to_date=query.to_date,
                    batch_id=f"market-fallback:{query.to_date.isoformat()}",
                )
            except Exception as error:
                LOGGER.exception("market chart fallback failed for %s", symbol)
                raise _analysis_failure(error) from error
        except Exception as error:
            raise _analysis_failure(error) from error
        return ResponseEnvelope(data=data, meta=_meta(request, clock))

    return application


__all__ = ["create_app"]
