"""Where flights are kept.

Two stores with the same methods:
- MemoryStore: a dict inside the process. Used by the tests and when no database is configured.
- PostgresStore: a table in PostgreSQL. Every replica talks to the same database, so they share flights.

The database settings come from environment variables that Kubernetes fills from a Secret.
Nothing about the database is written into the image.
"""
import os
from typing import Dict, List, Optional, Protocol

from pydantic import BaseModel


class Flight(BaseModel):
    flight_no: str
    origin: str
    destination: str
    gate: Optional[str] = None


class FlightExists(Exception):
    pass


class FlightStore(Protocol):
    def list(self) -> List[Flight]: ...
    def exists(self, flight_no: str) -> bool: ...
    def add(self, flight: Flight) -> None: ...
    def set_gate(self, flight_no: str, gate: Optional[str]) -> Optional[Flight]: ...
    def ping(self) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._flights: Dict[str, Flight] = {}

    def list(self) -> List[Flight]:
        return list(self._flights.values())

    def exists(self, flight_no: str) -> bool:
        return flight_no in self._flights

    def add(self, flight: Flight) -> None:
        if flight.flight_no in self._flights:
            raise FlightExists(flight.flight_no)
        self._flights[flight.flight_no] = flight

    def set_gate(self, flight_no: str, gate: Optional[str]) -> Optional[Flight]:
        flight = self._flights.get(flight_no)
        if flight is not None:
            flight.gate = gate
        return flight

    def ping(self) -> None:
        return None

    def clear(self) -> None:
        self._flights.clear()


SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    flight_no   TEXT PRIMARY KEY,
    origin      TEXT NOT NULL,
    destination TEXT NOT NULL,
    gate        TEXT
)
"""


class PostgresStore:
    """Keeps flights in one PostgreSQL table. Connections are short-lived on purpose:
    a restarted database then needs no special handling in the service."""

    def __init__(self, **conn) -> None:
        self._conn = conn
        self._ready = False

    def _connect(self):
        """Open a connection; create the table the first time the database answers.
        The service can start before the database does, so nothing connects at import time."""
        import psycopg
        db = psycopg.connect(**self._conn, connect_timeout=3)
        if not self._ready:
            db.execute(SCHEMA)
            db.commit()
            self._ready = True
        return db

    def list(self) -> List[Flight]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT flight_no, origin, destination, gate FROM flights ORDER BY flight_no"
            ).fetchall()
        return [Flight(flight_no=r[0], origin=r[1], destination=r[2], gate=r[3]) for r in rows]

    def exists(self, flight_no: str) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM flights WHERE flight_no = %s", (flight_no,)).fetchone() is not None

    def add(self, flight: Flight) -> None:
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO flights (flight_no, origin, destination, gate) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (flight_no) DO NOTHING",
                (flight.flight_no, flight.origin, flight.destination, flight.gate),
            )
            if cur.rowcount == 0:
                raise FlightExists(flight.flight_no)

    def set_gate(self, flight_no: str, gate: Optional[str]) -> Optional[Flight]:
        with self._connect() as db:
            row = db.execute(
                "UPDATE flights SET gate = %s WHERE flight_no = %s "
                "RETURNING flight_no, origin, destination, gate",
                (gate, flight_no),
            ).fetchone()
        if row is None:
            return None
        return Flight(flight_no=row[0], origin=row[1], destination=row[2], gate=row[3])

    def ping(self) -> None:
        with self._connect() as db:
            db.execute("SELECT 1")


def store_from_env(env=os.environ) -> FlightStore:
    """PostgreSQL when DB_HOST is set, otherwise the in-memory store.

    DB_HOST and DB_PORT come from the chart. DB_USER, DB_PASSWORD and DB_NAME come from the Secret.
    If DB_HOST is set but the others are missing, fail at start-up with a clear message.
    """
    host = env.get("DB_HOST")
    if not host:
        return MemoryStore()
    missing = [k for k in ("DB_USER", "DB_PASSWORD", "DB_NAME") if not env.get(k)]
    if missing:
        raise RuntimeError(f"DB_HOST is set but these settings are missing: {', '.join(missing)}")
    return PostgresStore(
        host=host,
        port=int(env.get("DB_PORT", "5432")),
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
        dbname=env["DB_NAME"],
    )
