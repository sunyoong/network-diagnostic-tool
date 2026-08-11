from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,48}[a-z0-9]$")
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    session_id: uuid.UUID
    username: str
    display_name: str
    role: str
    must_change_password: bool


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("아이디는 영문 소문자, 숫자, '.', '_', '-'를 사용한 3~50자여야 합니다.")
    return username


def validate_password(password: str, username: str | None = None) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError(f"비밀번호는 {PASSWORD_MIN_LENGTH}~{PASSWORD_MAX_LENGTH}자여야 합니다.")
    if username and username.lower() in password.lower():
        raise ValueError("비밀번호에 아이디를 포함할 수 없습니다.")


def _peppered(password: str) -> str:
    return f"{password}{get_settings().password_pepper}"


def hash_password(password: str) -> str:
    return _password_hasher.hash(_peppered(password))


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _password_hasher.verify(encoded_hash, _peppered(password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    pepper = get_settings().session_token_pepper
    return hashlib.sha256(f"{token}{pepper}".encode("utf-8")).hexdigest()


def hash_client_ip(ip: str) -> str | None:
    secret = get_settings().client_hash_secret
    if not secret or not ip or ip == "unknown":
        return None
    return hmac.new(secret.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()


def summarize_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    return cleaned[:255]
