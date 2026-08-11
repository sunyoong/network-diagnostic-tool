from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request

from app.core.auth import AuthContext
from app.core.config import get_settings
from app.services.auth_service import csrf_matches, resolve_session


async def require_current_user(request: Request) -> AuthContext | None:
    settings = get_settings()
    if not settings.auth_enabled:
        request.state.current_user = None
        return None
    cookie_name = settings.session_cookie_name
    if not settings.cookie_secure and cookie_name.startswith("__Host-"):
        cookie_name = "netprobe_session"
    token = request.cookies.get(cookie_name)
    if not token:
        raise HTTPException(401, detail={"code": "AUTHENTICATION_REQUIRED", "message": "로그인이 필요합니다."})
    context = await resolve_session(token)
    if context is None:
        raise HTTPException(401, detail={"code": "SESSION_EXPIRED", "message": "로그인 세션이 만료되었습니다."})
    request.state.current_user = context
    return context


async def require_csrf(request: Request) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return
    context = getattr(request.state, "current_user", None) or await require_current_user(request)
    header_token = request.headers.get("x-csrf-token")
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not header_token or not cookie_token or header_token != cookie_token or not await csrf_matches(context.session_id, header_token):
        raise HTTPException(403, detail={"code": "CSRF_VALIDATION_FAILED", "message": "요청 보안 검증에 실패했습니다."})


def require_roles(*roles: str) -> Callable:
    async def dependency(request: Request) -> AuthContext | None:
        context = await require_current_user(request)
        if context is None:
            return None
        if context.must_change_password:
            raise HTTPException(403, detail={"code": "PASSWORD_CHANGE_REQUIRED", "message": "비밀번호 변경이 필요합니다."})
        if context.role not in roles:
            raise HTTPException(403, detail={"code": "PERMISSION_DENIED", "message": "요청 권한이 없습니다."})
        return context
    return dependency
