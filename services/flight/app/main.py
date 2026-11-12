from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.gates import rules
from app.store import Flight, FlightExists, store_from_env

app = FastAPI(title="Flight Service")


class FlightUpdate(BaseModel):
    gate: Optional[str] = None


# PostgreSQL when DB_HOST is set (the Helm chart sets it), otherwise in memory.
store = store_from_env()


def check_gate(flight_no: str, gate: Optional[str]) -> None:
    """Reject a gate that the airport config does not allow (422)."""
    problem = rules.problem(flight_no, gate)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Ready only when the database answers. Liveness stays on /health so a database
    outage takes pods out of the Service but does not restart them."""
    try:
        store.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="database not reachable")
    return {"status": "ready"}


@app.get("/flights")
def list_flights():
    return store.list()


@app.post("/flights", status_code=201)
def create_flight(flight: Flight):
    check_gate(flight.flight_no, flight.gate)
    try:
        store.add(flight)
    except FlightExists:
        raise HTTPException(status_code=409, detail="Flight already exists")
    return flight


@app.patch("/flights/{flight_no}")
def update_flight(flight_no: str, update: FlightUpdate):
    if not store.exists(flight_no):
        raise HTTPException(status_code=404, detail="Flight not found")
    check_gate(flight_no, update.gate)
    flight = store.set_gate(flight_no, update.gate)
    if flight is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return flight