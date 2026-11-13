"""Storage layer tests.

The same behaviour is checked against both stores. The PostgreSQL run needs a real database:
set TEST_DB_HOST (and optionally TEST_DB_PORT, TEST_DB_USER, TEST_DB_PASSWORD, TEST_DB_NAME).
Without it those tests are skipped; CI starts a PostgreSQL container and runs them.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app import main
from app.gates import GateRules
from app.store import Flight, FlightExists, MemoryStore, PostgresStore, store_from_env

FLIGHT = Flight(flight_no="TK1234", origin="IST", destination="ESB")

DB_SETTINGS = dict(
    host=os.environ.get("TEST_DB_HOST"),
    port=int(os.environ.get("TEST_DB_PORT", "5432")),
    user=os.environ.get("TEST_DB_USER", "flight"),
    password=os.environ.get("TEST_DB_PASSWORD", "flight"),
    dbname=os.environ.get("TEST_DB_NAME", "flight"),
)


def make_postgres():
    if not DB_SETTINGS["host"]:
        pytest.skip("TEST_DB_HOST is not set")
    store = PostgresStore(**DB_SETTINGS)
    with store._connect() as db:
        db.execute("TRUNCATE flights")
    return store


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    return MemoryStore() if request.param == "memory" else make_postgres()


def test_a_new_store_is_empty(store):
    assert store.list() == []


def test_added_flight_is_listed(store):
    store.add(FLIGHT)
    assert store.list() == [FLIGHT]
    assert store.exists("TK1234")
    assert not store.exists("TK0000")


def test_adding_the_same_flight_twice_is_refused(store):
    store.add(FLIGHT)
    with pytest.raises(FlightExists):
        store.add(FLIGHT)
    assert len(store.list()) == 1


def test_gate_can_be_set_and_cleared(store):
    store.add(FLIGHT)
    assert store.set_gate("TK1234", "A1").gate == "A1"
    assert store.list()[0].gate == "A1"
    assert store.set_gate("TK1234", None).gate is None


def test_setting_a_gate_on_a_missing_flight_returns_none(store):
    assert store.set_gate("TK0000", "A1") is None


def test_postgres_data_is_shared_between_two_store_objects():
    """Two replicas are two store objects pointing at the same database."""
    first = make_postgres()
    second = PostgresStore(**DB_SETTINGS)
    first.add(FLIGHT)
    assert second.list() == [FLIGHT]


def test_postgres_data_survives_a_new_store_object():
    """A restarted pod builds a new store object; the data must still be there."""
    make_postgres().add(FLIGHT)
    assert PostgresStore(**DB_SETTINGS).list() == [FLIGHT]


def test_without_db_host_the_memory_store_is_used():
    assert isinstance(store_from_env({}), MemoryStore)


def test_db_host_without_credentials_fails_with_a_clear_message():
    with pytest.raises(RuntimeError, match="DB_USER, DB_PASSWORD, DB_NAME"):
        store_from_env({"DB_HOST": "db"})


def test_ready_is_503_when_the_database_is_not_reachable(monkeypatch):
    broken = PostgresStore(host="127.0.0.1", port=1, user="x", password="x", dbname="x")
    monkeypatch.setattr(main, "store", broken)
    assert TestClient(main.app).get("/ready").status_code == 503


def test_ready_is_200_with_the_memory_store(monkeypatch):
    monkeypatch.setattr(main, "store", MemoryStore())
    assert TestClient(main.app).get("/ready").status_code == 200


def test_api_works_on_top_of_postgres(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "store", make_postgres())
    monkeypatch.setattr(main, "rules", GateRules(str(tmp_path / "none.yaml")))
    client = TestClient(main.app)
    assert client.post("/flights", json=FLIGHT.model_dump()).status_code == 201
    assert client.post("/flights", json=FLIGHT.model_dump()).status_code == 409
    assert client.patch("/flights/TK1234", json={"gate": "A1"}).json()["gate"] == "A1"
    assert client.get("/flights").json()[0]["gate"] == "A1"
