"""API v0.13 OpenAPI document generated from backend contract models."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from pydantic import Field, StringConstraints, model_validator

from backend.contracts.analysis import (
    AnalyticalMetric,
    LongTermResult,
    NormalizedCompany,
    NormalizedDividend,
    NormalizedDividendCoverage,
    NormalizedPrice,
    NormalizedRating,
    Provenance,
    ReasonCode,
    Score,
)
from backend.contracts.envelopes import (
    ApiError,
    CommandMetadata,
    ContractModel,
    ErrorEnvelope,
    ResponseEnvelope,
    ResponseMeta,
)
from backend.contracts.paper import CashMovement, PaperExecution, PaperOrder, PaperPosition, PortfolioSummary
from backend.contracts.routes import (
    CashMovementListResource,
    CashMovementListRequest,
    CommandAcknowledgement,
    CreatePaperOrderRequest,
    CreatePaperOrderResource,
    ExecutionListResource,
    ExecutionListRequest,
    MeResource,
    OrderListRequest,
    OrderListResource,
    PageRequest,
    PAPER_ROUTES,
    PatchPreferencesRequest,
    PortfolioResource,
    ResetPortfolioRequest,
    ResetPortfolioResource,
    SetupPortfolioRequest,
    SetupPortfolioResource,
    RouteContract,
    RouteErrorCode,
)
from backend.contracts.scalars import NonNegativeMoney, NonNegativeVersion, OpaqueIdentifier

API_VERSION = "0.13"
MAX_CHART_SESSIONS = 1000


class ScoreMetric(AnalyticalMetric[Score]):
    pass


class NumericMetric(AnalyticalMetric[float]):
    pass


class SwingGuard(ContractModel):
    code: ReasonCode
    status: Literal["pass", "fail", "unknown"]
    observed: float | None
    threshold: float | None
    evidence_refs: tuple[OpaqueIdentifier, ...]


class ReasonExplanation(ContractModel):
    code: ReasonCode
    message: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class HoldingAdvice(ContractModel):
    action: Literal["keep", "sell", "insufficient_data", "not_applicable"]
    generation: OpaqueIdentifier | None
    state_version: NonNegativeVersion | None
    exit_policy_version: OpaqueIdentifier | None
    evaluation_session: date | None
    reasons: tuple[ReasonExplanation, ...]
    unavailable_checks: tuple[ReasonExplanation, ...]


class SwingRecommendation(ContractModel):
    symbol: OpaqueIdentifier
    entry_action: Literal["buy", "no_clear_signal", "insufficient_data"]
    buy_strength: ScoreMetric
    indicators: dict[Literal["ema20", "ema50", "rsi14", "atr14", "traded_value20"], NumericMetric]
    eligibility_guards: tuple[SwingGuard, ...]
    holding_advice: HoldingAdvice | None


class SwingRecommendationsData(ContractModel):
    batch_id: OpaqueIdentifier
    market_session: date
    published_at: datetime
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    strategy_id: OpaqueIdentifier
    generation: OpaqueIdentifier | None
    state_version: NonNegativeVersion | None
    items: tuple[SwingRecommendation, ...]
    next_cursor: str | None


class GrowthAnalysis(ContractModel):
    growth_score: ScoreMetric
    overall_score: ScoreMetric
    dimension_contributions: dict[str, ScoreMetric]
    advisory_state: Literal["candidate", "watchlist", "low_score", "review_required", "insufficient_evidence"]
    reasons: tuple[ReasonExplanation, ...]

    @model_validator(mode="after")
    def validate_growth_scores(self) -> "GrowthAnalysis":
        if self.growth_score != self.overall_score:
            raise ValueError("overall Growth score must equal growth_score")
        return self


class DividendResearch(ContractModel):
    payments: tuple[NormalizedDividend, ...]
    coverage: tuple[NormalizedDividendCoverage, ...]
    trailing_ordinary_yield: NumericMetric | None
    dividend_score: ScoreMetric

    @model_validator(mode="after")
    def validate_deferred_score(self) -> "DividendResearch":
        if (
            self.dividend_score.status != "deferred_scope"
            or self.dividend_score.value is not None
            or "dividend_scoring_deferred_v1" not in self.dividend_score.reason_codes
        ):
            raise ValueError("V1 dividend scoring must remain explicitly deferred")
        return self


class LongTermRankedCompany(ContractModel):
    company_id: OpaqueIdentifier
    symbol: OpaqueIdentifier
    result: LongTermResult
    growth: GrowthAnalysis
    dividend_research: DividendResearch

    @model_validator(mode="after")
    def validate_analysis_views(self) -> "LongTermRankedCompany":
        if self.growth.overall_score != self.result.growth.overall_score:
            raise ValueError("Growth view must match its immutable LongTermResult")
        if self.dividend_research.dividend_score != self.result.dividend.overall_score:
            raise ValueError("Dividend view must match its deferred LongTermResult objective")
        return self


class LongTermRankingsData(ContractModel):
    objective: Literal["growth", "dividend", "balanced"]
    batch_id: OpaqueIdentifier
    market_session: date
    published_at: datetime
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    strategy_id: OpaqueIdentifier
    items: tuple[LongTermRankedCompany, ...]
    next_cursor: str | None
    overall_score: ScoreMetric | None = None

    @model_validator(mode="after")
    def validate_balanced_deferred(self) -> "LongTermRankingsData":
        if self.objective == "balanced":
            if (
                self.items
                or self.overall_score is None
                or self.overall_score.status != "deferred_scope"
                or self.overall_score.value is not None
                or "balanced_scoring_deferred_v1" not in self.overall_score.reason_codes
            ):
                raise ValueError("Balanced must return a deferred null score and no ranked items")
        elif self.overall_score is not None:
            raise ValueError("only Balanced rankings can carry an overall score")
        if self.objective == "dividend":
            symbols = [item.symbol for item in self.items]
            if symbols != sorted(symbols):
                raise ValueError("dividend research rows must be ordered by symbol")
        return self


class StockDetailData(ContractModel):
    company: NormalizedCompany
    batch_id: OpaqueIdentifier
    market_session: date
    published_at: datetime
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    strategy_id: OpaqueIdentifier
    swing: SwingRecommendation
    long_term: LongTermResult
    growth: GrowthAnalysis
    dividend_research: DividendResearch
    prices: tuple[NormalizedPrice, ...]
    source_evidence: tuple[Provenance, ...]
    ratings: tuple[NormalizedRating, ...]

    @model_validator(mode="after")
    def validate_analysis_views(self) -> "StockDetailData":
        if self.growth.overall_score != self.long_term.growth.overall_score:
            raise ValueError("Growth view must match its immutable LongTermResult")
        if self.dividend_research.dividend_score != self.long_term.dividend.overall_score:
            raise ValueError("Dividend view must match its deferred LongTermResult objective")
        return self


ChartSeriesName = Literal["ohlcv", "ema20", "ema50", "rsi14", "atr14", "traded_value20"]
ChartIndicatorName = Literal["ema20", "ema50", "rsi14", "atr14", "traded_value20"]
ChartPointStatus = Literal["traded", "confirmed_no_trade", "unknown", "missing_price"]


class ChartPoint(ContractModel):
    session_date: date
    status: ChartPointStatus
    open: NonNegativeMoney | None
    high: NonNegativeMoney | None
    low: NonNegativeMoney | None
    close: NonNegativeMoney | None
    last_traded_close: NonNegativeMoney | None
    analytical_carried_close: NonNegativeMoney | None
    volume: Annotated[int, Field(ge=0)] | None
    indicators: dict[ChartIndicatorName, NumericMetric]
    source_evidence: tuple[Provenance, ...]


class StockChartData(ContractModel):
    symbol: OpaqueIdentifier
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    batch_id: OpaqueIdentifier
    points: Annotated[tuple[ChartPoint, ...], Field(max_length=MAX_CHART_SESSIONS)]

    @model_validator(mode="after")
    def validate_ordered_range(self) -> "StockChartData":
        dates = [point.session_date for point in self.points]
        if (
            dates != sorted(dates)
            or len(dates) != len(set(dates))
            or any(day < self.from_date or day > self.to_date for day in dates)
        ):
            raise ValueError("chart points must be ascending and within the requested inclusive date range")
        return self


class RecommendationQuery(PageRequest):
    batch_id: OpaqueIdentifier | None = None
    symbol: OpaqueIdentifier | None = None
    sector: Annotated[str, StringConstraints(min_length=1, max_length=256)] | None = None


class RankingQuery(RecommendationQuery):
    objective: Literal["growth", "dividend", "balanced"]


class StockQuery(ContractModel):
    batch_id: OpaqueIdentifier | None = None


class ChartQuery(StockQuery):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    series: Annotated[tuple[ChartSeriesName, ...], Field(max_length=6)] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "ChartQuery":
        if self.to_date < self.from_date:
            raise ValueError("chart end date cannot precede its start date")
        if self.series is not None and len(self.series) != len(set(self.series)):
            raise ValueError("chart series selection cannot contain duplicates")
        return self


class OpenAPIOperation(ContractModel):
    operation_id: str
    summary: str
    request_model: type[ContractModel] | None = None
    response_model: type[ContractModel]
    success_status: int = 200
    query_model: type[ContractModel] | None = None
    path_parameters: tuple[str, ...] = ()
    error_outcomes: tuple[tuple[int, RouteErrorCode], ...] = (
        (401, "unauthenticated"),
        (403, "admission_denied"),
        (429, "rate_limited"),
        (503, "service_unavailable"),
        (503, "admission_unavailable"),
    )


ANALYTICAL_LIST_ERRORS: tuple[tuple[int, RouteErrorCode], ...] = (
    (401, "unauthenticated"),
    (403, "admission_denied"),
    (404, "not_found"),
    (409, "cursor_stale"),
    (410, "snapshot_expired"),
    (422, "validation_failed"),
    (429, "rate_limited"),
    (503, "service_unavailable"),
    (503, "admission_unavailable"),
    (503, "analysis_not_ready"),
)
STOCK_READ_ERRORS: tuple[tuple[int, RouteErrorCode], ...] = (
    (401, "unauthenticated"),
    (403, "admission_denied"),
    (404, "not_found"),
    (410, "snapshot_expired"),
    (422, "validation_failed"),
    (429, "rate_limited"),
    (503, "service_unavailable"),
    (503, "admission_unavailable"),
    (503, "analysis_not_ready"),
)

OPERATIONS: tuple[OpenAPIOperation, ...] = (
    OpenAPIOperation(
        operation_id="getMe",
        summary="Read the authenticated user's profile and preferences",
        response_model=MeResource,
    ),
    OpenAPIOperation(
        operation_id="patchMePreferences",
        summary="Update user preferences",
        request_model=PatchPreferencesRequest,
        response_model=CommandAcknowledgement,
    ),
    OpenAPIOperation(
        operation_id="getSwingRecommendations",
        summary="Read shared Swing entry results and separate holding advice",
        query_model=RecommendationQuery,
        response_model=SwingRecommendationsData,
        error_outcomes=ANALYTICAL_LIST_ERRORS,
    ),
    OpenAPIOperation(
        operation_id="getLongTermRankings",
        summary="Read Growth rankings or dividend research with deferred Balanced compatibility",
        query_model=RankingQuery,
        response_model=LongTermRankingsData,
        error_outcomes=ANALYTICAL_LIST_ERRORS,
    ),
    OpenAPIOperation(
        operation_id="getStock",
        summary="Read company evidence and both analysis workflows",
        query_model=StockQuery,
        response_model=StockDetailData,
        path_parameters=("symbol",),
        error_outcomes=STOCK_READ_ERRORS,
    ),
    OpenAPIOperation(
        operation_id="getStockChart",
        summary="Read up to 1,000 exchange-session chart observations",
        query_model=ChartQuery,
        response_model=StockChartData,
        path_parameters=("symbol",),
        error_outcomes=STOCK_READ_ERRORS,
    ),
    OpenAPIOperation(
        operation_id="getPaperPortfolio",
        summary="Read the active paper portfolio",
        response_model=PortfolioResource,
    ),
    OpenAPIOperation(
        operation_id="setupPaperPortfolio",
        summary="Set up a paper portfolio",
        request_model=SetupPortfolioRequest,
        response_model=SetupPortfolioResource,
        success_status=201,
    ),
    OpenAPIOperation(
        operation_id="createPaperOrder",
        summary="Create a manual recommendation-linked paper order",
        request_model=CreatePaperOrderRequest,
        response_model=CreatePaperOrderResource,
        success_status=201,
    ),
    OpenAPIOperation(
        operation_id="listPaperOrders",
        summary="List bounded paper order history",
        query_model=OrderListRequest,
        response_model=OrderListResource,
    ),
    OpenAPIOperation(
        operation_id="listPaperExecutions",
        summary="List bounded paper execution history",
        query_model=ExecutionListRequest,
        response_model=ExecutionListResource,
    ),
    OpenAPIOperation(
        operation_id="listPaperCashMovements",
        summary="List bounded paper cash ledger",
        query_model=CashMovementListRequest,
        response_model=CashMovementListResource,
    ),
    OpenAPIOperation(
        operation_id="resetPaperPortfolio",
        summary="Reset the active paper portfolio",
        request_model=ResetPortfolioRequest,
        response_model=ResetPortfolioResource,
        success_status=200,
    ),
)


def _components() -> dict[str, object]:
    models: dict[str, type[ContractModel]] = {
        "ApiError": ApiError,
        "ErrorEnvelope": ErrorEnvelope,
        "ResponseMeta": ResponseMeta,
        "CommandMetadata": CommandMetadata,
        "MeResource": MeResource,
        "PortfolioResource": PortfolioResource,
        "PortfolioSummary": PortfolioSummary,
        "PaperPosition": PaperPosition,
        "PaperOrder": PaperOrder,
        "PaperExecution": PaperExecution,
        "CashMovement": CashMovement,
        "PageRequest": PageRequest,
        "OrderListRequest": OrderListRequest,
        "ExecutionListRequest": ExecutionListRequest,
        "CashMovementListRequest": CashMovementListRequest,
        "CommandAcknowledgement": CommandAcknowledgement,
        "SetupPortfolioRequest": SetupPortfolioRequest,
        "SetupPortfolioResource": SetupPortfolioResource,
        "CreatePaperOrderRequest": CreatePaperOrderRequest,
        "CreatePaperOrderResource": CreatePaperOrderResource,
        "ResetPortfolioRequest": ResetPortfolioRequest,
        "ResetPortfolioResource": ResetPortfolioResource,
        "PatchPreferencesRequest": PatchPreferencesRequest,
        "SwingRecommendation": SwingRecommendation,
        "SwingRecommendationsData": SwingRecommendationsData,
        "LongTermRankedCompany": LongTermRankedCompany,
        "LongTermRankingsData": LongTermRankingsData,
        "StockDetailData": StockDetailData,
        "ReasonExplanation": ReasonExplanation,
        "GrowthAnalysis": GrowthAnalysis,
        "DividendResearch": DividendResearch,
        "ChartPoint": ChartPoint,
        "StockChartData": StockChartData,
        "RecommendationQuery": RecommendationQuery,
        "RankingQuery": RankingQuery,
        "StockQuery": StockQuery,
        "ChartQuery": ChartQuery,
    }
    schemas: dict[str, object] = {}
    optional_default_fields = {
        "CommandMetadata": {"expected_generation", "expected_state_version"},
        "PatchPreferencesRequest": {"objective", "fee_rate_pct"},
        "CreatePaperOrderRequest": {"acknowledge_keep_override"},
    }
    for name, model in models.items():
        schema = model.model_json_schema(mode="serialization", ref_template="#/components/schemas/{model}")
        definitions = schema.pop("$defs", {})
        for definition_name, definition in definitions.items():
            schemas.setdefault(definition_name, definition)
        schemas[name] = schema
    for operation in OPERATIONS:
        response_model: Any = operation.response_model
        envelope = ResponseEnvelope[response_model]
        schema = envelope.model_json_schema(mode="serialization", ref_template="#/components/schemas/{model}")
        definitions = schema.pop("$defs", {})
        for definition_name, definition in definitions.items():
            schemas.setdefault(definition_name, definition)
        schemas[f"{operation.response_model.__name__}Response"] = schema
    # Keep the contract model intact while exposing idempotency as the v0.13 HTTP header.
    command_body = cast(dict[str, Any], deepcopy(schemas["CommandMetadata"]))
    command_properties = command_body["properties"]
    if isinstance(command_properties, dict):
        command_properties.pop("idempotency_key", None)
        for name in ("expected_generation", "expected_state_version"):
            property_schema = command_properties.get(name)
            if isinstance(property_schema, dict) and "default" in property_schema:
                property_schema["x-default"] = property_schema.pop("default")
    command_required = command_body.get("required")
    if isinstance(command_required, list):
        command_body["required"] = [name for name in command_required if name != "idempotency_key"]
    command_body["description"] = (
        "Restore-safe command metadata. Idempotency-Key is carried in the HTTP header per API v0.13."
    )
    schemas["CommandMetadataBody"] = command_body
    for request_name in (
        "PatchPreferencesRequest",
        "SetupPortfolioRequest",
        "CreatePaperOrderRequest",
        "ResetPortfolioRequest",
    ):
        request_schema = cast(dict[str, Any], schemas[request_name])
        request_properties = request_schema.get("properties") if isinstance(request_schema, dict) else None
        command_property = request_properties.get("command") if isinstance(request_properties, dict) else None
        if isinstance(command_property, dict):
            command_property["$ref"] = "#/components/schemas/CommandMetadataBody"
    for name, schema_value in schemas.items():
        if not isinstance(schema_value, dict):
            continue
        properties = schema_value.get("properties")
        if not isinstance(properties, dict):
            continue
        if name in {"NonNegativeMoney", "SignedMoney", "StartingCash"}:
            amount = properties.get("amount")
            if isinstance(amount, dict):
                signed = name == "SignedMoney"
                amount["pattern"] = (
                    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$"
                    if signed
                    else (
                        r"^(?:0|[1-9][0-9]*)(?:\.0{1,6})?$"
                        if name == "StartingCash"
                        else r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$"
                    )
                )
                amount["maxLength"] = 21 if signed else 20
                amount["x-money-currency"] = "XOF"
                if name != "StartingCash":
                    amount["x-response-pattern"] = (
                        r"^-?(?:0|[1-9][0-9]*)\.[0-9]{6}$"
                        if signed
                        else r"^(?:0|[1-9][0-9]*)\.[0-9]{6}$"
                    )
                if name == "StartingCash":
                    amount["description"] = (
                        "Whole-XOF amount from 100000 through 100000000 inclusive; "
                        "response values use six decimal places."
                    )
                    amount["x-whole-xof-minimum"] = 100_000
                    amount["x-whole-xof-maximum"] = 100_000_000
        for field_name, value in properties.items():
            if (
                name in optional_default_fields
                and field_name in optional_default_fields[name]
                and isinstance(value, dict)
                and "default" in value
            ):
                value["x-default"] = value.pop("default")
            if field_name == "fee_rate_pct" and isinstance(value, dict):
                value["pattern"] = r"^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?$"
            if field_name == "quantity" and isinstance(value, dict):
                value.setdefault("minimum", 1)
                value.setdefault("maximum", 1_000_000_000)
    return schemas


def _parameter(
    name: str,
    schema: dict[str, object],
    *,
    location: str = "query",
    required: bool = False,
) -> dict[str, object]:
    return {"name": name, "in": location, "required": required, "schema": schema}


def _response_headers(status: int) -> dict[str, object]:
    headers: dict[str, object] = {
        "Cache-Control": {
            "required": True,
            "schema": {"type": "string", "const": "private, no-store"},
        }
    }
    if status == 429:
        headers["Retry-After"] = {
            "required": True,
            "description": "Bounded by the configured per-endpoint rate limit.",
            "schema": {"type": "integer", "minimum": 1},
        }
    return headers


def _query_parameters(model: type[ContractModel]) -> list[dict[str, object]]:
    schema = model.model_json_schema(mode="validation", by_alias=True)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    return [
        _parameter(name, value, required=name in required)
        for name, value in properties.items()
    ]


def _operation(
    route: OpenAPIOperation,
    method: str,
    path: str,
    route_contract: RouteContract | None,
) -> dict[str, object]:
    responses: dict[str, object] = {}
    success_status = route_contract.success_status if route_contract is not None else route.success_status
    response_ref = f"#/components/schemas/{route.response_model.__name__}Response"
    responses[str(success_status)] = {
        "description": "Successful response",
        "headers": _response_headers(success_status),
        "content": {"application/json": {"schema": {"$ref": response_ref}}},
    }
    error_codes_by_status: dict[int, set[str]] = {}
    if route_contract is not None:
        for outcome in route_contract.error_outcomes:
            error_codes_by_status.setdefault(outcome.status, set()).add(outcome.code)
    else:
        for status, code in route.error_outcomes:
            error_codes_by_status.setdefault(status, set()).add(code)
    for status, error_codes in sorted(error_codes_by_status.items()):
        responses[str(status)] = {
            "description": "API error",
            "headers": _response_headers(status),
            "x-error-codes": sorted(error_codes),
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}},
        }
    result: dict[str, object] = {
        "operationId": route.operation_id,
        "summary": route.summary,
        "security": [{"BearerAuth": []}],
        "responses": responses,
    }
    if route.operation_id == "getStockChart":
        result["x-max-exchange-sessions"] = MAX_CHART_SESSIONS
    if route.path_parameters:
        result["parameters"] = [
            _parameter(
                parameter,
                {"type": "string", "minLength": 1, "maxLength": 128},
                location="path",
                required=True,
            )
            for parameter in route.path_parameters
        ]
    if route.query_model is not None:
        parameters = cast(list[dict[str, object]], result.get("parameters", []))
        result["parameters"] = parameters + _query_parameters(route.query_model)
    if route.request_model is not None:
        parameters = cast(list[dict[str, object]], result.get("parameters", []))
        result["parameters"] = parameters + [
            _parameter(
                "Idempotency-Key",
                {"type": "string", "pattern": r"^[0-9]{13}\.[0-9a-f]{32}$"},
                location="header",
                required=True,
            )
        ]
        result["requestBody"] = {
            "required": True,
            "description": "Command bodies are limited to 16 KiB.",
            "x-max-bytes": 16384,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{route.request_model.__name__}"}
                }
            },
        }
    return result


def build_openapi() -> dict[str, object]:
    operations = {route.operation_id: route for route in OPERATIONS}
    paths: dict[str, dict[str, object]] = {}
    route_contracts = {(route.method.lower(), route.path): route for route in PAPER_ROUTES}
    endpoint_map = (
        ("GET", "/v1/me", "getMe"),
        ("PATCH", "/v1/me/preferences", "patchMePreferences"),
        ("GET", "/v1/swing/recommendations", "getSwingRecommendations"),
        ("GET", "/v1/long-term/rankings", "getLongTermRankings"),
        ("GET", "/v1/stocks/{symbol}", "getStock"),
        ("GET", "/v1/stocks/{symbol}/chart", "getStockChart"),
        ("GET", "/v1/paper/portfolio", "getPaperPortfolio"),
        ("POST", "/v1/paper/portfolio", "setupPaperPortfolio"),
        ("POST", "/v1/paper/orders", "createPaperOrder"),
        ("GET", "/v1/paper/orders", "listPaperOrders"),
        ("GET", "/v1/paper/executions", "listPaperExecutions"),
        ("GET", "/v1/paper/cash-movements", "listPaperCashMovements"),
        ("POST", "/v1/paper/reset", "resetPaperPortfolio"),
    )
    for method, path, operation_id in endpoint_map:
        route = operations[operation_id]
        route_contract = route_contracts.get((method.lower(), path))
        paths.setdefault(path, {})[method.lower()] = _operation(route, method, path, route_contract)
    if len(endpoint_map) != 13 or len({operation_id for _, _, operation_id in endpoint_map}) != 13:
        raise RuntimeError("API v0.13 operation inventory must contain 13 unique operations")
    declared_paper_routes = {(method.lower(), path) for method, path, _ in endpoint_map} & set(route_contracts)
    if declared_paper_routes != set(route_contracts):
        raise RuntimeError("OpenAPI operations do not cover the frozen paper route inventory")
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Tradvisor API",
            "version": API_VERSION,
            "description": (
                "API and data contract v0.13. Authenticated application routes; "
                "no live transport is included in this package."
            ),
        },
        "security": [{"BearerAuth": []}],
        "paths": paths,
        "components": {
            "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": _components(),
        },
    }


def render() -> str:
    return json.dumps(build_openapi(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output or Path(__file__).parents[1] / "frontend/src/api/generated/openapi.json"
    expected = render()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            generator = Path(__file__).parents[1] / "scripts/generate-client/generate.sh"
            print(f"OpenAPI drift detected: run {generator}", file=sys.stderr)
            return 1
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
