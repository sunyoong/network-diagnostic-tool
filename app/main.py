from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import client_info, dns_lookup, http_check, port_check
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.schemas.response import error_response

configure_logging()
logger = get_logger("ndt.app")
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="HTTP, TCP 포트, DNS 및 접속 정보를 점검하는 네트워크 진단 서비스",
    version="1.0.0",
)

if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    start = time.monotonic()
    request.state.start_time = start
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)
    response.headers["X-Response-Time-ms"] = str(duration_ms)
    return response


def _elapsed_ms(request: Request) -> int:
    start = getattr(request.state, "start_time", None)
    if start is None:
        return 0
    return int((time.monotonic() - start) * 1000)


# --- 예외 핸들러 -------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = str(uuid.uuid4())
    messages = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    logger.warning(f"path={request.url.path} request_id={request_id} result=VALIDATION_ERROR detail={messages}")
    return JSONResponse(
        status_code=422,
        content=error_response("VALIDATION_ERROR", messages or "입력값이 올바르지 않습니다.", request_id, _elapsed_ms(request)),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = str(uuid.uuid4())
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        code = exc.detail["code"]
        message = exc.detail.get("message", "요청을 처리할 수 없습니다.")
    else:
        code = "INTERNAL_SERVER_ERROR" if exc.status_code >= 500 else "VALIDATION_ERROR"
        message = str(exc.detail)
    logger.warning(f"path={request.url.path} request_id={request_id} result={code} status={exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(code, message, request_id, _elapsed_ms(request)),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.error(f"path={request.url.path} request_id={request_id} result=INTERNAL_SERVER_ERROR error={type(exc).__name__}")
    return JSONResponse(
        status_code=500,
        content=error_response("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다.", request_id, _elapsed_ms(request)),
    )


# --- 라우터 ------------------------------------------------------------------

app.include_router(http_check.router, prefix="/api/v1", tags=["http-check"])
app.include_router(port_check.router, prefix="/api/v1", tags=["port-check"])
app.include_router(dns_lookup.router, prefix="/api/v1", tags=["dns-lookup"])
app.include_router(client_info.router, prefix="/api/v1", tags=["client-info"])


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- 정적 파일 (프론트엔드) ---------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")
