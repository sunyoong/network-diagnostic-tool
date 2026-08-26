# NetProbe API 호출 매뉴얼

실행 중인 NetProbe API를 `curl`로 빠르게 호출하기 위한 문서입니다. 기본 주소는
`http://127.0.0.1:8000`이며, Windows PowerShell에서는 `curl` 별칭과의 충돌을 피하려고
`curl.exe`를 사용합니다.

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>
- API 기본 경로: `/api/v1`

## 1. 엔드포인트 요약

| 분류 | 메서드 | 경로 | 권한 |
| --- | --- | --- | --- |
| 상태 | `GET` | `/health`, `/health/live` | 없음 |
| 상태 | `GET` | `/health/ready` | 없음 |
| HTTP 진단 | `POST` | `/api/v1/http-check` | OPERATOR, ADMIN |
| TCP 포트 진단 | `POST` | `/api/v1/port-check` | OPERATOR, ADMIN |
| DNS 조회 | `POST` | `/api/v1/dns-lookup` | OPERATOR, ADMIN |
| 접속 정보 | `GET` | `/api/v1/client-info` | VIEWER, OPERATOR, ADMIN |
| 로그인 | `POST` | `/api/v1/auth/login` | 없음 |
| 내 계정 | `GET` | `/api/v1/auth/me` | 로그인 사용자 |
| 비밀번호 변경 | `POST` | `/api/v1/auth/change-password` | 로그인 사용자 |
| 로그아웃 | `POST` | `/api/v1/auth/logout` | 로그인 사용자 |
| 진단 이력 | `GET` | `/api/v1/diagnostics` | VIEWER, OPERATOR, ADMIN |
| 진단 상세 | `GET` | `/api/v1/diagnostics/{run_id}` | VIEWER, OPERATOR, ADMIN |
| 사용자 관리 | `GET`, `POST` | `/api/v1/admin/users` | ADMIN |
| 사용자 수정 | `PATCH` | `/api/v1/admin/users/{user_id}` | ADMIN |
| 계정 작업 | `POST` | `/api/v1/admin/users/{user_id}/{action}` | ADMIN |

`NDT_AUTH_ENABLED=false`인 기본 개발 설정에서는 역할·세션·CSRF 검사가 우회되므로 아래
진단 명령을 바로 실행할 수 있습니다. 인증을 활성화했다면 먼저 7장의 로그인 절차를 수행합니다.

## 2. 서버 상태 확인

```powershell
curl.exe -sS http://127.0.0.1:8000/health
curl.exe -sS http://127.0.0.1:8000/health/ready
```

정상 응답 예시는 각각 `{"status":"ok"}`와
`{"status":"ready","database":"disabled"}`입니다.

## 3. HTTP 상태 확인

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/http-check" `
  -H "Content-Type: application/json" `
  -d '{"url":"https://example.com","method":"GET","timeout_seconds":5,"follow_redirects":true}'
```

| 필드 | 필수 | 허용값·기본값 |
| --- | --- | --- |
| `url` | 예 | `http://` 또는 `https://` URL, 최대 2048자 |
| `method` | 아니요 | `GET`(기본값), `HEAD` |
| `timeout_seconds` | 아니요 | 1~10초, 기본값 5초 |
| `follow_redirects` | 아니요 | `true`(기본값), `false` |

## 4. TCP 포트 확인

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/port-check" `
  -H "Content-Type: application/json" `
  -d '{"host":"example.com","port":443,"timeout_seconds":3}'
```

| 필드 | 필수 | 허용값·기본값 |
| --- | --- | --- |
| `host` | 예 | 도메인 또는 IP, 최대 253자 |
| `port` | 예 | 1~65535. 서버의 `NDT_ALLOWED_TCP_PORTS`에도 포함되어야 함 |
| `timeout_seconds` | 아니요 | 1~10초, 기본값 3초 |

기본 허용 포트는 `22`, `53`, `80`, `443`, `5432`, `3306`, `6379`, `8080`입니다.

## 5. DNS 레코드 조회

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/dns-lookup" `
  -H "Content-Type: application/json" `
  -d '{"domain":"example.com","record_type":"A"}'
```

| 필드 | 필수 | 허용값·기본값 |
| --- | --- | --- |
| `domain` | 예 | 도메인, 최대 253자 |
| `record_type` | 아니요 | `A`(기본값), `AAAA`, `CNAME`, `MX`, `TXT`, `NS` |

## 6. 접속 정보 확인

```powershell
curl.exe -sS "http://127.0.0.1:8000/api/v1/client-info"
```

서버가 확인한 클라이언트 IP, User-Agent, 언어, HTTP 버전과 Host 정보를 반환합니다.

## 7. 인증 활성화 환경에서 호출

로그인 응답의 세션 쿠키와 CSRF 쿠키를 `cookie.txt`에 저장합니다. 비밀번호가 명령 기록에
남을 수 있으므로 운영 계정으로 실행할 때는 터미널 기록과 화면 공유에 주의합니다.

```powershell
curl.exe -sS -c cookie.txt -X POST "http://127.0.0.1:8000/api/v1/auth/login" `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"CHANGE_ME"}'

$csrfLine = Get-Content -LiteralPath cookie.txt |
  Where-Object { $_ -match "`tnetprobe_csrf`t" } |
  Select-Object -Last 1
$csrf = ($csrfLine -split "`t")[-1]
```

조회용 `GET` 요청은 쿠키만 전달합니다.

```powershell
curl.exe -sS -b cookie.txt "http://127.0.0.1:8000/api/v1/auth/me"
curl.exe -sS -b cookie.txt "http://127.0.0.1:8000/api/v1/client-info"
```

진단 및 상태 변경 요청은 쿠키와 `X-CSRF-Token` 헤더를 함께 전달합니다.

```powershell
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/http-check" `
  -H "Content-Type: application/json" `
  -H "X-CSRF-Token: $csrf" `
  -d '{"url":"https://example.com","method":"GET"}'
```

로그아웃:

```powershell
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/auth/logout" `
  -H "X-CSRF-Token: $csrf"
```

## 8. 진단 이력 조회

DB와 진단 저장 기능이 활성화된 경우에 사용할 수 있습니다.

```powershell
# 최근 이력: limit 1~200, offset 0 이상
curl.exe -sS -b cookie.txt "http://127.0.0.1:8000/api/v1/diagnostics?limit=20&offset=0"

# 단일 상세
curl.exe -sS -b cookie.txt "http://127.0.0.1:8000/api/v1/diagnostics/RUN_ID"
```

VIEWER와 OPERATOR는 본인의 이력만 조회하며 ADMIN은 전체 이력을 조회합니다.

## 9. 관리자 사용자 API

아래 명령은 ADMIN 계정으로 로그인한 `cookie.txt`와 7장에서 읽은 `$csrf`를 사용합니다.

```powershell
# 사용자 목록: role, status, query는 선택 사항
curl.exe -sS -b cookie.txt "http://127.0.0.1:8000/api/v1/admin/users?limit=50&offset=0"

# 사용자 생성
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/admin/users" `
  -H "Content-Type: application/json" -H "X-CSRF-Token: $csrf" `
  -d '{"username":"operator1","display_name":"Operator 1","email":null,"role":"OPERATOR","temporary_password":"CHANGE_ME_123!"}'

# 사용자 수정
curl.exe -sS -b cookie.txt -X PATCH "http://127.0.0.1:8000/api/v1/admin/users/USER_ID" `
  -H "Content-Type: application/json" -H "X-CSRF-Token: $csrf" `
  -d '{"display_name":"New Name","role":"VIEWER","status":"ACTIVE"}'

# 잠금 해제
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/admin/users/USER_ID/unlock" `
  -H "X-CSRF-Token: $csrf"

# 임시 비밀번호 재설정
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/admin/users/USER_ID/reset-password" `
  -H "Content-Type: application/json" -H "X-CSRF-Token: $csrf" `
  -d '{"temporary_password":"NEW_CHANGE_ME_123!"}'

# 해당 사용자의 모든 세션 폐기
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/admin/users/USER_ID/revoke-sessions" `
  -H "X-CSRF-Token: $csrf"
```

비밀번호는 12~128자이며 사용자명 포함 금지 등 서버 비밀번호 정책을 통과해야 합니다.

## 10. 비밀번호 변경

```powershell
curl.exe -sS -b cookie.txt -X POST "http://127.0.0.1:8000/api/v1/auth/change-password" `
  -H "Content-Type: application/json" -H "X-CSRF-Token: $csrf" `
  -d '{"current_password":"CURRENT_PASSWORD","new_password":"NEW_CHANGE_ME_123!"}'
```

## 11. 공통 응답 형식

성공 응답:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": {
    "request_id": "UUID",
    "timestamp": "2026-08-26T12:00:00+09:00",
    "duration_ms": 10
  }
}
```

오류 응답:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "오류 설명"
  },
  "meta": {
    "request_id": "UUID",
    "timestamp": "2026-08-26T12:00:00+09:00",
    "duration_ms": 1
  }
}
```

자주 보는 상태 코드는 `401`(로그인 필요), `403`(권한 부족·대상 차단·CSRF 실패),
`422`(입력 오류), `429`(분당 호출 제한 초과), `503`(DB 사용 불가)입니다.

> 사설 IP와 내부 대상은 기본적으로 차단됩니다. 사내 진단이 필요하면 서버 설정의
> `NDT_ALLOW_PRIVATE_TARGETS`와 `NDT_ALLOWED_TARGET_DOMAINS`를 먼저 확인하세요.
