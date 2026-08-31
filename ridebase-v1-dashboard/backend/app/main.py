"""RideBase V1 Intelligence - prediction + analytics API."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .artifacts import get_store
from .config import settings
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ridebase.api")

app = FastAPI(
    title="RideBase V1 Intelligence API",
    version="1.0.0",
    description="Next-service days/km prediction + model analytics on RideBase Synthetic Dataset v1.3.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    # published Claude artifacts run from a per-artifact *.claudeusercontent.com origin
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def observability(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > settings.MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413, content={"detail": "request too large"})
        except ValueError:
            pass
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # pragma: no cover - handled by exception handlers below too
        log.exception("request_id=%s method=%s path=%s UNHANDLED", rid, request.method, request.url.path)
        raise
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    # technical metadata only - never the request payload
    log.info("request_id=%s method=%s path=%s status=%s latency_ms=%s model_gen=%s",
             rid, request.method, request.url.path, response.status_code, latency_ms,
             getattr(get_store(), "generation", "?"))
    response.headers["x-request-id"] = rid
    response.headers["x-response-time-ms"] = str(latency_ms)
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exc(_: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exc(_: Request, exc: Exception):  # no stack trace to the client
    log.exception("unhandled: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


@app.on_event("startup")
def _startup():
    store = get_store(reload=True)
    h = store.health()
    log.info("artifacts loaded: generation=%s health=%s leakage=%s errors=%s",
             store.generation, h["status"], h["leakage_guard"], h["errors"])
    from .v2_service import init_v2, v2_loaded
    init_v2()
    log.info("v2 survival bundle loaded=%s", v2_loaded())


app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "RideBase V1 Intelligence API", "docs": "/docs", "health": "/health"}
