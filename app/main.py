from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin_users, auth, client_info, dns_lookup, history, http_check, port_check
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import database_ready, dispose_engine
from app.schemas.response import error_response

configure_logging()
logger = get_logger("ndt.app")
settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    description="HTTP, TCP 포트, DNS 및 접속 정보를 진단하는 서비스",
    version=settings.app_version,
    lifespan=lifespan,
)

if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=settings.auth_enabled,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )


@app.middleware("http")
async def response_middleware(request: Request, call_next):
    start = time.monotonic()
    request.state.start_time = start
    response = await call_next(request)
    response.headers["X-Response-Time-ms"] = str(int((time.monotonic() - start) * 1000))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _elapsed_ms(request: Request) -> int:
    start = getattr(request.state, "start_time", None)
    return int((time.monotonic() - start) * 1000) if start is not None else 0


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = str(uuid.uuid4())
    messages = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(status_code=422, content=error_response("VALIDATION_ERROR", messages, request_id, _elapsed_ms(request)))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = str(uuid.uuid4())
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = detail.get("code", "INTERNAL_SERVER_ERROR" if exc.status_code >= 500 else "VALIDATION_ERROR")
    message = detail.get("message", str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=error_response(code, message, request_id, _elapsed_ms(request)))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.error(f"path={request.url.path} request_id={request_id} error={type(exc).__name__}")
    return JSONResponse(status_code=500, content=error_response("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", request_id, _elapsed_ms(request)))


app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(admin_users.router, prefix="/api/v1/admin/users", tags=["admin-users"])
app.include_router(history.router, prefix="/api/v1/diagnostics", tags=["diagnostic-history"])
app.include_router(http_check.router, prefix="/api/v1", tags=["http-check"])
app.include_router(port_check.router, prefix="/api/v1", tags=["port-check"])
app.include_router(dns_lookup.router, prefix="/api/v1", tags=["dns-lookup"])
app.include_router(client_info.router, prefix="/api/v1", tags=["client-info"])


@app.get("/health")
@app.get("/health/live")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness():
    if settings.database_enabled and not await database_ready():
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return {"status": "ready", "database": "enabled" if settings.database_enabled else "disabled"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/login")
async def login_page():
    if not settings.auth_enabled:
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/")
async def index(request: Request):
    cookie_name = settings.session_cookie_name
    if not settings.cookie_secure and cookie_name.startswith("__Host-"):
        cookie_name = "netprobe_session"
    if settings.auth_enabled and not request.cookies.get(cookie_name):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")
