from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class Meta(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat()
    )
    duration_ms: int = 0


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    meta: Meta


def success_response(data: Any, request_id: str, duration_ms: int) -> dict:
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": {
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "duration_ms": duration_ms,
        },
    }


def error_response(code: str, message: str, request_id: str, duration_ms: int) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
        "meta": {
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "duration_ms": duration_ms,
        },
    }


# --- 진단별 응답 데이터 모델 -------------------------------------------------


class HttpCheckData(BaseModel):
    url: str
    final_url: Optional[str] = None
    reachable: bool
    status_code: Optional[int] = None
    reason_phrase: Optional[str] = None
    resolved_ip: Optional[str] = None
    response_time_ms: int
    content_length: Optional[int] = None
    content_type: Optional[str] = None
    server: Optional[str] = None
    redirect_count: int = 0


class PortCheckData(BaseModel):
    host: str
    resolved_ips: List[str] = Field(default_factory=list)
    port: int
    open: bool
    result: str  # OPEN, REFUSED, TIMEOUT, DNS_FAILED, BLOCKED
    connection_time_ms: Optional[int] = None
    message: str


class DnsLookupData(BaseModel):
    domain: str
    record_type: str
    records: List[str] = Field(default_factory=list)
    ttl: Optional[int] = None
    resolver: Optional[str] = None
    lookup_time_ms: int


class ClientInfoData(BaseModel):
    client_ip: str
    forwarded_for: List[str] = Field(default_factory=list)
    user_agent: Optional[str] = None
    accept_language: Optional[str] = None
    protocol: str
    scheme: str
    host: str
