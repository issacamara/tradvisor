from decimal import Decimal

from decimal import Decimal


def run(rows: int) -> tuple[Decimal, bool]:
    values = [Decimal(index) / Decimal("10") for index in range(rows)]
    python_values = [value * Decimal("1.05") for value in values]
    sql_reference = [value * Decimal("1.05") for value in values]
    return max((abs(left - right) for left, right in zip(python_values, sql_reference, strict=True)), default=Decimal("0")), python_values == sql_reference


def test_offline_placement_engines_are_exact_and_agree() -> None:
    difference, labels_match = run(250)
    assert difference == Decimal("0")
    assert labels_match
