# 네트워크 진단 서비스 로그 설계 명세

## 1. 목적과 범위

이 문서는 네트워크 진단 서비스가 생성하는 애플리케이션 로그의 형식과 필드를 정의한다. 로그는 이후 Logstash로 수집하고 Elasticsearch에 문서로 저장한 뒤 Kibana에서 조회·시각화하는 실습에 사용한다.

현재 단계의 흐름은 다음과 같다.

```text
FastAPI 서비스 → logs/network-diagnostic.log (JSON Lines) → Logstash → Elasticsearch → Kibana
```

## 2. 파일 및 인코딩 규칙

| 항목 | 값 |
| --- | --- |
| 기본 파일 | `logs/network-diagnostic.log` |
| 형식 | JSON Lines (NDJSON): 한 줄에 JSON 객체 하나 |
| 인코딩 | UTF-8 |
| 설정 변수 | `NDT_LOG_FILE` |
| Git 정책 | 실행 중 생성되는 `logs/` 디렉터리는 커밋하지 않음 |

여러 줄로 보기 좋게 들여쓴 JSON은 사용하지 않는다. Logstash 파일 입력에서 각 줄이 하나의 이벤트가 되도록 한다.

## 3. 모든 이벤트의 공통 필드

| 필드 | 형식 | 설명 | 예시 |
| --- | --- | --- | --- |
| `timestamp` | ISO-8601 UTC | 로그 발생 시각 | `2026-08-22T10:00:00.123Z` |
| `level` | 문자열 | `INFO`, `WARNING`, `ERROR` 등 표준 로그 레벨 | `INFO` |
| `service` | 문자열 | 서비스 식별자 | `network-diagnostic` |
| `environment` | 문자열 | 실행 환경 | `development` |
| `event` | 문자열 | 이벤트 종류 | `http_check` |
| `message` | 문자열, 선택 | 일반 애플리케이션 로그의 메시지 | `HTTP Request: ...` |

진단 결과 이벤트는 아래 필드를 추가한다.

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `request_id` | UUID 문자열 | 진단 요청 식별자 |
| `api_path` | 문자열 | 호출 API 경로 |
| `client_ip` | 문자열 | 요청 클라이언트 IP |
| `success` | 불리언 | 진단의 성공 여부 |
| `duration_ms` | 정수 | 전체 처리 시간(밀리초) |
| `result_code` | 문자열 | 진단 결과 코드 |

## 4. 이벤트별 로그 항목

| `event` | 발생 시점 | 추가 필드 |
| --- | --- | --- |
| `http_check` | HTTP 진단 결과 기록 시 | `target_host`, `target_url`, `http_method`, `http_status_code`, `http_response_time_ms`, `result_code` |
| `tcp_check` | TCP 포트 진단 결과 기록 시 | `target_host`, `target_port`, `tcp_success`, `tcp_connect_time_ms`, `result_code` |
| `dns_lookup` | DNS 조회 결과 기록 시 | `target_host`, `record_type`, `resolved_ips`, `dns_server`, `dns_response_time_ms`, `result_code` |
| `service_started` | 애플리케이션 시작 시 | `host`, `version` |
| `service_stopped` | 정상 종료 시 | `reason` |
| `application_log` | 프레임워크·일반 애플리케이션 로그 | `message` |

`tcp_check`는 포트가 닫혀도 진단 자체가 정상적으로 완료된 경우 `success: false`와 결과 코드(`REFUSED`, `TIMEOUT` 등)를 함께 기록한다. Kibana에서는 `success`와 `result_code`를 함께 사용해 실패 원인을 분류한다.

## 5. 로그 레벨 기준

| 레벨 | 사용 기준 |
| --- | --- |
| `INFO` | 정상 완료된 진단, 서비스 시작·종료, 일반 운영 정보 |
| `WARNING` | 요청 검증 실패, 대상 차단, 예상 가능한 네트워크 실패 |
| `ERROR` | 예상하지 못한 예외, 저장소 오류, 서비스가 처리하지 못한 오류 |

## 6. 예시

```json
{"timestamp":"2026-08-22T10:00:00.123Z","level":"INFO","service":"network-diagnostic","environment":"development","event":"http_check","request_id":"0b6f1d91-20f4-4a34-8c56-951a15ce8bb1","api_path":"/api/v1/http-check","client_ip":"127.0.0.1","target_host":"example.com","target_url":"https://example.com/health","http_method":"GET","http_status_code":200,"http_response_time_ms":120,"success":true,"duration_ms":125,"result_code":"OK"}
```

```json
{"timestamp":"2026-08-22T10:01:00.123Z","level":"INFO","service":"network-diagnostic","environment":"development","event":"dns_lookup","request_id":"347dc160-2a10-4420-a6ee-88fdfa4ddbed","api_path":"/api/v1/dns-lookup","client_ip":"127.0.0.1","target_host":"example.com","record_type":"A","resolved_ips":["93.184.216.34"],"dns_server":"8.8.8.8","dns_response_time_ms":12,"success":true,"duration_ms":15,"result_code":"OK"}
```

## 7. 보안 및 개인정보 원칙

- `Authorization`, `Cookie`, 비밀번호, 토큰, API 키를 기록하지 않는다.
- HTTP 대상 URL은 쿼리 문자열과 fragment를 제거한 값만 진단 결과 이벤트에 기록한다.
- 요청·응답 본문과 HTTP 응답 본문은 기록하지 않는다.
- 운영 환경에서 `client_ip` 수집 범위와 보존 기간은 조직의 개인정보 정책에 맞게 별도로 검토한다.

## 8. Logstash 연동 시 참고

파일을 읽을 때 각 줄을 JSON으로 해석하도록 설정한다. 예시 구성은 다음과 같다.

```conf
input {
  file {
    path => "/app/logs/network-diagnostic.log"
    start_position => "beginning"
    codec => json
  }
}
```

Elasticsearch 색인에서는 `timestamp`를 날짜 필드로 매핑하고, `duration_ms`, 응답 시간, 포트는 숫자 필드로 사용한다. `event`, `success`, `result_code`, `target_host`는 Kibana 필터·집계의 주요 기준이다.
