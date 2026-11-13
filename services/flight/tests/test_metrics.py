import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import main
from app.gates import GateRules

FLIGHT = {"flight_no": "TK1234", "origin": "IST", "destination": "ESB"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "rules", GateRules(str(tmp_path / "missing.yaml")))
    main.store.clear()
    return TestClient(main.app, raise_server_exceptions=False)


def count(method: str, path: str, status: str) -> float:
    """The counter's value now. The registry lives as long as the process, so tests compare before and after."""
    value = REGISTRY.get_sample_value("http_requests_total", {"method": method, "path": path, "status": status})
    return value or 0.0


def observed(method: str, path: str) -> float:
    value = REGISTRY.get_sample_value("http_request_duration_seconds_count", {"method": method, "path": path})
    return value or 0.0


def test_metrics_endpoint_answers_in_the_prometheus_text_format(client):
    client.get("/flights")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'http_requests_total{method="GET",path="/flights",status="200"}' in response.text
    assert "http_request_duration_seconds_bucket" in response.text


def test_a_request_is_counted_and_timed(client):
    before, timed = count("GET", "/flights", "200"), observed("GET", "/flights")
    client.get("/flights")
    assert count("GET", "/flights", "200") == before + 1
    assert observed("GET", "/flights") == timed + 1


def test_the_path_label_is_the_route_not_the_flight_number(client):
    client.post("/flights", json=FLIGHT)
    before = count("PATCH", "/flights/{flight_no}", "200")
    client.patch("/flights/TK1234", json={"gate": "A1"})
    assert count("PATCH", "/flights/{flight_no}", "200") == before + 1
    assert "TK1234" not in client.get("/metrics").text


def test_client_errors_keep_their_status_code(client):
    before = count("PATCH", "/flights/{flight_no}", "404")
    client.patch("/flights/XX0000", json={"gate": "A1"})
    assert count("PATCH", "/flights/{flight_no}", "404") == before + 1


def test_an_unknown_address_is_counted_as_unmatched(client):
    before = count("GET", "unmatched", "404")
    client.get("/no/such/page")
    client.get("/another/one")
    assert count("GET", "unmatched", "404") == before + 2


def test_a_failing_store_is_counted_as_a_500(client, monkeypatch):
    class BrokenStore:
        def list(self):
            raise RuntimeError("database is down")

    monkeypatch.setattr(main, "store", BrokenStore())
    before = count("GET", "/flights", "500")
    assert client.get("/flights").status_code == 500
    assert count("GET", "/flights", "500") == before + 1


def test_the_scrape_itself_is_not_counted(client):
    client.get("/metrics")
    client.get("/metrics")
    assert "/metrics" not in client.get("/metrics").text
