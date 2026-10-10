from pathlib import Path

import pytest
import yaml

from aosconfig.differ import diff_configs
from aosconfig.models import AirportConfig

SAMPLE = Path(__file__).resolve().parents[3] / "config" / "airport.yaml"


@pytest.fixture
def raw():
    return yaml.safe_load(SAMPLE.read_text())


def test_first_install_adds_everything(raw):
    changes = diff_configs(None, AirportConfig(**raw))
    assert all(c.kind == "added" for c in changes)
    assert len(changes) == 12


def test_same_config_has_no_changes(raw):
    cfg = AirportConfig(**raw)
    assert diff_configs(cfg, cfg) == []


def test_added_gate_is_reported(raw):
    old = AirportConfig(**raw)
    raw["gates"].append({"id": "B3", "terminal": "T2"})
    new = AirportConfig(**raw)

    changes = diff_configs(old, new)

    assert len(changes) == 1
    assert changes[0].kind == "added"
    assert changes[0].section == "gates"
    assert changes[0].key == "B3"


def test_removed_gate_is_reported(raw):
    old = AirportConfig(**raw)
    raw["gates"] = [g for g in raw["gates"] if g["id"] != "B2"]
    new = AirportConfig(**raw)

    changes = diff_configs(old, new)

    assert len(changes) == 1
    assert changes[0].kind == "removed"
    assert changes[0].section == "gates"
    assert changes[0].key == "B2"


def test_removed_airline_gate_is_reported_as_change(raw):
    old = AirportConfig(**raw)
    raw["airlines"][0]["gates"].remove("A2")
    new = AirportConfig(**raw)

    changes = diff_configs(old, new)

    assert len(changes) == 1
    assert changes[0].kind == "changed"
    assert changes[0].section == "airlines"
    assert changes[0].key == "TK"
    assert "-A2" in changes[0].detail


def test_moving_an_item_in_the_file_is_not_a_change(raw):
    """Items are matched by id, so a different order is not a difference."""
    old = AirportConfig(**raw)
    raw["gates"].reverse()
    new = AirportConfig(**raw)
    assert diff_configs(old, new) == []
