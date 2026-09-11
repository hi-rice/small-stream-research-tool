# small-stream-research-tool

표시명: **소하천 데이터 관리** · NDMI

국립재난안전연구원의 소하천 연구업무를 위한 Windows 로컬·오프라인 프로그램이다.
다양한 Excel 연구자료를 데이터 사전에 맞춰 관리하고 출처와 변경이력을 보존하는 것을 목표로 한다.

## 현재 상태

Phase 0 개발 기반과 Phase 1 SQLite 기반을 제공한다. DB 연결, 19개 V1 테이블,
39개 FK, CHECK·UNIQUE·부분 유일 인덱스와 순차 SQL migration을 구현했다.
CLI는 시작 확인 메시지를 기록하고 종료하며 DB 초기화는 명시적 API 호출로만 수행한다.
로그인·Excel 처리·QC 실행·업무 화면·분석은 아직 구현하지 않았다.

## 환경과 의존성

- Python **3.12.x**, Windows를 기본 대상으로 한다.
- 표준 `venv` + `pip`, `pyproject.toml` + setuptools의 `src` 패키지 구조를 사용한다.
  별도 패키지 관리자 없이 Python 기본 도구로 설치·검증하기 위한 선택이다.
- 현재 실행 의존성은 Python 표준 라이브러리뿐이다.
- 개발 도구는 pytest(테스트), ruff(lint·format)다. mypy는 도입하지 않았다.
- 향후 PySide6, pandas, openpyxl, matplotlib는 실제 사용하는 Phase에서 추가한다.
  SQLite는 표준 `sqlite3`를 사용하며 ORM은 도입하지 않는다.

## 개발환경 설치 (PowerShell)

Python 3.12를 먼저 준비한 뒤 저장소 루트에서 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`py -3.12`로 인터프리터를 찾지 못하면 설치된 Python 3.12 실행파일로
`-m venv .venv`를 실행한다. 활성화 스크립트 없이 가상환경 실행파일을 직접 사용한다.
개발 도구의 최초 다운로드에는 네트워크가 필요할 수 있다. 설치 후 현재 실행 기능은
인터넷에 연결하지 않으며 연구자료를 외부로 전송하지 않는다.
의존성 허용 버전은 pyproject.toml에서 관리한다. 현재 lockfile은 없으며
개발환경의 완전한 버전 고정은 후속 배포 준비에서 검토한다.

## 실행

```powershell
.\.venv\Scripts\python.exe -m small_stream_research_tool
.\.venv\Scripts\small-stream-research-tool.exe --version
.\.venv\Scripts\small-stream-research-tool.exe --log-level DEBUG
```

두 실행 경로는 `app/main.py`의 `main()`으로 연결된다. `--help`로 옵션을 확인할 수 있다.
실제 창을 띄우거나 DB·workspace·백업 파일을 만들지 않는다.

## 설정과 로깅

앱 정보와 경로는 `config/settings.py`에서 관리한다.
기준 경로는 `%LOCALAPPDATA%/NDMI/small-stream-research-tool`이며,
LOCALAPPDATA가 없으면 사용자 홈의 `AppData/Local`을 사용한다.
DB·workspace·backups 하위 경로는 계산만 하고 생성하지 않는다. 상대 경로 설정은 거부한다.
실제 연구자료 위치나 사용자별 절대경로는 소스에 넣지 않는다.

logging은 앱 이름 공간의 모듈 logger를 사용하며 기본 INFO 레벨로 stderr에 출력한다.
실제 로그 파일·로테이션·보관 정책은 후속 단계에서 정한다.
현재 시작 로그에 환경값·사용자 경로·원본자료를 넣지 않는다.
로깅 기반이 임의 민감정보를 자동 제거해 주는 것은 아니므로 향후 호출부에서도
비밀번호·인증정보·IP·RTSP·연락처·원본 셀 값을 기록하지 않아야 한다.
공통 예외 계층은 실제 Service 예외가 필요한 단계에서 도입한다.

## SQLite 기반 API

`database.initialize_database(db_path)`는 지정한 DB를 초기화하고 연결을 닫은 뒤
적용 버전 번호를 반환한다. 경로를 생략해 명시적으로 호출하면 Phase 0 설정의
`database_dir/research.sqlite3`를 사용한다. 앱 시작이나 패키지 import만으로 생성하지 않는다.
테스트는 `tmp_path` 아래 synthetic DB만 사용한다.

`connect_database(db_path)`의 반환 연결은 호출자가 닫는다. 연결마다 foreign_keys를
활성화·확인하며, 업무 쓰기는 `transaction(connection)` 안에서 수행한다.
이 helper는 명시적 BEGIN IMMEDIATE/COMMIT/ROLLBACK을 사용하고 중첩 transaction을 거부한다.

`get_schema_version(connection)`은 빈 DB에서 0, 현재 초기 스키마에서 1을 반환한다.
`apply_migrations(connection)`은 전용 유휴 연결에서 `001_initial.sql`부터 번호순으로 적용한다.
schema_version에는 `001` 형식의 버전, 파일명, 앱 버전, UTC 적용 시각을 기록한다.
각 migration의 DDL·DML과 버전 기록을 함께 확정하고 실패하면 해당 migration만 rollback한다.
이미 적용된 migration은 재실행하지 않으며 최신 상태에서는 스키마·기록을 변경하지 않는다.
번호 중복·누락, 미등록 기존 DB, 비호환 버전/파일명은 자동 보정하지 않고 거부한다.
적용한 SQL 파일은 수정하지 않고 다음 번호 파일을 추가한다. SQL 안의 transaction·PRAGMA·
ATTACH/DETACH는 허용하지 않으며, SQL 파일은 패키지 데이터로 포함한다.

제약은 DATABASE_DESIGN.md를 따른다. 현재 사용값 부분 UNIQUE는 활성 행만 대상으로 한다.
관리코드 구성요소는 DB에서 길이를 검사하며 숫자 구성·연결 일치는 후속 Service 책임이다.
login_id는 정규화된 소문자 저장 형태만 허용하며 DB가 자동 변환하지 않는다.
role·매핑 상태/방법·quality_status 등 닫힌 목록이 확정되지 않은 필드는 임의 enum으로 제한하지 않는다.
날짜/JSON 형식, provenance 교차 일치, 현재값 선정·QC 실행도 후속 Phase 책임이다.

## 테스트와 코드 검사

설치 후 저장소 루트에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

단위 테스트는 import·메타데이터·경로·logging을 검사한다.
통합 smoke test는 설치된 module/console 진입점을 임시 작업 폴더에서 실행한다.
DB 통합 테스트는 19개 테이블·39개 FK, 제약 위반 거부, 재초기화·순차 적용과
DDL/DML/버전 기록 실패 rollback을 검증한다.
실제 연구자료, 운영 DB, GUI 환경에 의존하지 않는다.

## 구조

```text
pyproject.toml
README.md
AGENTS.md / docs/                 기존 개발지침·설계문서
src/small_stream_research_tool/
  __init__.py / __main__.py
  app/main.py                    시작점
  config/settings.py             앱 정보·경로 계산
  database/
    __init__.py                  명시적 초기화 API
    connection.py                FK 활성화 연결·transaction
    migrations.py                버전 조회·순차 migration runner
    migrations/001_initial.sql   V1 초기 스키마
  utils/logging.py                콘솔 로깅
tests/
  unit/                          설정·로깅
  integration/                   시작점·SQLite 제약·migration 검증
```

`ui`, `services`, `repositories`, `models` 등은 해당 Phase에서 필요할 때
생성한다. 이후에도 UI → Service → Repository → Database 방향을 유지한다.
설계문서의 ‘구현 전’ 표현은 설계 기준 시점이며 현재 구현 상태는 이 README에서 설명한다.

## 자료 보호

실제 연구 Excel/CSV·운영 DB·workspace·백업·출력물과 민감 운영정보는 Git에 올리지 않는다.
기존 `.gitignore` 정책을 유지하며 synthetic fixture도 개별 검토 후에만 예외를 둔다.
UI PNG는 추적할 수 있으나 분석 출력은 `exports/` 같은 제외 경로에 저장한다.
원본 자료를 fixture라는 이름으로 복사하지 않는다.
