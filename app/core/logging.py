"""로깅 설정.

요청 ID, API 경로, 처리 결과, 처리시간, 클라이언트 IP를 기록한다.
비밀번호, Authorization, Cookie는 기록하지 않는다.
"""
from __future__ import annotations

import logging
import re
import sys

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
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt='%(asctime)s level=%(levelname)s logger=%(name)s msg="%(message)s"',
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # 접근 로그 등 너무 시끄러운 서드파티 로거는 WARNING으로 조정
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
