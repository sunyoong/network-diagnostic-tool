# NetProbe — 네트워크 진단 웹서비스

브라우저에서 HTTP 상태, TCP 포트, DNS 레코드, 접속 정보를 점검할 수 있는 FastAPI 기반
네트워크 진단 도구입니다. `docs/specifications/network-diagnostic-service-spec.md` 명세서를 기준으로 구현했습니다.

## 관련 문서

- [서비스 기능 및 개발 설계 명세](docs/specifications/network-diagnostic-service-spec.md)
- [PostgreSQL 데이터베이스 명세](docs/specifications/postgresql-database-spec.md)
- [인증 및 계정 명세](docs/specifications/authentication-account-spec.md)
- [Windows PostgreSQL 설치 가이드](docs/guides/POSTGRESQL_WINDOWS_INSTALL_GUIDE.md)
- [PostgreSQL·로그인 기능 사용 가이드](docs/guides/DATABASE_AUTH_GUIDE.md)

## 빠른 시작

### Windows PowerShell

프로젝트 루트(`requirements.txt`와 `app` 폴더가 있는 위치)에서 실행합니다. `.venv` 가상환경은 프로젝트 폴더 내부에 생성됩니다.

```powershell
py -3.12 -m venv .venv

# PowerShell 실행 정책 오류가 발생할 때 현재 창에서만 임시 허용
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

실행 정책을 변경하지 않으려면 가상환경을 활성화하지 않고 다음처럼 직접 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### macOS/Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

브라우저에서 `http://localhost:8000` 접속. API 문서는 `http://localhost:8000/docs`.

상세한 환경 설정과 문제 해결 방법은 [`RUN_GUIDE.md`](docs/guides/RUN_GUIDE.md)를 참고하세요.

## 테스트

```bash
pytest
```

## 프로젝트 구조

```text
app/
├── main.py              # FastAPI 앱, 라우터 등록, 예외 핸들러, 정적 파일 서빙
├── api/                 # 라우터 (요청 검증 → 서비스 호출 → 응답 매핑)
│   ├── http_check.py
│   ├── port_check.py
│   ├── dns_lookup.py
│   └── client_info.py
├── schemas/              # Pydantic 요청/응답 모델, 공통 응답 봉투
│   ├── request.py
│   └── response.py
├── services/              # 실제 네트워크 I/O 로직 (라우터와 분리)
│   ├── http_service.py    # httpx.AsyncClient, 리다이렉트마다 IP 재검증
│   ├── tcp_service.py      # asyncio.open_connection()
│   └── dns_service.py       # dns.asyncresolver
├── core/
│   ├── config.py          # 환경변수 기반 설정 (NDT_ 접두사)
│   ├── security.py        # SSRF 방지, 입력 검증, 요청 횟수 제한
│   ├── deps.py             # FastAPI 의존성 (rate limit, 세마포어, 클라이언트 IP)
│   └── logging.py          # 구조화 로깅, 민감정보 마스킹
└── static/                # 프론트엔드 (Vanilla HTML/CSS/JS)
    ├── index.html
    ├── css/style.css
    └── js/app.js
tests/
├── test_security.py
└── test_api.py
```

## 설계 노트 (명세서 대비 구현 결정사항)

명세서 4.1/4.2에 두 가지 결과 표현 방식이 섞여 있어, 다음과 같이 일관되게 구현했습니다.

- **HTTP 확인(BE-01)**: 서버가 실제 HTTP 응답(2xx~5xx)을 받으면 `success:true`와
  `data`로 반환합니다. 연결 자체가 실패한 경우(`CONNECTION_REFUSED`,
  `CONNECTION_TIMEOUT`, `TLS_ERROR`)는 공통 오류 봉투(`success:false`)로 반환하되,
  명세서 표 4.2 기준대로 HTTP 상태 코드는 `200`을 유지합니다.
- **TCP 포트 확인(BE-02)**: 응답 데이터 자체에 `result` 필드(`OPEN`/`REFUSED`/
  `TIMEOUT`/`DNS_FAILED`/`BLOCKED`)가 정의되어 있으므로, 이 값들은 모두
  `success:true`인 정상 완료된 진단 결과로 반환합니다.
- **입력 형식 오류·대상 차단·DNS 조회 자체 실패**는 두 기능 모두
  `VALIDATION_ERROR`(422), `TARGET_NOT_ALLOWED`(403),
  `DNS_RESOLUTION_FAILED`(400)로 통일했습니다.

## 보안 정책 (요약)

- `http`, `https` 스킴만 허용, URL에 인증정보(`user:password@host`) 포함 시 거부.
- 루프백·링크로컬·멀티캐스트·예약·사설 IP·클라우드 메타데이터 주소(`169.254.169.254` 등)
  접근을 기본 차단 (`NDT_ALLOW_PRIVATE_TARGETS=true`로 사내 진단 시에만 완화 가능).
- DNS로 해석된 모든 IP를 검사하며, HTTP 리다이렉트마다 목적지 IP를 재검증합니다.
- TCP 포트는 기본 허용 목록(`22,53,80,443,5432,3306,6379,8080`)만 진단 가능.
- 클라이언트 IP 기준 분당 요청 횟수 제한(기본 30회, 인메모리 슬라이딩 윈도우).
  **참고**: 다중 워커/인스턴스로 배포할 경우 이 인메모리 구현은 워커별로 별도 카운트되므로
  Redis 등 공유 저장소 기반 구현으로 교체를 권장합니다.
- HTTP 응답 본문은 저장하지 않고 최대 수신 크기(`NDT_MAX_RESPONSE_BYTES`)까지만 스트리밍합니다.
- `Cookie`, `Authorization` 등 민감 헤더는 응답/로그에 노출하지 않으며, 로그의 쿼리 문자열
  민감값은 마스킹합니다.

## 알려진 제한사항 / 2단계 확장 대상

- 프로덕션 다중 워커 배포 시 요청 횟수 제한과 동시성 세마포어는 프로세스 로컬입니다.
- 진단 이력 저장은 브라우저 `localStorage`(최대 5건)만 지원하며, 서버 측 이력·CSV
  다운로드, SSL 인증서 상세 조회, WebSocket 테스트는 2단계 개선 항목입니다(명세서 13장).
