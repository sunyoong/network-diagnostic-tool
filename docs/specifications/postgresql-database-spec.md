# NetProbe PostgreSQL 데이터베이스 명세서

> 문서 상태: 구축 전 검토안(Draft)  
> 대상 애플리케이션: Network Diagnostic Tool  
> 공식 기준 PostgreSQL: 16.x (권장 설치 버전 16.14, 문법 호환 범위 14~18)
> DB 접근 방식: `asyncpg >=0.30,<1.0` 직접 SQL, SQLAlchemy/ORM 미사용
> 작성 기준: 현재 구현된 HTTP, TCP 포트, DNS, 접속 정보 API

## 1. 문서 목적

현재 NetProbe는 데이터베이스 없이 동작하며 진단 결과를 서버에 저장하지 않는다. 이 문서는 PostgreSQL을 도입해 운영상 가치가 있는 진단 이력과 장애 정보를 안전하게 저장하기 위한 1차 설계를 정의한다.

이 단계에서는 데이터베이스를 생성하거나 애플리케이션 코드를 변경하지 않는다. 본 문서의 저장 범위, 개인정보 처리, 보존기간을 승인한 후 구축을 진행한다.

## 2. 설계 목표

- HTTP, TCP 포트, DNS 진단 요청과 결과를 서버 측에 저장한다.
- 성공뿐 아니라 입력 오류, 접근 차단, DNS 실패, 타임아웃 등 실패 이력도 남긴다.
- 요청 ID를 기준으로 애플리케이션 로그와 DB 데이터를 연결할 수 있게 한다.
- 진단 유형별 상세 필드를 검색·통계 처리하기 쉬운 관계형 구조로 저장한다.
- URL 쿼리, 인증정보, Cookie, Authorization 등 민감정보는 저장하지 않는다.
- 클라이언트 IP는 원문 대신 HMAC 해시를 기본 저장하여 사용자별 추세와 요청 제한 분석에 활용한다.
- 데이터 보존기간과 정리 정책을 명확히 정의한다.
- 향후 사용자 인증, 즐겨찾기, 반복 진단, 통계 대시보드로 확장할 수 있게 한다.

## 3. 범위

### 3.1 1차 구축 범위

| 구분 | 저장 내용 |
|---|---|
| 공통 진단 실행 | 요청 ID, 진단 유형, 성공 여부, 결과 코드, 처리시간, 실행 시각 |
| HTTP 진단 | 마스킹된 URL, 메서드, 타임아웃, 응답 코드, 최종 URL, 대상 IP, 응답시간 |
| TCP 진단 | 호스트, 포트, 변환 IP, 연결 결과, 연결시간 |
| DNS 진단 | 도메인, 레코드 유형, 레코드 값, TTL, 리졸버, 조회시간 |
| 운영 감사 이벤트 | DB 저장 실패, 보안 정책 차단, 관리자 데이터 정리 등 중요 이벤트 |
| 보존 관리 | 데이터 만료일, 정기 삭제 기준, 삭제 배치 기록 |

현재 `GET /api/v1/client-info` 응답은 화면 표시 용도로만 사용하며 1차 DB에는 저장하지 않는다. 클라이언트 추세 분석에는 원본 접속 정보 대신 진단 실행의 `client_key`만 사용한다.

### 3.2 1차 구축 제외 범위

- 사용자 회원가입, 로그인 및 권한 관리(별도 [`authentication-account-spec.md`](authentication-account-spec.md)에서 설계)
- 비밀번호 또는 인증 토큰 저장
- HTTP 응답 본문 저장
- Cookie, Authorization 및 기타 인증 헤더 저장
- 요청/응답 전문 전체 저장
- 브라우저 `localStorage` 기록 자동 이관
- 서버 로그 원문 전체 저장
- Redis 기반 다중 워커 요청 횟수 제한
- 즐겨찾기, 스케줄 진단, 알림, CSV 내보내기

## 4. 데이터 분류 및 저장 원칙

### 4.1 데이터 등급

| 등급 | 예시 | 저장 원칙 |
|---|---|---|
| 일반 | 진단 유형, 상태 코드, 처리시간, 포트 번호 | 명세된 보존기간 동안 저장 |
| 내부 운영정보 | 대상 호스트, 도메인, 대상 IP, 오류 코드 | DB 접근 권한을 운영 역할로 제한 |
| 개인정보 가능 정보 | 클라이언트 IP, User-Agent | 최소화·해시화, 원문 저장은 별도 승인 필요 |
| 민감정보 | 비밀번호, 토큰, Cookie, Authorization | 저장 금지 |

### 4.2 URL 저장 규칙

사용자가 입력한 URL에는 토큰이나 개인정보가 쿼리 문자열로 포함될 수 있으므로 다음 규칙을 적용한다.

1. URL의 `scheme`, `host`, `port`, `path`만 저장한다.
2. 쿼리 문자열은 전체 제거한 뒤 `query_redacted=true`로 표시한다.
3. URL에 포함된 사용자명·비밀번호 형식은 현재 입력 검증과 동일하게 요청 단계에서 거부한다.
4. `final_url`도 동일한 방식으로 정제한 후 저장한다.
5. HTTP 응답 본문과 응답 헤더 전체는 저장하지 않는다.
6. `content_type`, `content_length`, `server`처럼 명세된 비민감 응답 메타데이터만 저장한다.

### 4.3 클라이언트 식별 규칙

기본 정책은 원본 클라이언트 IP를 저장하지 않고 다음 값만 저장하는 것이다.

```text
client_key = HMAC-SHA256(NDT_CLIENT_HASH_SECRET, 정규화된 클라이언트 IP)
```

- 단순 SHA-256이 아닌 서버 비밀키 기반 HMAC을 사용해 사전 대입 복원을 어렵게 한다.
- `NDT_CLIENT_HASH_SECRET`은 DB나 Git에 저장하지 않고 비밀관리 시스템 또는 런타임 환경변수로 제공한다.
- HMAC 비밀키를 교체하면 과거와 신규 클라이언트 키가 연결되지 않는 점을 운영 정책에 반영한다.
- 원본 IP 저장이 감사 목적으로 반드시 필요한 경우 별도 승인 후 `client_ip` 컬럼 사용을 활성화하고 보존기간을 7일 이하로 제한한다.
- `X-Forwarded-For` 전체 체인은 저장하지 않는다.

### 4.4 저장 금지 항목

- HTTP 요청 및 응답 본문
- `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`
- 비밀번호, API 키, 세션 ID, JWT, OAuth 코드
- URL 쿼리 문자열 원문
- 예외 스택 트레이스와 서버 로컬 파일 경로
- 신뢰하지 않는 `X-Forwarded-For` 값

## 5. 논리 데이터 모델

```mermaid
erDiagram
    DIAGNOSTIC_RUNS ||--o| HTTP_DIAGNOSTIC_RESULTS : "has detail"
    DIAGNOSTIC_RUNS ||--o| TCP_DIAGNOSTIC_RESULTS : "has detail"
    DIAGNOSTIC_RUNS ||--o| DNS_DIAGNOSTIC_RESULTS : "has detail"
    DIAGNOSTIC_RUNS ||--o{ AUDIT_EVENTS : "referenced by"

    DIAGNOSTIC_RUNS {
        uuid id PK
        varchar diagnostic_type
        boolean success
        varchar result_code
        integer api_status_code
        integer duration_ms
        char client_key
        timestamptz started_at
        timestamptz completed_at
        timestamptz expires_at
    }

    HTTP_DIAGNOSTIC_RESULTS {
        uuid run_id PK_FK
        text requested_url
        varchar method
        boolean query_redacted
        boolean reachable
        integer status_code
        inet resolved_ip
        integer response_time_ms
    }

    TCP_DIAGNOSTIC_RESULTS {
        uuid run_id PK_FK
        varchar host
        integer port
        inet_array resolved_ips
        varchar connection_result
        integer connection_time_ms
    }

    DNS_DIAGNOSTIC_RESULTS {
        uuid run_id PK_FK
        varchar domain
        varchar record_type
        text_array records
        integer record_count
        boolean records_redacted
        integer ttl
        varchar resolver
        integer lookup_time_ms
    }

    AUDIT_EVENTS {
        bigint id PK
        uuid run_id FK
        varchar event_type
        varchar severity
        jsonb details
        timestamptz created_at
        timestamptz expires_at
    }
```

## 6. 테이블 명세

### 6.1 `diagnostic_runs`

모든 진단 요청에 공통으로 생성되는 부모 테이블이다. 현재 API 응답의 `meta.request_id`를 기본키로 사용한다.

| 컬럼 | 형식 | NULL | 기본값 | 설명 |
|---|---|---:|---|---|
| `id` | `uuid` | N | 애플리케이션 생성 | API `request_id`와 동일 |
| `diagnostic_type` | `varchar(16)` | N | - | `HTTP`, `TCP`, `DNS` |
| `success` | `boolean` | N | - | 공통 응답의 성공 여부 |
| `result_code` | `varchar(40)` | N | - | `OK`, `OPEN`, `TIMEOUT`, `VALIDATION_ERROR` 등 |
| `api_status_code` | `smallint` | N | - | API가 반환한 HTTP 상태 코드 |
| `error_message` | `varchar(500)` | Y | `NULL` | 사용자에게 반환한 정제된 오류 메시지 |
| `duration_ms` | `integer` | N | - | API 전체 처리시간 |
| `client_key` | `char(64)` | Y | `NULL` | 클라이언트 IP HMAC-SHA256 16진수 |
| `client_ip` | `inet` | Y | `NULL` | 기본 비활성, 별도 승인 시 단기 저장 |
| `source` | `varchar(20)` | N | `'WEB'` | `WEB`, `API`, 향후 `SCHEDULED` |
| `app_version` | `varchar(40)` | Y | `NULL` | 진단을 수행한 애플리케이션 버전/커밋 |
| `started_at` | `timestamptz` | N | - | 진단 시작 시각, UTC 저장 |
| `completed_at` | `timestamptz` | N | - | 진단 완료 시각, UTC 저장 |
| `expires_at` | `timestamptz` | N | - | 보존기간 종료 시각 |
| `created_at` | `timestamptz` | N | `now()` | DB 입력 시각 |

제약조건:

- `diagnostic_type IN ('HTTP', 'TCP', 'DNS')`
- `api_status_code BETWEEN 100 AND 599`
- `duration_ms >= 0`
- `completed_at >= started_at`
- `expires_at > created_at`
- 상세 결과 테이블은 `diagnostic_type`에 해당하는 테이블 하나만 연결한다.

### 6.2 `http_diagnostic_results`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `run_id` | `uuid` | N | `diagnostic_runs.id`, PK/FK |
| `requested_url` | `text` | N | 쿼리 문자열을 제거한 입력 URL |
| `target_host` | `varchar(253)` | N | 정규화된 대상 호스트 |
| `method` | `varchar(8)` | N | `GET`, `HEAD` |
| `timeout_ms` | `integer` | N | 요청 타임아웃 설정값 |
| `follow_redirects` | `boolean` | N | 리다이렉트 추적 여부 |
| `query_redacted` | `boolean` | N | 입력 URL에서 쿼리를 제거했는지 여부 |
| `final_url` | `text` | Y | 정제된 최종 URL |
| `reachable` | `boolean` | N | HTTP 응답 수신 여부 |
| `status_code` | `smallint` | Y | 대상 서버 HTTP 상태 코드 |
| `reason_phrase` | `varchar(120)` | Y | 대상 서버 상태 설명 |
| `resolved_ip` | `inet` | Y | 실제 연결 대상 IP |
| `response_time_ms` | `integer` | Y | 대상 응답시간 |
| `content_length` | `bigint` | Y | 응답 크기 또는 Content-Length |
| `content_type` | `varchar(255)` | Y | Content-Type |
| `server_header` | `varchar(255)` | Y | 정제된 Server 헤더 |
| `redirect_count` | `smallint` | N | 리다이렉트 횟수 |

저장 실패 진단의 경우 입력값과 확인 가능한 필드만 저장하고 결과 필드는 `NULL`로 둔다.

### 6.3 `tcp_diagnostic_results`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `run_id` | `uuid` | N | `diagnostic_runs.id`, PK/FK |
| `host` | `varchar(253)` | N | 정규화된 입력 호스트 |
| `port` | `integer` | N | 대상 포트, 1~65535 |
| `timeout_ms` | `integer` | N | 연결 타임아웃 설정값 |
| `resolved_ips` | `inet[]` | N | DNS로 확인한 IP 목록, 기본 빈 배열 |
| `is_open` | `boolean` | N | 포트 연결 성공 여부 |
| `connection_result` | `varchar(20)` | N | `OPEN`, `REFUSED`, `TIMEOUT`, `DNS_FAILED`, `BLOCKED` |
| `connection_time_ms` | `integer` | Y | TCP 연결 완료 시간 |
| `message` | `varchar(500)` | N | 사용자 표시용 정제 메시지 |

### 6.4 `dns_diagnostic_results`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `run_id` | `uuid` | N | `diagnostic_runs.id`, PK/FK |
| `domain` | `varchar(253)` | N | IDNA 정규화 도메인 |
| `record_type` | `varchar(10)` | N | `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS` |
| `records` | `text[]` | N | 조회 결과, 기본 빈 배열 |
| `record_count` | `integer` | N | 실제 조회된 레코드 수 |
| `records_redacted` | `boolean` | N | 정책에 따라 레코드 값을 제거했는지 여부 |
| `ttl` | `integer` | Y | DNS TTL |
| `resolver` | `varchar(255)` | Y | 사용한 리졸버 주소 또는 식별자 |
| `lookup_time_ms` | `integer` | Y | DNS 조회시간 |

DNS TXT 레코드는 민감정보가 포함될 가능성이 있다. 권장 기본안은 TXT 조회 결과의 `records`를 빈 배열로 저장하고, `record_count`에는 실제 조회 건수, `records_redacted`에는 `true`를 저장하는 것이다. 이 정책은 구축 전 확정해야 한다.

### 6.5 `audit_events`

진단 결과와 별도로 보안·운영 이벤트를 기록한다. 일반 성공 요청마다 생성하지 않고 중요한 이벤트만 저장한다.

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `id` | `bigint GENERATED ALWAYS AS IDENTITY` | N | PK |
| `run_id` | `uuid` | Y | 연관 진단 요청 ID |
| `event_type` | `varchar(50)` | N | 이벤트 유형 |
| `severity` | `varchar(10)` | N | `INFO`, `WARNING`, `ERROR` |
| `client_key` | `char(64)` | Y | 클라이언트 HMAC 키 |
| `details` | `jsonb` | N | 스키마가 허용한 정제 데이터만 저장 |
| `created_at` | `timestamptz` | N | 이벤트 시각 |
| `expires_at` | `timestamptz` | N | 만료 시각 |

주요 `event_type`:

- `TARGET_BLOCKED`
- `RATE_LIMIT_EXCEEDED`
- `VALIDATION_REJECTED`
- `DATABASE_WRITE_FAILED`
- `RETENTION_JOB_COMPLETED`
- `RETENTION_JOB_FAILED`

`details`에는 비밀번호, 토큰, URL 쿼리, 요청 헤더 전문, 스택 트레이스를 넣지 않는다.

## 7. PostgreSQL DDL 초안

아래 DDL은 초기 SQL 마이그레이션의 설계 기준이다. 실제 구축에서는 `migrations` 폴더의 번호 기반 SQL 파일로 관리한다.

```sql
CREATE TABLE diagnostic_runs (
    id uuid PRIMARY KEY,
    diagnostic_type varchar(16) NOT NULL
        CHECK (diagnostic_type IN ('HTTP', 'TCP', 'DNS')),
    success boolean NOT NULL,
    result_code varchar(40) NOT NULL,
    api_status_code smallint NOT NULL
        CHECK (api_status_code BETWEEN 100 AND 599),
    error_message varchar(500),
    duration_ms integer NOT NULL CHECK (duration_ms >= 0),
    client_key char(64),
    client_ip inet,
    source varchar(20) NOT NULL DEFAULT 'WEB'
        CHECK (source IN ('WEB', 'API', 'SCHEDULED')),
    app_version varchar(40),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (completed_at >= started_at),
    CHECK (expires_at > created_at)
);

CREATE TABLE http_diagnostic_results (
    run_id uuid PRIMARY KEY
        REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    requested_url text NOT NULL,
    target_host varchar(253) NOT NULL,
    method varchar(8) NOT NULL CHECK (method IN ('GET', 'HEAD')),
    timeout_ms integer NOT NULL CHECK (timeout_ms BETWEEN 1000 AND 10000),
    follow_redirects boolean NOT NULL,
    query_redacted boolean NOT NULL DEFAULT false,
    final_url text,
    reachable boolean NOT NULL,
    status_code smallint CHECK (status_code BETWEEN 100 AND 599),
    reason_phrase varchar(120),
    resolved_ip inet,
    response_time_ms integer CHECK (response_time_ms >= 0),
    content_length bigint CHECK (content_length >= 0),
    content_type varchar(255),
    server_header varchar(255),
    redirect_count smallint NOT NULL DEFAULT 0 CHECK (redirect_count >= 0)
);

CREATE TABLE tcp_diagnostic_results (
    run_id uuid PRIMARY KEY
        REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    host varchar(253) NOT NULL,
    port integer NOT NULL CHECK (port BETWEEN 1 AND 65535),
    timeout_ms integer NOT NULL CHECK (timeout_ms BETWEEN 1000 AND 10000),
    resolved_ips inet[] NOT NULL DEFAULT '{}',
    is_open boolean NOT NULL,
    connection_result varchar(20) NOT NULL
        CHECK (connection_result IN ('OPEN', 'REFUSED', 'TIMEOUT', 'DNS_FAILED', 'BLOCKED')),
    connection_time_ms integer CHECK (connection_time_ms >= 0),
    message varchar(500) NOT NULL
);

CREATE TABLE dns_diagnostic_results (
    run_id uuid PRIMARY KEY
        REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    domain varchar(253) NOT NULL,
    record_type varchar(10) NOT NULL
        CHECK (record_type IN ('A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS')),
    records text[] NOT NULL DEFAULT '{}',
    record_count integer NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    records_redacted boolean NOT NULL DEFAULT false,
    ttl integer CHECK (ttl >= 0),
    resolver varchar(255),
    lookup_time_ms integer CHECK (lookup_time_ms >= 0)
);

CREATE TABLE audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid REFERENCES diagnostic_runs(id) ON DELETE SET NULL,
    event_type varchar(50) NOT NULL,
    severity varchar(10) NOT NULL
        CHECK (severity IN ('INFO', 'WARNING', 'ERROR')),
    client_key char(64),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > created_at)
);
```

## 8. 인덱스 설계

```sql
CREATE INDEX ix_diagnostic_runs_created_at
    ON diagnostic_runs (created_at DESC);

CREATE INDEX ix_diagnostic_runs_type_created_at
    ON diagnostic_runs (diagnostic_type, created_at DESC);

CREATE INDEX ix_diagnostic_runs_result_created_at
    ON diagnostic_runs (result_code, created_at DESC);

CREATE INDEX ix_diagnostic_runs_client_created_at
    ON diagnostic_runs (client_key, created_at DESC)
    WHERE client_key IS NOT NULL;

CREATE INDEX ix_diagnostic_runs_expires_at
    ON diagnostic_runs (expires_at);

CREATE INDEX ix_http_results_target_host
    ON http_diagnostic_results (target_host);

CREATE INDEX ix_tcp_results_host_port
    ON tcp_diagnostic_results (host, port);

CREATE INDEX ix_dns_results_domain_type
    ON dns_diagnostic_results (domain, record_type);

CREATE INDEX ix_audit_events_type_created_at
    ON audit_events (event_type, created_at DESC);

CREATE INDEX ix_audit_events_expires_at
    ON audit_events (expires_at);
```

초기에는 모든 인덱스를 무조건 추가하지 않고 실제 조회 API와 `EXPLAIN (ANALYZE, BUFFERS)` 결과를 기준으로 유지 여부를 판단한다.

## 9. 데이터 저장 흐름

진단 요청 한 건은 하나의 트랜잭션으로 저장한다.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant N as Network Service
    participant P as PostgreSQL

    C->>A: 진단 요청
    A->>A: 입력 및 보안 정책 검증
    A->>N: 네트워크 진단 실행
    N-->>A: 성공 또는 실패 결과
    A->>P: BEGIN
    A->>P: diagnostic_runs INSERT
    A->>P: 유형별 결과 INSERT
    A->>P: COMMIT
    A-->>C: API 응답
```

저장 원칙:

- 네트워크 진단 결과가 확정된 후 공통 행과 상세 행을 동일 트랜잭션에 저장한다.
- 공통 행 저장 후 상세 행 저장이 실패하면 전체 트랜잭션을 롤백한다.
- DB 장애가 네트워크 진단 API의 가용성을 막을지 여부는 구축 전 결정한다.
- 권장 기본값은 **진단 결과는 사용자에게 반환하되 DB 저장 실패를 오류 로그와 지표로 기록하는 fail-open 방식**이다.
- 감사 요구가 강한 환경에서는 DB 저장 성공 후에만 응답하는 fail-closed 방식으로 변경할 수 있다.

## 10. 보존기간 및 삭제 정책

### 10.1 권장 기본 보존기간

| 데이터 | 보존기간 | 비고 |
|---|---:|---|
| 진단 실행 및 상세 결과 | 90일 | 통계·장애 추적 목적 |
| 실패·차단 감사 이벤트 | 180일 | 보안 추세 분석 목적 |
| 원본 클라이언트 IP | 저장 안 함 | 활성화 시 최대 7일 |
| 클라이언트 HMAC 키 | 진단 이력과 동일 | 90일 |
| 애플리케이션 로그 | 별도 로그 정책 | DB 보존과 분리 |

### 10.2 삭제 작업

매일 비혼잡 시간대에 다음 순서로 실행한다.

```sql
DELETE FROM audit_events
WHERE expires_at < now();

DELETE FROM diagnostic_runs
WHERE expires_at < now();
```

상세 결과는 `ON DELETE CASCADE`로 함께 삭제된다. 데이터가 수백만 건 이상 증가하면 월 단위 파티셔닝과 파티션 삭제 방식으로 전환한다.

삭제 배치는 한 번에 지나치게 많은 행을 지우지 않도록 건수 제한과 반복 실행을 적용하고, 완료·실패 결과를 감사 이벤트 또는 외부 모니터링에 남긴다.

## 11. 예상 조회 기능

DB 구축 후 다음 API 또는 관리자 화면을 2차 기능으로 추가할 수 있다.

| 기능 | 예시 |
|---|---|
| 최근 진단 이력 | `GET /api/v1/diagnostics?limit=20` |
| 단일 진단 상세 | `GET /api/v1/diagnostics/{request_id}` |
| 유형별 필터 | `type=HTTP`, `type=TCP`, `type=DNS` |
| 결과별 필터 | `result_code=TIMEOUT` |
| 기간 검색 | `from`, `to` |
| 대상 검색 | 호스트 또는 도메인 완전일치/접두 검색 |
| 통계 | 성공률, 평균 응답시간, 오류 코드 분포 |
| CSV 내보내기 | 관리자 권한 및 최대 기간 제한 적용 |

사용자 인증을 도입하기 전에는 상세 이력 API를 외부에 공개하지 않고 관리자 네트워크 또는 별도 인증 계층으로 제한한다.

## 12. 애플리케이션 연동 권장안

### 12.1 Python 구성

| 구성요소 | 권장 기술 |
|---|---|
| 데이터 접근 | ORM 없이 `asyncpg` 직접 SQL |
| PostgreSQL 드라이버 | `asyncpg` |
| 마이그레이션 | 번호 기반 SQL 파일 + `schema_migrations` 적용 이력 |
| 연결 관리 | `asyncpg.Pool` 연결 풀 |
| 데이터 검증 | 기존 Pydantic 요청·응답 모델 + PostgreSQL 제약조건 |

라우터에서 직접 SQL을 실행하지 않는다. 권장 구성은 다음과 같다.

```text
app/
├── db/
│   ├── session.py
│   ├── models.py
│   └── migrations/
├── repositories/
│   └── diagnostic_repository.py
└── services/
    └── diagnostic_history_service.py
```

### 12.2 환경변수

```dotenv
NDT_DATABASE_URL=postgresql://netprobe_app:CHANGE_ME@127.0.0.1:5432/netprobe
NDT_DATABASE_POOL_SIZE=10
NDT_DATABASE_MAX_OVERFLOW=10
NDT_DATABASE_POOL_TIMEOUT_SECONDS=5
NDT_DATABASE_STATEMENT_TIMEOUT_MS=5000
NDT_DIAGNOSTIC_RETENTION_DAYS=90
NDT_AUDIT_RETENTION_DAYS=180
NDT_STORE_RAW_CLIENT_IP=false
NDT_CLIENT_HASH_SECRET=CHANGE_ME_WITH_SECRET_MANAGER
```

- 실제 DB 비밀번호와 HMAC 비밀키는 `.env.example`에 값으로 기록하지 않는다.
- 운영 환경에서는 전체 연결 문자열보다 비밀관리 시스템을 통한 조합을 권장한다.
- DB 연결 문자열이 로그나 오류 응답에 노출되지 않도록 한다.

### 12.3 연결 풀 초기값

단일 Uvicorn 워커 기준 권장 시작값:

- 기본 풀 크기: 10
- 초과 연결: 10
- 연결 획득 제한시간: 5초
- SQL 실행 제한시간: 5초
- 연결 유효성 확인: `pool_pre_ping=true`

다중 워커 사용 시 최대 연결 수는 다음 계산을 기준으로 PostgreSQL `max_connections`를 넘지 않게 한다.

```text
최대 애플리케이션 연결 = 인스턴스 수 × 워커 수 × (pool_size + max_overflow)
```

## 13. 트랜잭션 및 장애 처리

- 각 진단 결과 저장은 공통 행과 상세 행을 묶은 단일 트랜잭션으로 처리한다.
- API 요청 전체 동안 DB 트랜잭션을 열어둔 채 네트워크 I/O를 기다리지 않는다.
- 네트워크 진단 완료 후 짧은 DB 트랜잭션을 시작한다.
- 일시적 연결 오류에 대한 자동 재시도는 최대 1회로 제한하고 지수 백오프를 적용한다.
- 유효성 오류나 제약조건 위반은 자동 재시도하지 않는다.
- DB 저장 실패 시 응답의 `request_id`를 로그에 남겨 사후 추적할 수 있게 한다.
- 상세 데이터 중 일부가 없는 실패 결과도 명세된 `NULL` 규칙에 따라 저장할 수 있어야 한다.

## 14. DB 보안 명세

### 14.1 역할 분리

| 역할 | 권한 |
|---|---|
| `netprobe_owner` | 스키마와 마이그레이션 소유, 애플리케이션 로그인 금지 |
| `netprobe_migrator` | 배포 시 DDL 실행 |
| `netprobe_app` | 운영 중 필요한 SELECT/INSERT/UPDATE만 허용 |
| `netprobe_readonly` | 관리자 조회·리포트용 SELECT |

애플리케이션 역할에는 `SUPERUSER`, `CREATEDB`, `CREATEROLE`, 스키마 소유권을 부여하지 않는다.

### 14.2 네트워크 및 전송

- 운영 DB는 인터넷에 직접 공개하지 않는다.
- 애플리케이션 서버 또는 승인된 관리 네트워크에서만 5432 포트 접근을 허용한다.
- 운영 연결은 TLS를 사용하고 인증서 검증을 활성화한다.
- 개발·운영 DB와 계정을 분리한다.
- 기본 `public` 스키마의 불필요한 생성 권한을 제거한다.

### 14.3 백업

- 매일 자동 백업, 최소 7개 일간 복구 지점을 권장한다.
- 운영 중요도에 따라 PITR(Point-in-Time Recovery)을 활성화한다.
- 백업 파일도 운영 DB와 동일한 수준으로 암호화·접근 통제한다.
- 분기별 또는 월별로 복구 테스트를 수행한다.

## 15. 모니터링 항목

- DB 연결 풀 사용률과 대기시간
- 결과 저장 성공/실패 건수
- INSERT 지연시간
- 테이블 및 인덱스 크기
- 만료 데이터 삭제 건수와 소요시간
- 장기 실행 SQL
- deadlock, connection error, statement timeout
- 진단 유형별 일간 건수와 오류율

## 16. 마이그레이션 전략

1. PostgreSQL 인스턴스와 역할을 생성한다.
2. `python -m app.cli migrate`로 초기 SQL 마이그레이션을 실행해 테이블과 인덱스를 생성한다.
3. 애플리케이션 시작 시 마이그레이션을 자동 실행하지 않는다.
4. 배포 파이프라인 또는 운영 절차에서 마이그레이션을 별도 실행한다.
5. DB 저장 기능을 기능 플래그로 배포한다.
6. 초기에는 fail-open 방식과 낮은 트래픽 비율로 검증한다.
7. 저장 결과와 API 응답이 일치하는지 모니터링한다.
8. 안정화 후 서버 측 이력 조회 기능을 활성화한다.

권장 기능 플래그:

```dotenv
NDT_DATABASE_ENABLED=false
NDT_DIAGNOSTIC_PERSISTENCE_ENABLED=false
```

## 17. 테스트 요구사항

### 17.1 단위 테스트

- URL 쿼리 제거 및 민감값 마스킹
- 클라이언트 IP HMAC 생성
- API 결과에서 DB 모델로의 필드 매핑
- 보존 만료일 계산
- 결과 코드 매핑

### 17.2 통합 테스트

- HTTP 성공/실패 결과 저장
- TCP `OPEN`, `REFUSED`, `TIMEOUT`, `BLOCKED` 저장
- DNS 정상, 빈 레코드, NXDOMAIN, 타임아웃 저장
- 공통 행과 상세 행의 트랜잭션 원자성
- FK 및 CHECK 제약조건
- 만료 데이터 삭제와 상세 행 CASCADE 삭제
- DB 연결 실패 시 fail-open 동작
- 민감정보가 DB에 저장되지 않는지 확인

### 17.3 성능 테스트

- 동시 진단 20건 상황에서 연결 풀 고갈 여부
- 진단 이력 100만 건 기준 최근 이력 조회 성능
- 보존 삭제 작업 중 API INSERT 지연 여부
- 유형·기간·결과 코드 필터의 인덱스 사용 여부

## 18. 구축 전 확정이 필요한 결정사항

다음 항목은 DB 구축 전에 검토·승인이 필요하다.

| 번호 | 결정 항목 | 권장 기본안 |
|---:|---|---|
| 1 | 진단 이력 보존기간 | 90일 |
| 2 | 감사 이벤트 보존기간 | 180일 |
| 3 | 원본 클라이언트 IP 저장 | 저장하지 않음, HMAC만 저장 |
| 4 | DNS TXT 레코드 값 저장 | 저장하지 않고 건수만 저장 |
| 5 | DB 저장 실패 시 API 처리 | 진단 응답은 반환하는 fail-open |
| 6 | 이력 조회 권한 | 인증된 관리자만 허용 |
| 7 | PostgreSQL 운영 위치 | 애플리케이션과 동일 사설망 |
| 8 | 백업 수준 | 일 1회 + 최소 7일 복구 지점 |
| 9 | 예상 일일 진단 건수 | 용량 산정을 위해 확인 필요 |
| 10 | 사용자 로그인 도입 여부 | 별도 [`authentication-account-spec.md`](authentication-account-spec.md) 검토 |

## 19. 예상 구축 단계

### 1단계: 기반 구축

- PostgreSQL 인스턴스, DB, 역할 생성
- `asyncpg` 연결 풀과 직접 SQL 저장소 추가
- 연결 설정과 `/health` DB 준비 상태 검사
- 초기 스키마 마이그레이션

### 2단계: 진단 결과 저장

- 공통 저장 모델과 Repository 구현
- HTTP, TCP, DNS 결과 매핑
- 민감정보 정제와 클라이언트 HMAC 처리
- 저장 실패 모니터링

### 3단계: 이력 조회

- 최근 이력과 단일 상세 조회 API
- 관리자 접근 제어
- 기간·유형·결과 필터
- 프론트엔드 최근 이력을 `localStorage`에서 서버 API로 전환

### 4단계: 운영 안정화

- 보존기간 삭제 작업
- 백업과 복구 테스트
- 통계·대시보드
- 용량과 인덱스 튜닝

## 20. 승인 기준

다음 조건이 합의되면 DB 구축을 시작할 수 있다.

- 저장 대상과 저장 금지 항목이 승인되었다.
- 클라이언트 IP 처리 방식이 승인되었다.
- DNS TXT 레코드 저장 정책이 승인되었다.
- 진단 및 감사 데이터 보존기간이 승인되었다.
- DB 저장 실패 시 fail-open/fail-closed 정책이 결정되었다.
- PostgreSQL 운영 위치와 백업 정책이 결정되었다.
- 이력 조회 권한과 인증 방식이 결정되었다.
