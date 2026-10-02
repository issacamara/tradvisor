from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.openapi import API_VERSION, build_openapi, render
from backend.openapi import ChartQuery

ROOT = Path(__file__).parents[3]
GENERATED_SPEC = ROOT / "frontend/src/api/generated/openapi.json"


def test_schema_covers_every_api_v013_operation() -> None:
    spec = build_openapi()
    operations = {
        (method.upper(), path): operation
        for path, path_item in spec["paths"].items()
        for method, operation in path_item.items()
    }
    assert len(operations) == 5
    assert set(operations) == {
        ("GET", "/v1/me"),
        ("GET", "/v1/swing/recommendations"),
        ("GET", "/v1/long-term/rankings"),
        ("GET", "/v1/stocks/{symbol}"),
        ("GET", "/v1/stocks/{symbol}/chart"),
    }
    assert all(operation["security"] == [{"BearerAuth": []}] for operation in operations.values())
    assert all(
        response["headers"]["Cache-Control"]["schema"]["const"] == "private, no-store"
        for operation in operations.values()
        for response in operation["responses"].values()
    )
    assert spec["info"]["version"] == API_VERSION


def test_schema_retains_nullable_metrics_and_analytical_contracts() -> None:
    schemas = build_openapi()["components"]["schemas"]
    for name in ("NonNegativeMoney",):
        amount = schemas[name]["properties"]["amount"]
        assert amount["type"] == "string"
        expected_pattern = r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$"
        assert amount["pattern"] == expected_pattern
        assert amount["x-money-currency"] == "XOF"

    metric = schemas["ScoreMetric"]
    assert {"assessable", "warming_up", "missing_inputs", "unsupported_basis", "deferred_scope"} <= set(
        metric["properties"]["status"]["enum"]
    )
    assert any(
        variant.get("type") == "null"
        for variant in metric["properties"]["value"]["anyOf"]
    )
    objective = schemas["LongTermObjectiveState"]
    assert "dividend" in str(objective) and "balanced" in str(objective)

    overall_score = schemas["LongTermRankingsData"]["properties"]["overall_score"]["anyOf"]
    assert {"$ref": "#/components/schemas/ScoreMetric"} in overall_score
    assert {"type": "null"} in overall_score



def test_chart_query_rejects_reversed_or_duplicate_series() -> None:
    with pytest.raises(ValidationError):
        ChartQuery.model_validate({"from": date(2026, 6, 2), "to": date(2026, 6, 1)})
    with pytest.raises(ValidationError):
        ChartQuery.model_validate(
            {
                "from": date(2026, 6, 1),
                "to": date(2026, 6, 2),
                "series": ("rsi14", "rsi14"),
            }
        )


def test_generated_document_is_deterministic_and_current() -> None:
    assert render() == render()
    assert GENERATED_SPEC.read_text(encoding="utf-8") == render()
    result = subprocess.run(
        [sys.executable, "-m", "backend.openapi", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    generated = json.loads(GENERATED_SPEC.read_text(encoding="utf-8"))
    component_names = set(generated["components"]["schemas"])
    references: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
                references.add(reference.rsplit("/", 1)[-1])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(generated)
    assert references <= component_names
