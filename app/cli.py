from __future__ import annotations

import argparse
import asyncio
import getpass
import uuid

import asyncpg

from app.core.auth import hash_password, normalize_username, validate_password
from app.db.migrations import migrate
from app.db.session import dispose_engine, get_pool


async def create_admin(username: str, display_name: str, email: str | None) -> None:
    username = normalize_username(username)
    password = getpass.getpass("초기 비밀번호: "); confirm = getpass.getpass("초기 비밀번호 확인: ")
    if password != confirm: raise SystemExit("비밀번호가 일치하지 않습니다.")
    validate_password(password, username); pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO user_accounts(id,username,email,display_name,password_hash,role,status,must_change_password)
                VALUES($1,$2,$3,$4,$5,'ADMIN','ACTIVE',true)""",
                uuid.uuid4(), username, email, display_name.strip(), hash_password(password),
            )
    except asyncpg.UniqueViolationError as exc:
        raise SystemExit("이미 존재하는 아이디 또는 이메일입니다.") from exc
    print(f"관리자 계정 '{username}'을 생성했습니다. 첫 로그인 후 비밀번호를 변경하세요.")


async def run(args) -> None:
    if args.command == "migrate":
        applied = await migrate()
        print("적용된 마이그레이션: " + (", ".join(applied) if applied else "없음"))
    else:
        await create_admin(args.username, args.display_name, args.email)


def main() -> None:
    parser = argparse.ArgumentParser(description="Network Diagnostic Tool 관리 명령")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="미적용 SQL 마이그레이션 실행")
    create = sub.add_parser("create-admin", help="최초 관리자 계정 생성")
    create.add_argument("--username", required=True); create.add_argument("--display-name", required=True); create.add_argument("--email")
    args = parser.parse_args()
    try: asyncio.run(run(args))
    finally: asyncio.run(dispose_engine())


if __name__ == "__main__": main()
