# PostgreSQL·로그인 기능 사용 방법

[`postgresql-database-spec.md`](../specifications/postgresql-database-spec.md)와 [`authentication-account-spec.md`](../specifications/authentication-account-spec.md)를 구현한 기능의 실행 절차입니다. Python 3.12와 PostgreSQL 16 이상을 권장합니다.

데이터 접근은 ORM 없이 `asyncpg` 연결 풀과 `$1`, `$2` 바인딩 파라미터를 사용한 직접 SQL 방식입니다. 스키마 변경은 `migrations` 폴더의 번호순 SQL 파일과 `schema_migrations` 테이블로 관리합니다.

## 1. 가상환경과 패키지 설치

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.venv`는 현재 프로젝트 디렉터리 내부에 만들어집니다.

## 2. PostgreSQL 준비

관리자 계정으로 `psql`에 접속하여 실행합니다. 예시 비밀번호는 실제로 사용하지 마세요.

```sql
CREATE ROLE netprobe_app LOGIN PASSWORD '강력한-실제-비밀번호';
CREATE DATABASE netprobe OWNER netprobe_app ENCODING 'UTF8';
REVOKE ALL ON DATABASE netprobe FROM PUBLIC;
GRANT CONNECT ON DATABASE netprobe TO netprobe_app;
```

`.env`를 수정합니다. 비밀번호에 특수문자가 있으면 URL 인코딩해야 합니다.

```dotenv
NDT_DATABASE_ENABLED=true
NDT_DIAGNOSTIC_PERSISTENCE_ENABLED=true
NDT_DATABASE_URL=postgresql://netprobe_app:URL인코딩된비밀번호@127.0.0.1:5432/netprobe
NDT_CLIENT_HASH_SECRET=충분히-긴-임의문자열
NDT_SESSION_TOKEN_PEPPER=서로-다른-긴-임의문자열
NDT_PASSWORD_PEPPER=또-다른-긴-임의문자열
NDT_COOKIE_SECURE=false
```

문자열 생성 예시:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 3. 테이블과 최초 관리자 생성

```powershell
python -m app.cli migrate
python -m app.cli create-admin --username admin --display-name "관리자" --email admin@example.com
```

관리자 생성 명령은 비밀번호를 숨겨 입력받습니다. 비밀번호는 12~128자이며 아이디를 포함할 수 없습니다. 생성 후 `.env`에서 로그인을 켭니다.

새 스키마 변경은 `migrations/002_설명.sql`처럼 다음 번호의 SQL 파일로 추가한 후 `python -m app.cli migrate`를 다시 실행합니다. 적용 완료된 파일은 수정하지 않습니다.

```dotenv
NDT_AUTH_ENABLED=true
```

## 4. 웹 서버 실행

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

[http://localhost:8000](http://localhost:8000)에 접속하면 로그인 화면으로 이동합니다. API 문서는 `/docs`, 준비 상태는 `/health/ready`에서 확인합니다.

## 권한

- `ADMIN`: 계정 관리, 진단 실행, 전체 이력 조회
- `OPERATOR`: 진단 실행, 본인 이력 조회
- `VIEWER`: 본인 이력과 접속 정보 조회

관리 API는 `/api/v1/admin/users`, 인증은 `/api/v1/auth`, 이력은 `/api/v1/diagnostics` 아래에 있습니다. 브라우저는 세션 쿠키와 CSRF 토큰을 자동으로 전송합니다.

## 운영 환경 필수 사항

- HTTPS 적용 후 `NDT_COOKIE_SECURE=true`로 변경합니다.
- `.env`는 커밋하지 말고 비밀 관리 도구에 보관합니다.
- 정기 백업과 보존 기간이 지난 진단·감사 데이터 정리 작업을 운영합니다.

## DB 없이 실행

아래 값을 유지하면 기존처럼 로그인과 저장 없이 실행됩니다.

```dotenv
NDT_DATABASE_ENABLED=false
NDT_DIAGNOSTIC_PERSISTENCE_ENABLED=false
NDT_AUTH_ENABLED=false
```

DB 저장 실패는 진단 자체를 중단하지 않고 `DATABASE_WRITE_FAILED` 로그를 남깁니다. 인증 활성화 상태에서 DB가 끊기면 보호 API는 안전하게 실패합니다.
