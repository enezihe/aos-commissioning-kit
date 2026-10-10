from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from aosconfig.models import AirportConfig

SAMPLE = Path(__file__).resolve().parents[3] / "config" / "airport.yaml"


@pytest.fixture
def data():
    """A fresh copy of the valid sample config for every test."""
    return yaml.safe_load(SAMPLE.read_text())


def test_sample_config_is_valid(data):
    AirportConfig(**data)          # must not raise


def test_duplicate_gate_is_rejected(data):
    data["gates"].append({"id": "A1", "terminal": "T1"})
    with pytest.raises(ValidationError) as exc:
        AirportConfig(**data)
    assert "duplicate gate id: A1" in str(exc.value)


def test_gate_with_unknown_terminal_is_rejected(data):
    data["gates"].append({"id": "Z1", "terminal": "T9"})
    with pytest.raises(ValidationError) as exc:
        AirportConfig(**data)
    assert "gate Z1: unknown terminal T9" in str(exc.value)


def test_airline_with_unknown_gate_is_rejected(data):
    data["airlines"][0]["gates"].append("Q7")
    with pytest.raises(ValidationError) as exc:
        AirportConfig(**data)
    assert "airline TK: unknown gate Q7" in str(exc.value)


def test_bad_airline_code_is_rejected(data):
    data["airlines"][1]["code"] = "PCX"
    with pytest.raises(ValidationError):
        AirportConfig(**data)


def test_all_problems_are_reported_together(data):
    """Cross rules collect every problem, so one run shows them all."""
    data["gates"].append({"id": "A1", "terminal": "T1"})
    data["gates"].append({"id": "Z1", "terminal": "T9"})
    data["airlines"][0]["gates"].append("Q7")
    with pytest.raises(ValidationError) as exc:
        AirportConfig(**data)
    text = str(exc.value)
    assert "duplicate gate id: A1" in text
    assert "unknown terminal T9" in text
    assert "unknown gate Q7" in text
