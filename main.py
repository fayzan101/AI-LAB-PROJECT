import time

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import init_db, is_db_ready
from errors import get_error_code
from observability import (
    get_request_id,
    log_request,
    metrics_response,
    observe_request,
    request_context_middleware,
)
from rate_limit import RateLimiter
from routes import analytics, auth, employee, reports, tasks

app = FastAPI(title=settings.app_name)
app.state.startup_complete = False
app.state.started_at = int(time.time())
app.state.rate_limiter = RateLimiter(
    window_seconds=settings.rate_limit_window_seconds,
    max_requests=settings.rate_limit_max_requests,
    redis_url=settings.redis_url,
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(employee.router, prefix=settings.api_prefix)
app.include_router(analytics.router, prefix=settings.api_prefix)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    app.state.startup_complete = True


@app.middleware("http")
async def request_logging_and_rate_limit(request: Request, call_next):
    start = time.perf_counter()
    request_context_middleware(request)
    path = request.url.path
    exempt_paths = {"/", "/health/live", "/health/ready", "/health/startup", f"{settings.api_prefix}/auth/login", "/metrics"}

    if path not in exempt_paths:
        client_ip = request.client.host if request.client else "unknown"
        if app.state.rate_limiter.is_limited(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "status": "error",
                    "message": "Rate limit exceeded",
                    "error_code": get_error_code(status.HTTP_429_TOO_MANY_REQUESTS),
                    "trace_id": get_request_id(),
                    "data": {},
                    "meta": {
                        "window_seconds": settings.rate_limit_window_seconds,
                        "max_requests": settings.rate_limit_max_requests,
                    },
                },
            )

    response = await call_next(request)
    duration_seconds = time.perf_counter() - start
    trace_id = get_request_id()
    response.headers["x-trace-id"] = trace_id
    observe_request(request.method, path, response.status_code, duration_seconds)
    log_request(request.method, path, response.status_code, duration_seconds * 1000, trace_id)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": "Validation failed",
            "error_code": get_error_code(status.HTTP_422_UNPROCESSABLE_ENTITY),
            "trace_id": getattr(request.state, "request_id", ""),
            "data": {},
            "meta": {"errors": exc.errors()},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": str(exc.detail),
            "error_code": get_error_code(exc.status_code),
            "trace_id": getattr(request.state, "request_id", ""),
            "data": {},
            "meta": None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, __: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "Unexpected internal server error",
            "error_code": get_error_code(status.HTTP_500_INTERNAL_SERVER_ERROR),
            "trace_id": getattr(request.state, "request_id", ""),
            "data": {},
            "meta": None,
        },
    )


@app.get("/")
def home():
    return {"message": "FastAPI AI System Running"}


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    startup_ok = bool(app.state.startup_complete)
    db_ok = is_db_ready()
    ready = startup_ok and db_ok
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ready else "degraded",
            "startup_complete": startup_ok,
            "database_ready": db_ok,
        },
    )


@app.get("/health/startup")
def health_startup():
    return {
        "status": "ok" if app.state.startup_complete else "starting",
        "startup_complete": bool(app.state.startup_complete),
        "started_at_epoch": app.state.started_at,
    }


@app.get("/metrics")
def metrics():
    return metrics_response()