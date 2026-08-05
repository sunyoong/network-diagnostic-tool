from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings

DnsRecordType = Literal["A", "AAAA", "CNAME", "MX", "TXT", "NS"]
HttpMethod = Literal["GET", "HEAD"]


class HttpCheckRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    method: HttpMethod = "GET"
    timeout_seconds: float = Field(default=5.0, ge=1, le=10)
    follow_redirects: bool = True

    @field_validator("timeout_seconds")
    @classmethod
    def clamp_timeout(cls, v: float) -> float:
        settings = get_settings()
        if v > settings.max_http_timeout_seconds:
            raise ValueError(
                f"timeout_seconds는 {settings.max_http_timeout_seconds}초를 초과할 수 없습니다."
            )
        return v


class PortCheckRequest(BaseModel):
    host: str = Field(..., max_length=253)
    port: int = Field(..., ge=1, le=65535)
    timeout_seconds: float = Field(default=3.0, ge=1, le=10)

    @field_validator("timeout_seconds")
    @classmethod
    def clamp_timeout(cls, v: float) -> float:
        settings = get_settings()
        if v > settings.max_tcp_timeout_seconds:
            raise ValueError(
                f"timeout_seconds는 {settings.max_tcp_timeout_seconds}초를 초과할 수 없습니다."
            )
        return v


class DnsLookupRequest(BaseModel):
    domain: str = Field(..., max_length=253)
    record_type: DnsRecordType = "A"
