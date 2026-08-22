# 네트워크 진단 도구 실행 가이드

이 문서는 `network-diagnostic-tool.zip`에 포함된 코드를 로컬 PC에서 실행하는 방법을 설명합니다. 이 프로젝트는 **FastAPI 기반 Python 웹 애플리케이션**이며, 데이터베이스나 별도의 프런트엔드 빌드 과정은 필요하지 않습니다.

## 1. 사전 준비

- Python 3.10 이상
- 인터넷 연결(최초 Python 패키지 설치 및 외부 네트워크 진단 시 필요)
- 원본 압축 파일: `C:\sypark\개발\네트워크진단서비스\network-diagnostic-tool.zip`

Windows에서 다음 명령으로 Python 설치 여부를 확인합니다.

```powershell
python --version
```

명령을 찾을 수 없다면 [Python 공식 사이트](https://www.python.org/downloads/)에서 Python을 설치합니다. 설치 화면에서 **Add Python to PATH**를 선택해야 합니다. 설치 후 새 PowerShell 창을 열어 다시 확인합니다.

> 이 가이드를 작성한 PC에서는 현재 `python` 및 `py` 명령이 확인되지 않았습니다. 이 PC에서 실행하려면 먼저 Python을 설치해야 합니다.

## 2. 압축 해제

PowerShell에서 다음 명령을 실행합니다.

```powershell
Set-Location "C:\sypark\개발\네트워크진단서비스"
Expand-Archive -LiteralPath ".\network-diagnostic-tool.zip" -DestinationPath "." -Force
Set-Location ".\network-diagnostic-tool"
```

이미 압축을 해제했다면 프로젝트 루트, 즉 `requirements.txt`와 `app` 폴더가 보이는 위치로 이동하면 됩니다.

## 3. 가상환경 생성 및 활성화

프로젝트에 필요한 패키지가 다른 Python 프로젝트와 섞이지 않도록 가상환경을 사용합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

PowerShell 실행 정책 때문에 활성화가 차단되면 현재 PowerShell 프로세스에만 임시로 허용한 뒤 다시 활성화합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

활성화되면 명령줄 앞에 `(.venv)`가 표시됩니다.

## 4. 패키지 설치

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

설치되는 주요 패키지는 FastAPI, Uvicorn, HTTPX, dnspython, Pydantic 및 Pytest입니다.

## 5. 환경 설정

예제 설정 파일을 `.env`로 복사합니다.

```powershell
Copy-Item .env.example .env
```

공개 인터넷 주소만 진단한다면 기본값을 그대로 사용할 수 있습니다. 기본 설정은 보안을 위해 로컬·사설 IP 대역과 임의의 TCP 포트를 차단합니다.

사내망 또는 로컬 장비를 진단해야 하는 경우 `.env`에서 아래 값을 변경합니다.

```dotenv
NDT_ALLOW_PRIVATE_TARGETS=true
```

이 값을 `true`로 설정하면 사설 IP 접근 제한과 TCP 포트 허용 목록 제한이 완화됩니다. 외부에 공개된 서버에서는 SSRF 위험이 있으므로, 인증된 내부 사용자만 접근할 수 있는 환경에서만 사용해야 합니다.

기본 공개 모드에서 허용되는 TCP 포트는 다음과 같습니다.

```dotenv
NDT_ALLOWED_TCP_PORTS=[22,53,80,443,5432,3306,6379,8080]
```

## 6. 서버 실행

반드시 `app` 폴더의 상위 디렉터리인 프로젝트 루트에서 실행합니다.

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

정상 실행되면 브라우저에서 다음 주소를 엽니다.

- 웹 화면: <http://127.0.0.1:8000>
- API 문서(Swagger UI): <http://127.0.0.1:8000/docs>
- 상태 확인: <http://127.0.0.1:8000/health>

상태 확인 결과가 아래와 같으면 정상입니다.

```json
{"status":"ok"}
```

서버를 종료하려면 서버를 실행한 PowerShell 창에서 `Ctrl+C`를 누릅니다.

### 같은 네트워크의 다른 PC에서도 접속하기

개발 PC의 모든 네트워크 인터페이스에서 요청을 받도록 실행합니다.

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

다른 PC에서는 `http://개발-PC-IP:8000`으로 접속합니다. 접속되지 않으면 Windows 방화벽의 TCP 8000 포트 인바운드 허용 여부를 확인합니다. `--reload`는 개발용 기능이므로 공유 또는 운영 실행에서는 제외하는 것이 좋습니다.

## 7. 기능 확인

웹 화면에서 다음 기능을 사용할 수 있습니다.

- HTTP 상태 확인: `http://` 또는 `https://`로 시작하는 URL 입력
- TCP 포트 확인: 호스트와 포트 입력
- DNS 조회: 스킴과 경로를 제외한 도메인 입력(예: `example.com`)
- 접속 정보: 클라이언트 IP, User-Agent, 프로토콜 등 확인

PowerShell에서 API를 직접 확인하려면 다음 예시를 사용할 수 있습니다.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/http-check" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"url":"https://example.com","method":"GET","timeout_seconds":5,"follow_redirects":true}'

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/port-check" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"host":"example.com","port":443,"timeout_seconds":3}'

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/dns-lookup" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"domain":"example.com","record_type":"A"}'
```

## 8. JSON 로그 확인

서버를 실행하면 프로젝트 루트의 `logs/network-diagnostic.log` 파일 하나에 로그가 누적됩니다. 각 줄은 독립된 JSON 객체(JSON Lines/NDJSON)이므로 이후 Logstash의 `file` input과 `json` codec으로 바로 수집할 수 있습니다.

기본 경로는 `.env`에서 변경할 수 있습니다.

```env
NDT_LOG_FILE=logs/network-diagnostic.log
```

로그 파일에는 `timestamp`, `level`, `service`, `environment`, `event` 공통 필드와 진단별 대상, 성공 여부, 처리 시간이 기록됩니다. HTTP URL의 쿼리와 인증정보 등 민감정보는 파일에 기록하지 않습니다. `logs/` 디렉터리는 실행 중 생성되며 Git에는 포함되지 않습니다.

## 9. 테스트 실행

서버를 별도로 실행하지 않은 상태에서도 프로젝트 루트에서 테스트할 수 있습니다.

```powershell
python -m pytest
```

## 10. macOS/Linux 실행 명령

압축을 해제하고 프로젝트 루트로 이동한 뒤 아래 명령을 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 10. 자주 발생하는 문제

### `python` 명령을 찾을 수 없음

Python을 설치하면서 PATH 옵션을 선택했는지 확인하고 PowerShell을 새로 엽니다. Windows에서 Python Launcher가 설치되어 있다면 `python` 대신 `py`를 사용할 수도 있습니다.

### `No module named uvicorn` 또는 `No module named fastapi`

가상환경 활성화 여부를 확인한 후 패키지를 다시 설치합니다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### `Could not import module "app.main"`

현재 위치가 잘못된 경우입니다. `requirements.txt`와 `app` 폴더가 함께 보이는 프로젝트 루트로 이동한 뒤 실행합니다.

```powershell
Get-ChildItem
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 포트 8000이 이미 사용 중임

다른 포트로 실행합니다.

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

이 경우 접속 주소도 `http://127.0.0.1:8001`로 변경됩니다.

### 사설 IP 또는 특정 포트 진단이 차단됨

기본 보안 정책에 따른 정상 동작입니다. 인증된 사내 환경에서만 `.env`의 `NDT_ALLOW_PRIVATE_TARGETS=true` 설정을 검토합니다. 설정을 변경한 후에는 서버를 재시작합니다.

### 외부 HTTP/DNS 진단이 실패함

회사 방화벽, 프록시, VPN 또는 보안 프로그램이 Python 프로세스의 외부 통신을 제한하는지 확인합니다. 이 애플리케이션은 별도의 프록시 설정 화면을 제공하지 않습니다.

## 11. GitHub 저장소와 로컬 폴더 연결

GitHub 저장소 주소는 다음과 같습니다.

```text
https://github.com/sunyoong/network-diagnostic-tool.git
```

### 권장 방법: 기존 폴더를 백업하고 Clone

압축 파일에서 해제한 기존 프로젝트와 GitHub 저장소는 Git 이력이 다를 수 있습니다. 기존 파일과 충돌하지 않도록 폴더를 백업한 뒤 GitHub 저장소를 새로 Clone하는 방법이 가장 안전합니다.

실행 중인 서버가 있다면 먼저 `Ctrl+C`로 종료하고, PowerShell에서 다음 명령을 실행합니다.

```powershell
Set-Location "C:\sypark\개발\네트워크진단서비스"

Rename-Item `
  -LiteralPath ".\network-diagnostic-tool" `
  -NewName "network-diagnostic-tool-backup"

git clone https://github.com/sunyoong/network-diagnostic-tool.git
Set-Location ".\network-diagnostic-tool"
```

저장소가 비공개이므로 GitHub 로그인이나 브라우저 인증을 요청할 수 있습니다.

Clone한 저장소에는 `.venv`와 `.env`가 포함되지 않습니다. 프로젝트 내부에 Python 3.12 가상환경과 로컬 설정을 다시 생성합니다.

```powershell
py -3.12 -m venv .venv

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

기존 백업 폴더의 `.env`에 필요한 설정이 있다면 내용을 검토한 후 새 `.env`에 직접 반영합니다. `.venv` 폴더는 복사하지 말고 새로 생성하는 것이 안전합니다.

연결 상태는 다음 명령으로 확인합니다.

```powershell
git remote -v
git status
```

### 기존 폴더에 원격 저장소만 연결

기존 폴더를 그대로 사용해야 한다면 다음 명령으로 GitHub 원격 저장소를 등록할 수 있습니다.

```powershell
Set-Location "C:\sypark\개발\네트워크진단서비스\network-diagnostic-tool"

git init
git remote add origin https://github.com/sunyoong/network-diagnostic-tool.git
git fetch origin
git remote -v
```

이미 `origin`이 등록되어 있다는 오류가 나오면 현재 주소부터 확인합니다.

```powershell
git remote get-url origin
```

기존 로컬 파일과 GitHub 파일이 서로 다르면 `pull` 과정에서 충돌할 수 있습니다. 이 경우 파일을 덮어쓰거나 강제로 병합하지 말고, 위의 **기존 폴더 백업 후 Clone** 방법을 사용하세요.

### 이후 GitHub 변경사항 받기

프로젝트 폴더에서 다음 명령을 실행합니다.

```powershell
git pull
```

로컬에서 수정한 내용을 GitHub에 올릴 때는 변경 파일을 확인한 후 커밋하고 푸시합니다. 실제 `.env`와 `.venv`는 `.gitignore`에 의해 제외됩니다.

```powershell
git status
git add .
git commit -m "변경 내용 설명"
git push
```

## 운영 시 참고사항

- `--reload` 옵션은 개발 환경에서만 사용합니다.
- 기본 요청 제한은 클라이언트 IP당 분당 30회입니다.
- 요청 제한과 동시성 제어는 프로세스별 메모리에 저장되므로 다중 워커 운영에서는 공유되지 않습니다.
- 리버스 프록시를 사용하면 실제 클라이언트 IP를 처리하도록 `.env`의 `NDT_TRUSTED_PROXY_IPS`에 신뢰할 프록시 IP를 JSON 배열 형식으로 지정합니다.
- 운영 환경에서는 HTTPS 리버스 프록시, 사용자 인증, 접근 제어를 별도로 구성하는 것이 좋습니다.
