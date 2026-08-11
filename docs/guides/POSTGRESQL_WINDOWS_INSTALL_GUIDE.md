# Windows PostgreSQL 설치 및 프로젝트 연결 가이드

## 1. 적용 버전

| 항목 | 기준 |
|---|---|
| 권장 PostgreSQL | **16.14 (64-bit)** |
| 애플리케이션 공식 기준 | PostgreSQL 16.x |
| 문법상 호환 범위 | PostgreSQL 14~18 |
| 운영체제 | Windows 10/11 64-bit |
| Python DB 드라이버 | `asyncpg >=0.30,<1.0` |

이 프로젝트는 PostgreSQL 16을 개발·운영 기준으로 삼습니다. 현재 SQL에서 사용하는 `UUID`, `INET`, `JSONB`, 배열, `RETURNING`, `FOR UPDATE`, advisory lock은 PostgreSQL 14~18에서 지원되지만, 실제 운영 검증 기준은 16.x입니다. PostgreSQL 프로젝트는 각 메이저 버전을 약 5년간 지원하며 PostgreSQL 16은 2028년 11월까지 지원됩니다.

- 공식 Windows 다운로드: <https://www.postgresql.org/download/windows/>
- 공식 버전 지원 정책: <https://www.postgresql.org/support/versioning/>

## 2. PostgreSQL 설치

1. 공식 Windows 다운로드 페이지에서 EDB 설치 프로그램을 내려받습니다.
2. PostgreSQL 16의 최신 16.x 64-bit 버전을 선택합니다.
3. 설치 구성 요소에서 다음 항목을 선택합니다.
   - PostgreSQL Server
   - pgAdmin 4
   - Command Line Tools
4. 설치 경로와 데이터 경로는 특별한 이유가 없다면 기본값을 사용합니다.
5. 관리자 계정 `postgres`의 비밀번호를 설정하고 안전하게 보관합니다.
6. 포트는 기본값 `5432`, Locale은 `Default locale`을 사용합니다.
7. 추가 확장이 필요하지 않다면 Stack Builder는 실행하지 않아도 됩니다.

## 3. 설치 확인

새 PowerShell을 열어 다음 명령을 실행합니다.

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" --version
Get-Service postgresql*
```

`psql (PostgreSQL) 16.x`가 표시되고 서비스 상태가 `Running`이면 정상입니다. 서비스가 멈춰 있다면 관리자 PowerShell에서 다음처럼 시작합니다.

```powershell
Start-Service (Get-Service postgresql* | Select-Object -First 1).Name
```

## 4. 프로젝트용 계정과 DB 생성

시작 메뉴에서 `SQL Shell (psql)`을 실행하고 다음 값으로 접속합니다.

```text
Server: localhost
Database: postgres
Port: 5432
Username: postgres
Password: 설치할 때 설정한 관리자 비밀번호
```

접속 후 아래 SQL을 실행합니다. 예시 비밀번호 대신 충분히 긴 실제 비밀번호를 사용하세요. 연결 문자열 문제를 줄이려면 처음에는 영문과 숫자 위주로 설정하는 편이 간단합니다.

```sql
CREATE ROLE netprobe_app
LOGIN
PASSWORD 'NetProbeDb2026StrongPassword';

CREATE DATABASE netprobe
OWNER netprobe_app
ENCODING 'UTF8';

REVOKE ALL ON DATABASE netprobe FROM PUBLIC;
GRANT CONNECT ON DATABASE netprobe TO netprobe_app;
```

종료 명령은 `\q`입니다.

## 5. 프로젝트 환경 설정

프로젝트 디렉터리의 PowerShell에서 실행합니다.

```powershell
Copy-Item .env.example .env
```

`.env`의 DB 관련 값을 수정합니다.

```dotenv
NDT_DATABASE_ENABLED=true
NDT_DIAGNOSTIC_PERSISTENCE_ENABLED=true
NDT_DATABASE_URL=postgresql://netprobe_app:NetProbeDb2026StrongPassword@127.0.0.1:5432/netprobe

NDT_CLIENT_HASH_SECRET=충분히-긴-임의문자열
NDT_SESSION_TOKEN_PEPPER=서로-다른-긴-임의문자열
NDT_PASSWORD_PEPPER=또-다른-긴-임의문자열

NDT_COOKIE_SECURE=false
NDT_AUTH_ENABLED=false
```

비밀 문자열은 다음 명령을 세 번 실행해 각각 다른 값으로 설정합니다.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

DB 비밀번호에 `@`, `:`, `/`, `#`, `%` 같은 문자가 들어가면 연결 문자열에서 URL 인코딩해야 합니다.

## 6. 테이블과 관리자 생성

프로젝트 가상환경에서 실행합니다.

```powershell
python -m app.cli migrate
python -m app.cli create-admin --username admin --display-name "관리자" --email admin@example.com
```

마이그레이션은 `migrations` 폴더의 번호순 SQL을 실행하고 `schema_migrations` 테이블에 적용 이력을 기록합니다. 관리자를 만든 후 `.env`에서 인증을 활성화합니다.

```dotenv
NDT_AUTH_ENABLED=true
```

## 7. 서버 실행과 확인

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 웹 화면: <http://localhost:8000>
- DB 준비 상태: <http://localhost:8000/health/ready>
- API 문서: <http://localhost:8000/docs>

정상 준비 응답은 다음과 같습니다.

```json
{
  "status": "ready",
  "database": "enabled"
}
```

## 8. 문제 해결

### `psql` 명령을 찾지 못하는 경우

전체 경로를 사용하거나 PostgreSQL의 `bin` 디렉터리를 사용자 PATH에 추가합니다.

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -U netprobe_app -d netprobe
```

### 연결 거부가 발생하는 경우

```powershell
Get-Service postgresql*
Test-NetConnection 127.0.0.1 -Port 5432
```

서비스 실행 상태, 포트, `.env` 연결 문자열을 확인합니다.

### 인증 실패가 발생하는 경우

`netprobe_app` 비밀번호와 `.env`의 비밀번호가 같은지 확인합니다. 필요하면 `postgres` 계정으로 접속해 변경합니다.

```sql
ALTER ROLE netprobe_app PASSWORD '새로운강력한비밀번호';
```

## 9. 운영 환경 주의사항

- PostgreSQL과 애플리케이션을 최신 16.x 보안 패치 버전으로 유지합니다.
- 외부에서 5432 포트를 직접 공개하지 않습니다.
- `.env`를 Git에 커밋하지 않습니다.
- HTTPS 적용 후 `NDT_COOKIE_SECURE=true`로 변경합니다.
- 데이터베이스 정기 백업과 복구 테스트를 운영합니다.
