"""애플리케이션 설정.

환경 변수(.env)로 오버라이드 가능한 값들을 정의한다.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NDT_", extra="ignore")

    # 서버
    app_name: str = "Network Diagnostic Tool"
    environment: str = "development"  # development | production
    log_level: str = "INFO"
    log_file: str = "logs/network-diagnostic.log"

    # CORS (분리 배포 시에만 사용)
    cors_allowed_origins: List[str] = Field(default_factory=list)

    # 신뢰 프록시 (X-Forwarded-For 신뢰 여부 판단에 사용)
    trusted_proxy_ips: List[str] = Field(default_factory=list)

    # 진단 공통 제한
    default_http_timeout_seconds: float = 5.0
    max_http_timeout_seconds: float = 10.0
    default_tcp_timeout_seconds: float = 3.0
    max_tcp_timeout_seconds: float = 10.0
    max_redirects: int = 5
    max_response_bytes: int = 1_000_000  # 1MB, 본문 미리보기 상한

    # 동시성 제한
    max_concurrent_diagnostics: int = 20

    # 요청 횟수 제한 (분당)
    rate_limit_per_minute: int = 30

    # 허용 TCP 포트 (공개 서비스 기준)
    allowed_tcp_ports: List[int] = Field(
        default_factory=lambda: [22, 53, 80, 443, 5432, 3306, 6379, 8080]
    )

    # 사설/내부 대역 접근 허용 여부 (사내 진단용, 기본은 차단)
    allow_private_targets: bool = False

    # 허용 도메인/IP 대역 화이트리스트 (비어있으면 전체 허용, allow_private 정책과 별개로 적용)
    allowed_target_domains: List[str] = Field(default_factory=list)

    # PostgreSQL
    database_enabled: bool = False
    diagnostic_persistence_enabled: bool = False
    database_url: str = "postgresql://netprobe_app:CHANGE_ME@127.0.0.1:5432/netprobe"
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_pool_timeout_seconds: float = 5.0
    database_statement_timeout_ms: int = 5000
    diagnostic_retention_days: int = 90
    audit_retention_days: int = 180
    auth_audit_retention_days: int = 365
    store_raw_client_ip: bool = False
    client_hash_secret: str = ""

    # 로그인·세션
    auth_enabled: bool = False
    session_cookie_name: str = "__Host-netprobe_session"
    csrf_cookie_name: str = "netprobe_csrf"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    admin_session_absolute_hours: int = 4
    max_sessions_per_user: int = 5
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    password_history_count: int = 5
    session_token_pepper: str = ""
    password_pepper: str = ""
    cookie_secure: bool = True
    app_version: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
