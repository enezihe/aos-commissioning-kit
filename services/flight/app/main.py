from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.gates import rules

app = FastAPI(title="Flight Service")


class Flight(BaseModel):
    flight_no: str
    origin: str
    destination: str
    gate: Optional[str] = None


class FlightUpdate(BaseModel):
    gate: Optional[str] = None


flights: Dict[str, Flight] = {}


def check_gate(flight_no: str, gate: Optional[str]) -> None:
    """Reject a gate that the airport config does not allow (422)."""
    problem = rules.problem(flight_no, gate)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/flights")
def list_flights():
    return list(flights.values())


@app.post("/flights", status_code=201)
def create_flight(flight: Flight):
    check_gate(flight.flight_no, flight.gate)
    if flight.flight_no in flights:
        raise HTTPException(status_code=409, detail="Flight already exists")
    flights[flight.flight_no] = flight
    return flight


@app.patch("/flights/{flight_no}")
def update_flight(flight_no: str, update: FlightUpdate):
    flight = flights.get(flight_no)
    if flight is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    check_gate(flight_no, update.gate)
    flight.gate = update.gate
    return flight