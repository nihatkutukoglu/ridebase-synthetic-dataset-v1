"""RideBase V1 Intelligence - prediction + analytics API."""
from __future__ import annotations

import logging
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .artifacts import get_store, store_ready
from .config import settings
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ridebase.api")

_prod = settings.APP_ENV == "production"
app = FastAPI(
    title="RideBase V1 Intelligence API",
    version="1.0.0",
    description="Next-service days/km prediction + model analytics on RideBase Synthetic Dataset v1.3.",
    # don't expose the schema/interactive docs in production
    docs_url=None if _prod else "/docs",
    redoc_url=None if _prod else "/redoc",
    openapi_url=None if _prod else "/openapi.json",
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
             # observed, not forced: during warmup the store lock is held by the
             # warmup thread, and a log field must never stall a request
             (getattr(get_store(), "generation", "?") if store_ready() else "warming"))
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
    """Start warming models WITHOUT blocking the socket bind.

    uvicorn's ``Server.startup()`` awaits ``lifespan.startup()`` *before* it calls
    ``loop.create_server()``, so every second spent here is a second with no
    listening port. Locally that is ~2.6 s (V1 artifact store 2.1 s, V3 CatBoost
    bundle 0.4 s); on a cold free-tier instance it is far longer, and a platform
    waiting for a port sees nothing at all until it finishes.

    Loading therefore runs on a daemon thread. The port opens immediately, /health
    answers immediately and reports what is still warming, and each service keeps
    its own lazy initialisation so a request that arrives mid-warmup still works.
    ``get_store`` and the per-service ``init_*`` helpers are lock-guarded, so the
    warmup thread and an early request cannot double-load.
    """
    def _warm():
        try:
            store = get_store(reload=True)
            h = store.health()
            log.info("artifacts loaded: generation=%s health=%s leakage=%s errors=%s",
                     store.generation, h["status"], h["leakage_guard"], h["errors"])
        except Exception:
            log.exception("V1 artifact warmup failed")
        for label, loader in _WARMUP_STEPS:
            try:
                loader()
                log.info("%s warmup done", label)
            except Exception:
                log.exception("%s warmup failed", label)
        log.info("startup warmup complete")

    threading.Thread(target=_warm, name="ridebase-warmup", daemon=True).start()
    log.info("startup: warmup thread started; serving immediately")


def _warm_v2():
    from .v2_service import init_v2
    init_v2()


def _warm_v2_1():
    from .v2_1_service import init_v2_1, init_v2_1_history
    init_v2_1()
    init_v2_1_history()


def _warm_v3():
    from .v3_service import init_v3
    init_v3()


_WARMUP_STEPS = (("v2 survival bundle", _warm_v2),
                 ("v2.1 landmark predictor", _warm_v2_1),
                 ("v3 next-service-task predictor", _warm_v3))


app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "RideBase V1 Intelligence API", "docs": "/docs", "health": "/health"}
