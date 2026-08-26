"""로깅 설정.

요청 ID, API 경로, 처리 결과, 처리시간, 클라이언트 IP를 기록한다.
비밀번호, Authorization, Cookie는 기록하지 않는다.
"""
from __future__ import annotations

import logging
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

_SENSITIVE_QUERY_KEYS = re.compile(
    r"(password|passwd|token|secret|api[_-]?key|authorization)=([^&\s]+)",
    re.IGNORECASE,
)


def mask_sensitive_query(value: str) -> str:
    """URL/쿼리 문자열에서 민감 정보로 보이는 값을 마스킹한다."""
    return _SENSITIVE_QUERY_KEYS.sub(lambda m: f"{m.group(1)}=***", value)


def configure_logging() -> None:
    settings = get_settings()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(
            fmt='%(asctime)s level=%(levelname)s logger=%(name)s msg="%(message)s"',
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(JsonLinesFormatter(settings.environment))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(settings.log_level.upper())

    # 접근 로그 등 너무 시끄러운 서드파티 로거는 WARNING으로 조정
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class JsonLinesFormatter(logging.Formatter):
    """Logstash가 한 줄을 한 이벤트로 읽을 수 있는 JSON Lines formatter."""

    def __init__(self, environment: str) -> None:
        super().__init__()
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": "network-diagnostic",
            "environment": self.environment,
            "event": getattr(record, "event", "application_log"),
        }
        data.update(getattr(record, "event_fields", {}))
        if record.getMessage():
            data.setdefault("message", record.getMessage())
        if record.exc_info:
            data["error_stacktrace"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """구조화된 이벤트를 콘솔과 단일 JSON 로그 파일에 기록한다."""
    logger.log(level, event, extra={"event": event, "event_fields": fields})


def get_request_id(request: Any) -> str:
    """Return the middleware request id without trusting a client supplied value."""
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        import uuid
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    return request_id
