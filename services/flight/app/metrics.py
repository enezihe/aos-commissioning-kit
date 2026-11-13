"""Request metrics in the Prometheus text format.

Two metrics, enough to answer "how many, how many failed, how slow":
- http_requests_total             counter, by method, path and status code
- http_request_duration_seconds   histogram, by method and path

The path label is the route template (/flights/{flight_no}), never the real address,
so one flight number does not become one time series. Requests that match no route
are counted under "unmatched" for the same reason.

Each pod keeps its own numbers in memory. Prometheus scrapes every pod and adds them up.
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

METRICS_PATH = "/metrics"

REQUESTS = Counter(
    "http_requests_total",
    "Requests handled, by method, route and status code.",
    ["method", "path", "status"],
)

# Buckets in seconds. Most answers take a few milliseconds; the upper buckets show a slow database.
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time to answer a request, by method and route.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


async def record_request(request: Request, call_next):
    """Middleware: count and time every request except the scrape itself."""
    if request.url.path == METRICS_PATH:
        return await call_next(request)

    start = time.perf_counter()
    status = 500                                  # an exception that escapes the handler is a 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        path = _route_template(request)
        REQUESTS.labels(request.method, path, str(status)).inc()
        LATENCY.labels(request.method, path).observe(time.perf_counter() - start)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
