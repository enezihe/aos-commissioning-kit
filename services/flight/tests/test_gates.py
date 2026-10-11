import os

import pytest
from fastapi.testclient import TestClient

from app import main
from app.gates import GateRules

CONFIG = """
airport: {code: GLB, name: Test}
terminals: [{id: T1, name: Domestic}]
gates:
  - {id: A1, terminal: T1}
  - {id: A2, terminal: T1}
  - {id: A3, terminal: T1}
carousels: []
airlines:
  - {code: TK, name: Example Air, gates: [A1, A2]}
  - {code: PC, name: Sample Wings, gates: [A3]}
"""

FLIGHT = {"flight_no": "TK1234", "origin": "IST", "destination": "ESB"}


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "airport.yaml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def client(config_file, monkeypatch):
    """A client whose service reads gate rules from a temporary config file."""
    monkeypatch.setattr(main, "rules", GateRules(str(config_file)))
    main.flights.clear()
    return TestClient(main.app)


def test_without_a_config_file_nothing_is_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "rules", GateRules(str(tmp_path / "missing.yaml")))
    main.flights.clear()
    response = TestClient(main.app).post("/flights", json={**FLIGHT, "gate": "ANYTHING"})
    assert response.status_code == 201


def test_flight_without_a_gate_is_fine(client):
    assert client.post("/flights", json=FLIGHT).status_code == 201


def test_known_gate_for_the_airline_is_accepted(client):
    assert client.post("/flights", json={**FLIGHT, "gate": "A1"}).status_code == 201


def test_unknown_gate_is_rejected(client):
    response = client.post("/flights", json={**FLIGHT, "gate": "Z9"})
    assert response.status_code == 422
    assert response.json()["detail"] == "unknown gate Z9"


def test_gate_of_another_airline_is_rejected(client):
    response = client.post("/flights", json={**FLIGHT, "gate": "A3"})   # A3 belongs to PC
    assert response.status_code == 422
    assert response.json()["detail"] == "gate A3 is not allowed for airline TK"


def test_patch_with_a_bad_gate_is_rejected_and_nothing_changes(client):
    client.post("/flights", json={**FLIGHT, "gate": "A1"})
    response = client.patch("/flights/TK1234", json={"gate": "Z9"})
    assert response.status_code == 422
    assert client.get("/flights").json()[0]["gate"] == "A1"


def test_patch_on_a_missing_flight_is_still_404(client):
    assert client.patch("/flights/TK0000", json={"gate": "A1"}).status_code == 404


def test_a_changed_config_is_used_without_restarting(client, config_file):
    assert client.post("/flights", json={**FLIGHT, "gate": "B9"}).status_code == 422

    config_file.write_text(CONFIG.replace("[A1, A2]", "[A1, A2, B9]").replace(
        "  - {id: A3, terminal: T1}", "  - {id: A3, terminal: T1}\n  - {id: B9, terminal: T1}"))
    stat = os.stat(config_file)
    os.utime(config_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))  # force a new timestamp

    assert client.post("/flights", json={**FLIGHT, "gate": "B9"}).status_code == 201


def test_a_broken_config_is_ignored_and_the_service_keeps_working(client, config_file):
    config_file.write_text("gates: [this is: not valid")
    response = client.post("/flights", json={**FLIGHT, "gate": "Z9"})
    assert response.status_code == 201
