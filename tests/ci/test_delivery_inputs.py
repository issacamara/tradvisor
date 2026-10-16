from pathlib import Path

from scripts.ci.verify_delivery_inputs import validate


def test_delivery_inputs_are_pinned() -> None:
    validate(Path(__file__).parents[2])
