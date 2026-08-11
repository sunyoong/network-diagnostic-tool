from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core.auth_deps import require_csrf, require_current_user
from app.core.config import get_settings
from app.core.deps import get_real_client_ip
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.schemas.response import error_response, success_response
from app.services.auth_service import authenticate, change_password, revoke_session

router = APIRouter()


def _cookie_names() -> tuple[str, str]:
    settings = get_settings()
    session_name = settings.session_cookie_name
    if not settings.cookie_secure and session_name.startswith("__Host-"):
        session_name = "netprobe_session"
    return session_name, settings.csrf_cookie_name


@router.post("/login")
async def login(payload: LoginRequest, request: Request):
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail={"code": "AUTH_DISABLED", "message": "로그인 기능이 비활성화되어 있습니다."})
    result = await authenticate(payload.username, payload.password, get_real_client_ip(request), request.headers.get("user-agent"))
    request_id = str(uuid.uuid4())
    if result is None:
        return JSONResponse(
            status_code=401,
            content=error_response("AUTHENTICATION_FAILED", "아이디 또는 비밀번호를 확인해 주세요.", request_id, 0),
        )
    context, token, csrf_token = result
    response = JSONResponse(
        content=success_response(
            {
                "user": {
                    "id": str(context.user_id),
                    "username": context.username,
                    "display_name": context.display_name,
                    "role": context.role,
                },
                "must_change_password": context.must_change_password,
            },
            request_id,
            0,
        )
    )
    session_cookie, csrf_cookie = _cookie_names()
    max_age = (settings.admin_session_absolute_hours if context.role == "ADMIN" else settings.session_absolute_hours) * 3600
    response.set_cookie(session_cookie, token, max_age=max_age, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
    response.set_cookie(csrf_cookie, csrf_token, max_age=max_age, httponly=False, secure=settings.cookie_secure, samesite="lax", path="/")
    return response


@router.get("/me")
async def me(request: Request, context=Depends(require_current_user)):
    if context is None:
        return success_response({"authenticated": False, "auth_enabled": False}, str(uuid.uuid4()), 0)
    return success_response(
        {
            "authenticated": True,
            "user": {
                "id": str(context.user_id),
                "username": context.username,
                "display_name": context.display_name,
                "role": context.role,
            },
            "must_change_password": context.must_change_password,
        },
        str(uuid.uuid4()),
        0,
    )


@router.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(request: Request, context=Depends(require_current_user)):
    if context is not None:
        await revoke_session(context.session_id, context.user_id)
    response = JSONResponse(content=success_response({"logged_out": True}, str(uuid.uuid4()), 0))
    session_cookie, csrf_cookie = _cookie_names()
    response.delete_cookie(session_cookie, path="/")
    response.delete_cookie(csrf_cookie, path="/")
    return response


@router.post("/change-password", dependencies=[Depends(require_csrf)])
async def update_password(payload: ChangePasswordRequest, context=Depends(require_current_user)):
    if context is None:
        raise HTTPException(status_code=404, detail="인증 기능이 비활성화되어 있습니다.")
    try:
        changed = await change_password(context, payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "PASSWORD_POLICY_VIOLATION", "message": str(exc)}) from exc
    if not changed:
        raise HTTPException(status_code=401, detail={"code": "AUTHENTICATION_FAILED", "message": "현재 비밀번호를 확인해 주세요."})
    return success_response({"password_changed": True}, str(uuid.uuid4()), 0)
