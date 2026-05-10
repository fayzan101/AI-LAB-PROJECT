import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

logger = logging.getLogger("ai-server")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def get_request_id() -> str:
    return request_id_ctx.get()


def request_context_middleware(request: Request):
    header_request_id = request.headers.get("x-request-id", "").strip()
    request_id = header_request_id or str(uuid.uuid4())
    request_id_ctx.set(request_id)
    request.state.request_id = request_id


def log_request(method: str, path: str, status_code: int, duration_ms: float, trace_id: str) -> None:
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "trace_id": trace_id,
            }
        )
    )


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def observe_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_seconds)
