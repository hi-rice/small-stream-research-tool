# small-stream-research-tool

표시명: **소하천 데이터 관리** · NDMI

국립재난안전연구원의 소하천 연구업무를 위한 Windows 로컬·오프라인 프로그램이다.
다양한 Excel 연구자료를 데이터 사전에 맞춰 관리하고 출처와 변경이력을 보존하는 것을 목표로 한다.

## 현재 상태

Phase 0 개발 기반과 Phase 1 SQLite 기반을 제공한다. DB 연결, 19개 V1 테이블,
39개 FK, CHECK·UNIQUE·부분 유일 인덱스와 순차 SQL migration을 구현했다.
CLI는 시작 확인 메시지를 기록하고 종료하며 DB 초기화는 명시적 API 호출로만 수행한다.
Phase 1A는 사용자 생성·인증·비밀번호 변경·활성 상태 처리의 백엔드를 제공한다.
Phase 2는 분류·사전 버전·단위·변환 규칙·표준 항목·별칭 관리와 정확한 별칭 lookup을 제공한다.
Phase 3는 .xlsx 구조·명시적 헤더 범위·원본 행/셀을 읽는 Excel Reader를 제공한다.
Phase 4는 소하천 관리코드의 문자열 후보 생성·검증·원본/구성요소 비교를 제공한다.
Phase 5A는 정확한 별칭 기반 컬럼 매핑 draft와 사용자별 로컬 Workspace JSON을 제공한다.
Phase 5B는 행별 관리코드 검증·기존 하천 조회·표시 정책을 적용한 Import Preview를 제공한다.
Phase 6A는 사전 자료형에 따른 값 정규화와 행별 Import 저장 후보 준비를 제공한다.
Phase 6B-1은 source/Import 출처·소하천·특성값의 SQLite 저장소 primitive를 제공한다.
Phase 6B-2는 단일 시트 Prepared 결과의 실제 DB Import Execution을 제공한다.
Phase 6C는 RUNNING Import의 근거 검사와 명시적 SUCCESS 종료 복구를 제공한다.
Phase 7B-1은 명시적 대상을 검사하고 issue를 생성하는 범용 QC 기반을 제공한다.
Phase 8A는 명시적 현재값 선택, Phase 8B는 새 USER_CORRECTION 값 생성,
Phase 8C는 특성값 비활성화·복원과 현재값 참조 캐시 재구축 백엔드를 제공한다.
Phase 8 Final Gate는 Phase 7 QC와 Phase 8A/B/C의 합성 DB lifecycle 통합 검증을 통과했다.
Phase 9A는 GUI 없이 목록·검색·페이지·기본 상세·현재값/QC/출처의 안전한 조회 backend를 제공한다.
Phase 9B는 로컬 로그인·앱 shell·소하천 목록 GUI를 제공하고 Phase 9C는 상세 GUI를 제공한다.
Phase 9C-0는 상세 조회 전에 사용할 운영 연구 사전을 versioned manifest로 bootstrap한다.
Phase 9C는 목록에서 관리코드로 다시 조회하는 읽기 전용 상세 화면을 제공한다. 기본정보·좌표,
category별 70개 승인 특성, 현재 사용값 상태, 활성 QC·검토상태, 안전한 출처와 값 이력을 표시한다.
Phase 9C-UI는 Figma 09 화면에 맞춰 240px sidebar, 58px topbar, 조밀한 검색 영역,
목록과 선택 요약 패널 및 상세 화면의 색상·간격·타이포그래피를 정렬했다.
Phase 9D-1은 GUI 없이 Home·작업이력·마이페이지가 공유하는 읽기 전용 projection backend를
제공한다. Home 집계, 실제 record_history event의 안전한 대상 해석, 공개 사용자 profile과
bounded 최근 이력을 제공하며 raw JSON·내부 ID·password hash·절대경로는 반환하지 않는다.
Phase 9D-2는 로그인 후 Home에 활성 소하천·QC 집계·연구 사전 상태와 최근 5개 작업을
읽기 전용으로 표시한다. Phase 9D-3은 주요 연구 데이터 변경이력을 50건 단위로 조회하고
작업 유형·작업자·관리코드로 필터링한다.
Phase 9D-4는 Topbar에서 현재 작업자의 공개 계정정보와 최근 작업을 조회하는 읽기 전용
마이페이지를 제공한다. Phase 9 Final Gate는 합성 임시 DB에서 로그인부터 Home·목록·상세·
작업이력·마이페이지·로그아웃까지의 읽기 전용 통합 흐름과 DB 불변성을 검증했다.
실제 Windows 최종 육안 검수와 scrollbar 등 visual polish는 별도 후속 확인 항목이다.

## 환경과 의존성

- Python **3.12.x**, Windows를 기본 대상으로 한다.
- 표준 `venv` + `pip`, `pyproject.toml` + setuptools의 `src` 패키지 구조를 사용한다.
  별도 패키지 관리자 없이 Python 기본 도구로 설치·검증하기 위한 선택이다.
- 실행 의존성은 Python 표준 라이브러리, 비밀번호용 argon2-cffi, Excel 읽기용 openpyxl,
  데스크톱 GUI용 PySide6이다.
- 개발 도구는 pytest(테스트), ruff(lint·format)다. mypy는 도입하지 않았다.
- 향후 pandas, matplotlib는 실제 사용하는 Phase에서 추가한다.
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
기본 실행은 로컬 DB를 초기화/마이그레이션하고 최초 사용자 등록 또는 로그인 창을 연다.
`--version`/`--help`는 GUI·DB를 시작하지 않는다. 초기 등록은 사용자 0명일 때만 제공한다.
실행 전 `LOCALAPPDATA`가 올바른 절대 경로인지 확인한다. 연구 DB 대신 합성 DB로 확인하려면
별도 임시 `LOCALAPPDATA`를 지정한다.

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
사용자/인증 application exception은 `models/errors.py`에 둔다. 오류 메시지에 입력 비밀을 넣지 않는다.

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

## 로컬 인증 백엔드

`UserRepository(connection)`과 `AuthService(repository)`를 명시적으로 구성한다.
Service는 `create_user`, `authenticate`, `change_password`, `set_active`,
`needs_initial_user_setup`을 제공한다. 기본 계정을 자동 생성하지 않는다.
초기 등록 필요 여부는 비활성 계정도 포함한 전체 사용자 수가 0인지로 판단한다.
활성 상태 변경은 계정을 보존하며, 비활성 계정의 로그인·비밀번호 변경은 거부한다.
생성·인증·변경 작업은 기존 transaction 기반을 사용하고 성공 시 UTC 시각을 기록한다.
로그인 성공은 last_login_at과 updated_at을 갱신하며 실패 시 변경하지 않는다.

비밀번호는 argon2-cffi의 Argon2id `RFC_9106_LOW_MEMORY` 프로필로 처리한다
(memory 64 MiB, time cost 3, parallelism 4). salt와 hash encoding은 라이브러리가 관리한다.
[argon2-cffi 문서](https://argon2-cffi.readthedocs.io/en/stable/howto.html)를 따른다.
구현 정책으로 최소 15자, 빈 값·공백만 있는 값 금지를 적용한다.
최소 길이는 [NIST SP 800-63B-4의 단일 비밀번호 인증 기준](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)을 참고했다.
대문자·숫자·특수문자를 강제하지 않고, 앞뒤 공백을 포함한 입력을 그대로 검증한다.
비밀번호의 trim·Unicode 정규화·절단을 수행하지 않는다.

login_id는 앞뒤 공백 제거 → 소문자 변환 → ASCII 허용 문자·4~50자 검증을 적용한다.
표시명은 필수이며 부서·role은 nullable 메타데이터다. role 권한 체계는 구현하지 않았다.
Repository의 내부 `UserRecord`만 password_hash를 보유하며 repr에서 제외한다.
Service는 hash 없는 `User`를 반환한다. 내부 인증 레코드를 일반 출력·직렬화에 사용하지 않는다.
계정 상태·생성 API는 향후 앱 workflow의 기반이며 세션이나 관리자 권한 검사를 대신하지 않는다.

V1에서는 자동 비밀번호 복구를 제공하지 않는다. 이메일/전화번호·DB 직접 수정 복구,
임시 비밀번호 발급은 없으며 로그인·최초 등록 GUI도 아직 없다.

## 데이터 사전 기반

`DictionaryRepository(connection)` → `DictionaryService(repository)`로 구성한다.
분류·단위·표준 항목·별칭을 등록/조회/비활성화하고 사전 버전의 현재 상태를 전환한다.
물리 삭제 API와 연구 항목 seed는 없다. 날짜는 기존 UTC utility를 사용한다.
현재 버전 전환과 폐기 처리는 Service transaction으로 원자적으로 수행한다.

`create_item`의 data_type은 REAL/INTEGER/TEXT/DATE/DATETIME이며 사전의 기존 필드를 사용한다.
internal_name·category_key·단위 기호는 앞뒤 공백만 제거하고 대소문자를 보존한다.
단위는 unit_name/unit_symbol/dimension 구조이며 별도 key·설명·source 컬럼을 추가하지 않는다.
표준명 조회는 같은 표시명을 가진 여러 항목을 반환할 수 있다.
목록의 active/analyzable 필터는 해당 항목 상태를 기준으로 하며 연구 적합성을 자동 판정하지 않는다.

`normalize_alias`의 구현 정책은 NFC → 연속 whitespace를 한 칸으로 축약 → ASCII 영문 소문자화다.
단어 사이 공백·구두점·단위 표기·위첨자를 제거하지 않는다. 다른 표현은 별칭으로 명시 등록한다.
`find_dictionary_by_header(raw_header, source_scope=None)`는 정확한 별칭만 조회한다.
scope는 앞뒤 공백만 제거하고 대소문자를 구분한다. 생략하면 스키마의 GLOBAL을 사용한다.
명시 scope에 등록이 없을 때만 GLOBAL로 fallback하며 미매칭은 None이다.
등록된 scope 별칭이 비활성 또는 대상 항목이 사용 불가이면 다른 GLOBAL 의미로 대체하지 않는다.
lookup은 활성 별칭·활성/미폐기 항목·활성 분류·활성 단위(지정된 경우)를 요구한다.
빈/잘못된 header는 입력 오류다. 비활성 별칭도 기존 UNIQUE 식별자를 유지한다.

`register_conversion(..., approved=True)`는 사용자가 승인한 LINEAR factor/offset만 등록한다.
승인은 이 Service 호출의 전제이며 별도 승인자·승인 상태 컬럼을 만들지 않는다.
`convert_value`는 유한한 숫자와 활성 단위·등록된 활성 규칙으로 `value * factor + offset`만 계산한다.
자동 역변환·동일 단위 예외·수식 엔진·Excel 값 변환은 없다. 단위 의미를 추정하지 않는다.

`update_item_definition`은 값·Import 매핑·캐시·QC 규칙/issue에서 사용된 항목의 표준명,
내부명, category, data_type, unit, description, storage_type 변경을 거부한다.
이는 의미 보호를 위한 구현 정책이며 변경이 필요하면 새 항목을 등록한다.
미사용 활성 항목은 검증 후 해당 필드를 수정할 수 있다. 같은 값의 재요청은 변경하지 않는다.
`deprecate_item`은 폐기 버전 참조와 비활성 상태를 함께 기록하며 기존 폐기 버전을 덮어쓰지 않는다.
분류/단위 비활성화는 자식이나 과거 자료를 삭제·자동 변경하지 않는다.
사전 변경 이력의 상세 workflow와 Excel 자동매핑 UI는 아직 구현하지 않았다.

## Excel Reader 기반

`services/excel_reader.py`의 `ExcelReader(path)`는 파일 읽기 전용 Service이며 DB에 접근하지 않는다.
`.xlsx`만 지원하고 확장자 대소문자는 구분하지 않는다. `.xls`·`.xlsm` 등은 거부한다.
openpyxl 허용 범위는 `>=3.1.5,<3.2`다. 원본을 저장하거나 값·헤더·수식을 수정하지 않는다.

```python
from small_stream_research_tool.services.excel_reader import ExcelReader

with ExcelReader(path) as reader:  # path는 호출자가 선택한 .xlsx 경로
    info = reader.workbook_info
    sheet_name = info.sheet_names[0]  # 실제 선택은 호출자 책임
    sheet = reader.sheet_info(sheet_name)
    columns = reader.read_columns(sheet_name, header_start_row=1, header_end_row=2)
    preview = reader.read_preview(
        sheet_name, header_start_row=1, header_end_row=2, start_row=4, row_count=10
    )
    for row in reader.iter_rows(
        sheet_name,
        header_start_row=1,
        header_end_row=2,
        data_start_row=4,
        include_blank=False,
    ):
        pass  # row.cells를 후속 처리 계층으로 전달한다.
```

헤더 시작/종료 행은 호출자가 지정하며 자동 탐지·헤더 정규화·사전 매핑을 수행하지 않는다.
`data_start_row` 기본값은 헤더 종료+1이고 명시하면 설명 행 등을 건너뛸 수 있다.
헤더는 시트 내부의 양의 정수 범위, 데이터 시작은 헤더 이후부터 마지막 행+1까지 허용한다.
마지막 행+1은 데이터가 없는 경우이며 빈 iterator를 반환한다. bool·실수는 행 번호로 받지 않는다.

Workbook은 경로·모든 시트명·개수, Sheet는 이름·1-based 순서·크기·병합 범위·숨김 상태를 제공한다.
hidden/veryHidden을 자동 제외하지 않는다. chart sheet도 목록에 보존하되 크기는 None이고
셀 읽기 요청은 application 오류로 거부한다. 크기는 openpyxl의 사용 범위이므로 서식만 있는
셀까지 포함될 수 있으며 실제 연구 데이터 범위로 자동 해석하지 않는다.

컬럼은 시트 전체 열 범위와 원본 열 번호/문자를 유지한다. 각 `header_parts`는 실제 위치의
`cell`과 병합 범위·`merged_anchor`를 분리해 보존한다. 실제 병합 범위만 anchor를 참조하며
일반 빈 셀을 forward-fill하지 않는다. `display_header`는 None을 제외한 표시 문자열을
` | `로 연결한다. 동일 세로 병합 anchor의 반복 표시는 생략하지만 모든 원본 part는 유지한다.
빈 헤더는 빈 문자열, 중복 헤더는 동일 문자열로 유지하며 이름을 생성/변경하지 않는다.
숫자·날짜 헤더도 원본 native 값은 보존하고 표시 문자열만 생성한다.

`ExcelCell`은 1-based 행/열·열 문자·좌표·native 값·openpyxl value type·수식 여부·number format을
보존한다. 문자열 `001`/`3.50`은 그대로, 숫자 1과 서식 `000`은 별도 정보로 전달한다.
날짜·시간에 timezone을 임의 추가하지 않는다. 일반 수식은 `=...`와 `is_formula=True`,
배열/데이터 테이블 수식은 library 객체 대신 `ExcelFormula`의 표현·속성으로 전달한다.
Excel 오류 타입 `e`와 같은 글자의 일반 문자열 타입 `s`도 구분한다. 수식을 계산하지 않는다.

명시적 로딩 옵션은 `read_only=False`, `data_only=False`, `keep_vba=False`, `keep_links=False`,
`rich_text=False`다. 병합 메타데이터와 수식 보존을 우선하며 외부 링크 캐시·매크로·rich-text
서식은 읽기 대상이 아니다. [openpyxl 로딩 옵션 문서](https://openpyxl.readthedocs.io/en/stable/api/openpyxl.reader.excel.html)를 참고한다.
workbook은 일반 모드로 메모리에 로딩하므로 대용량 상수 메모리 streaming을 보장하지 않는다.
행 모델은 iterator로 한 행씩 만들며 전체 시트를 별도 list로 복제하지 않는다.
일반 모드의 빈 좌표 조회도 내부 셀 객체를 만들 수 있으므로 서식으로 크게 확장된 시트는
추후 실제 규모 확인 후 최적화한다. 별도 디스크 파일이나 DB에는 복제하지 않는다.

`ExcelRow.is_blank`는 모든 셀 값이 None일 때만 True다. 공백 문자열·0·False·수식·일부 열만
있는 마지막 행은 보존한다. `include_blank`로 완전히 빈 행의 포함/제외를 선택한다.
Preview는 빈 행을 포함한 실제 행 범위 중 최대 `row_count`개와 컬럼 메타데이터를 반환하며
0개 요청도 허용한다. Import 적합성 판정·QC·UNMAPPED 결정 기능은 없다.

Reader는 한 번만 로딩하며 읽기 전용 파일 handle은 로딩 성공/실패 직후 닫는다.
context 종료 또는 멱등 `close()`로 workbook을 해제한다. 행 iterator는 Reader가 열린 동안
소비해야 한다. 오류는 `models/excel_errors.py`의 application 예외로 전달하며 메시지에
원본 경로·셀 값·library 오류 원문을 넣지 않는다. 모델에 보존된 원본값 자체는 민감정보를
포함할 수 있으므로 후속 UI/로그/Export에서는 별도 표시·차단 정책이 필요하다.

## 소하천 관리코드 검증 기반

`services/stream_code_service.py`는 파일·DB·네트워크 I/O 없는 순수 함수다.
`normalize_component(name, value, number_format=...)`, `validate_source_code(value, ...)`,
`validate_stream_code(source_code=..., province_code=..., city_county_code=...,
town_code=..., stream_serial_no=..., number_formats=...)`를 제공한다.
`number_formats`는 해당 필드명 → 서식의 선택적 mapping이다.
구성 순서는 2+3+3+3이며 모든 유효 후보와 생성 코드는 ASCII 숫자 문자열이다.

문자열은 앞뒤 whitespace만 제거한다. 내부 공백·Unicode 숫자·부호·소수점·과학적 표기를
허용하지 않으며 짧은 문자열은 서식이 있어도 padding하지 않는다. None·빈 문자열은 MISSING이다.
정수는 음수가 아니어야 한다. float는 유한한 정수값만 허용하며 음의 0·비정수·NaN/Inf는 거부한다.
숫자의 자릿수가 기대 길이와 같고 서식이 None/General이면 패딩 없이 문자열 후보로 검증한다.
짧은 숫자는 AMBIGUOUS이며, 서식이 기대 길이만큼의 `0`과 정확히 같을 때만 padding 후보를 만든다.
예를 들어 synthetic 값 9와 `000`은 `009` 후보가 된다. 복잡한 서식·서식 폭 불일치는
해석하지 않고 AMBIGUOUS로 유지한다. 길이 초과 숫자는 INVALID_LENGTH로 거부한다.
일반 관리코드 문자열을 숫자로 바꾸지 않으며 숫자 입력의 문자열화·float 처리·padding·trim은
`normalization_steps`에 기록한다. raw 값과 number_format도 결과에 별도로 보존한다.

검증 상태는 VALID/MISSING/INVALID_FORMAT/INVALID_LENGTH/AMBIGUOUS다.
원본 전체 코드와 구성요소를 독립 검증하고 네 구성요소가 모두 VALID일 때만 생성한다.
둘 다 유효할 때만 MATCH/MISMATCH로 비교하고 나머지는 NOT_COMPARABLE이다.
원본이 없고 생성 가능하면 `SOURCE_MISSING_GENERATED_AVAILABLE` issue로 구분한다.
불변 결과 모델에 필드별 상태·기계용 code·한국어 message를 제공하며 원본을 교체하지 않는다.
VALID는 형식 검증 결과이며 실제 등록된 하천인지 확인하거나 DB 저장을 승인하는 의미가 아니다.

`normalize_excel_code_cell(name, cell)`은 호출자가 선택한 기존 ExcelCell의 값과 서식을 받는다.
전체 코드에는 name=`stream_code`를 사용한다. 수식/Excel 오류 셀은 코드 후보로 사용하지 않는다.
ExcelCell·Reader를 변경하거나 파일·컬럼을 자동 탐색하지 않는다.
잘못된 필드명·기대 길이·서식 인자 등의 API 오용은 `StreamCodeArgumentError`,
일반 원본값 오류는 검증 결과로 반환한다. 새 의존성·DB 쓰기·중복 조회·QC 저장은 없다.
로드맵의 중복 검출 연계는 이번 요청 범위에서 구현하지 않았다.

## 컬럼 매핑 Draft와 로컬 Workspace

`ColumnMappingService(dictionary_service)`는 기존 `find_dictionary_by_header`를 호출한다.
`build_initial_mappings(columns, source_scope=None)`는 Phase 3 `ExcelColumn.display_header`를
그대로 조회하며 기존 NFC/공백 축약/ASCII 소문자화·scope lookup 정책을 재사용한다.
정확한 scope → GLOBAL 순서이고 비활성 exact-scope 별칭은 GLOBAL로 대체하지 않는다.
빈/미등록 헤더는 UNMAPPED이며 fuzzy·의미 추론·컬럼 순서 추론은 없다.
중복 헤더도 원본 열 번호별로 보존하며 헤더 part는 원본 행·표시 문자열·병합 anchor를 유지한다.
이 모델에는 데이터 행이나 ExcelCell 객체를 넣지 않는다.

Draft 상태는 AUTO_MAPPED/USER_MAPPED/UNMAPPED/DO_NOT_MAP/NEEDS_REVIEW다.
방법은 AUTO_ALIAS/USER/NONE이며 자동 상태는 등록 별칭으로 얻은 후보를 뜻한다.
이 enum은 메모리/Workspace 계약이며 DB mapping_status 예시를 변경하거나 저장하지 않는다.
`set_user_mapping(mapping, dictionary_id)`는 활성/미폐기 항목과 활성 분류·단위를 확인한다.
`clear_mapping`은 미매핑, `mark_do_not_map`은 의도적 제외로 전환하고 원본 metadata는 유지한다.
수동 선택을 column_alias 규칙으로 자동 저장하지 않는다.
`refresh_auto_mappings`는 AUTO_MAPPED/UNMAPPED만 재평가하며 사용자 선택·제외·재검토는 유지한다.
`mapping_summary`는 상태별 개수만 반환한다. 행별 판정·QC·값 변환은 없다.

`WorkspaceService()`는 기존 경로 정책의 `%LOCALAPPDATA%/NDMI/small-stream-research-tool/workspace`
아래 `user_<user_id>.json` 하나를 사용한다. 생성자·조회만으로 디렉터리를 만들지 않으며
저장 시 생성한다. 테스트는 `WorkspaceService(tmp_path / "workspace")`처럼 주입한다.
repository 내부 경로와 사용자 파일의 symlink 우회는 거부한다.
단일 사용자 로컬 작업이 전제이며 동시 writer 조정이나 인증 session을 구현하지 않는다.

`create_workspace(current_user_id=..., source_file_path=...)`는 FILE_SELECTED draft와 원본 hash를
만든다. 이후 Reader/매핑 결과를 이용해 불변 draft의 시트·행 범위·매핑·단계를 갱신한다.
원본 검증을 위해 파일 선택 때 hash를 확보하고 같은 draft를 후속 작업에 전달한다.
단계는 FILE_SELECTED/HEADER_CONFIGURED/MAPPING/CODE_VALIDATION/PREVIEW이며 첫 단계에는 시트·헤더가 None,
후속 단계에는 선택한 시트·헤더 시작/종료·데이터 시작 행이 필요하다.
`save_workspace(draft, current_user_id)`는 hash를 다시 확인하고 저장 시각을 갱신한다.
원본이 달라졌으면 저장을 거부하며 오래된 매핑을 새 hash로 자동 승인하지 않는다.

V1 JSON에는 workspace_version=1, user_id, source_file_path, source_file_sha256,
selected_sheet_name, header_start_row, header_end_row, data_start_row, column_mappings,
current_step, saved_at, source_scope만 저장한다. 매핑/헤더 part도 정해진 필드만 허용하고
알 수 없는 필드·중복 JSON 키·잘못된 타입/상태 조합·지원하지 않는 버전은 거부한다.
SHA-256은 1 MiB chunk로 읽으며 저장 시각은 기존 UTC helper를 사용한다.
전체 JSON은 8 MiB, 개별 텍스트 metadata는 8,192자까지 허용한다.

`load_workspace(current_user_id)`는 JSON·버전·소유자·원본 존재/파일 여부·hash를 검증한다.
사전 재검증까지 포함한 재개 API는 `ColumnMappingService.resume_workspace(workspace_service,
current_user_id)`다. 결과의 original은 저장된 선택, resumed는 재검증된 선택이다.
대상 사전 항목의 삭제/비활성/폐기 또는 자동매핑 별칭 변경 시 기존 ID를 유지하며
NEEDS_REVIEW로 표시하고 다른 항목으로 바꾸지 않는다. 재개만으로 JSON을 다시 저장하지 않는다.
파일 없음·hash 불일치는 재개를 거부하며 자동 검색·원본 재지정 기능은 후속 단계다.
Workspace가 없으면 None이다. WorkspaceService 자체는 사전/연구 DB를 조회하지 않는다.

저장은 같은 폴더의 임시 파일 쓰기 → flush/fsync → 닫기 → os.replace로 수행한다.
일반 쓰기 실패 시 기존 JSON을 보존하고 자체 임시 파일을 정리한다. 강제 종료/전원 장애로
교체 전 임시 파일이 남을 가능성은 있으며 자동 재개 대상으로 읽지 않는다.
`delete_workspace(user_id)`는 해당 사용자 JSON만 삭제하며 없으면 False다.
자동 만료는 두지 않고 명시적 취소로 삭제한다. Import 성공 후 정리는 Phase 6에서 연결한다.

원본 데이터 행·전체 셀·비밀번호/hash·임의 민감 필드는 저장하지 않는다. 메타데이터의
비밀번호/서비스키 표기·IP·RTSP·연락처 등 보수적 탐지에 걸리면 저장/재개를 거부한다.
값을 임의로 마스킹해 원본 헤더를 바꾸지 않는다. 이 검사는 임의 문자열 속 모든 비밀을
판별하는 기능은 아니므로 후속 UI의 민감정보 확인·차단 정책을 대신하지 않는다.
새 Service는 원본값·경로·JSON을 로그에 기록하지 않고 application 오류에 입력을 넣지 않는다.
호출자는 현재 유효한 사용자 ID와 DB 문맥을 제공해야 한다. 숫자 ID 검사는 인증이나
DB 복원 후 동일인 확인을 대신하지 않으며 복원 시 재연결은 기존 Phase 14 계약에서 다룬다.

## 행별 Import Preview

`ImportPreviewService(dictionary_service, StreamLookupRepository(connection))`는 이미 초기화된
DB 연결을 사용한다. 새 DB나 대체 in-memory DB를 만들지 않는다.
`build_preview(rows, mappings, excluded_rows=..., field_policy=...)`는 입력 범위의 결과와
상태별 summary를 반환한다. 대량 행은 `iter_preview_rows`로 순회할 수 있다.
행·셀은 원본 1-based 위치로 연결하며 동일 헤더 문자열이나 tuple의 배열 순서로 찾지 않는다.

매핑을 재검증한 뒤 AUTO_MAPPED/USER_MAPPED만 사용한다. 사전 ID 숫자 대신 정확한
internal_name으로 stream_code·네 구성요소·stream_name을 구분한다. 동일 semantic의 중복은
Preview issue로 표시하며 첫/마지막 컬럼을 임의 선택하지 않는다. 재검토 매핑도 차단한다.
일반 UNMAPPED/DO_NOT_MAP 값은 사용하지 않고 일반 required 항목 전체를 자동 차단하지 않는다.

Phase 4의 `validate_stream_code_cells`가 기존 셀 정규화와 공통 비교 로직을 재사용한다.
원본/생성 코드가 MATCH이면 원본 후보, 원본이 MISSING이고 구성요소가 유효하면 생성 후보를 쓴다.
유효한 원본 코드만 있고 구성요소가 누락된 경우도 후보로 허용하며 검증 불가 사실은 유지한다.
불일치·잘못된 코드·모호한 숫자·관리코드 수식/오류 셀은 자동 선택하지 않는다.
원본이 잘못되고 생성 코드만 유효한 경우 생성 후보를 보여주되 effective code는 None이다.

안전한 코드와 blocking issue 없는 행만 SELECT한다. PK가 없으면 NEW_STREAM,
있으면 EXISTING_STREAM이며 비활성 기존 레코드도 존재하는 것으로 조회한다.
이는 업데이트/덮어쓰기 예정이라는 뜻이 아니다. 차단 문제는 NEEDS_REVIEW,
명시적 `excluded_rows`는 EXCLUDED가 우선이며 제외 행은 조회하지 않는다.
원본·생성·effective 코드와 비교 상태를 분리한다. 완전히 빈 행은 기본 생략하되
부분/마지막 행은 보존한다. 명시적으로 제외한 빈 행도 EXCLUDED로 표시한다.
`include_blank=True`로 빈 행을 포함할 수 있다. Summary는 포함된 행의 네 상태 개수다.

`PreviewFieldPolicy`는 excluded_internal_names/masked_internal_names의 frozenset을 받는다.
확정된 운영정보 internal_name 목록이 없으므로 기본값은 둘 다 비어 있다.
실제 dictionary seed/운영 단계에서 명시적으로 정책을 제공해야 하며 기본 Preview가
민감정보를 자동으로 탐지·제거한다고 간주하지 않는다. 새 secret detector는 만들지 않았다.
정책은 raw header가 아닌 internal_name에 적용한다. 제외가 마스킹보다 우선하며 마스킹은
고정 `[MASKED]` 문자열이다. 연구 식별자인 전체/구성 관리코드 필드는 숨김 대상으로 받지 않는다.

`mapped_values`와 전체 검증 결과는 런타임 내부 객체다. 일반 UI에는 반드시 `row.to_display()`의
별도 payload를 전달한다. 이 payload에는 정책 제외값이나 원본 ExcelCell이 없으며 stream_name의
별도 표시 경로에도 동일 정책을 적용한다. 내부 객체 전체를 UI/로그/Export에 직렬화하지 않는다.
Issue는 코드·고정 메시지·blocking 여부·원본 열 번호만 담으며 영구 data_quality_issue가 아니다.
stream_name이 없다는 이유만으로 차단하지 않는다. 실제 DB Import의 필수값 검증은 별도 계약이다.

Workspace version 1과 JSON 필드는 유지하고 current_step 허용값만 확장했다.
새 구현은 기존 5A JSON도 읽는다. 구버전 앱은 새 단계값을 지원하지 않으므로 최신 앱으로 재개한다.
`rebuild_from_workspace(workspace_service, current_user_id, ...)`는 원본 hash·매핑 재검증 후
Excel을 다시 열어 Preview를 만들고 완료 직후에도 hash를 확인한다. 재생성 자체는 Workspace를
저장하지 않는다. Preview 행·값·issue·표시 정책·행 제외 선택은 JSON에 추가하지 않았다.
재개 후 정책·제외 선택은 호출자가 다시 제공한다. DB 조회는 SELECT만 하며 commit/쓰기/스키마
변경을 하지 않는다. 일관된 DB 읽기 transaction이 필요하면 기존 연결의 호출자가 관리한다.
typed value와 준비 단계 필수값은 아래 Phase 6A를 따른다. 실제 민감 필드 정책과 T1 복구 계약은
실제 DB Import 구현 전에 확인한다.

## Phase 6A Import Preparation

`ImportPreparationService(dictionary_service).prepare(preview_result.rows, field_policy=...)`는
불변 `ImportPreparationResult(rows, summary)`를 반환한다. `prepare_row`와
`iter_prepared_rows`도 제공한다. Preview의 표시값이 아닌 내부 `mapped_values`의 ExcelCell을
사용하며, 사전의 현재 활성 상태·자료형·매핑 의미와 관리코드를 다시 검증한다.

상태는 `READY / BLOCKED / EXCLUDED`, READY 행의 작업은
`CREATE_STREAM / USE_EXISTING_STREAM`이다. Preview 차단은 해제하지 않는다.
신규 하천에는 유효한 11자리 코드, 일치하는 네 구성코드, 비어 있지 않은 원본 하천명이 필요하다.
전체 코드만 있는 신규 행은 구성요소를 임의 생성하지 않고 차단한다. 검증된 코드의 서식 기반
후보는 Phase 4 규칙을 재사용한다. 이름 placeholder를 생성하지 않는다.

신규 기본정보는 `PreparedStreamData`로, 동적 특성은 `PreparedCharacteristicValue`로 분리한다.
행정명·수계·주소·위경도도 일반 특성값으로 중복 준비하지 않는다. 신규 선택 core 항목은 매핑된
값만 검사하며 좌표는 기존 SQL의 위도 ±90 / 경도 ±180 범위를 따른다. 기존 하천은 이름 누락이나
다른 core 값으로 UPDATE 후보를 만들지 않으며 해당 core 변환도 수행하지 않는다.
기존 하천의 준비 특성값이 0개면 no-op BLOCKED, 신규 core가 유효하면 특성값 0개도 READY다.

| 자료형 | 준비 정책 |
| --- | --- |
| REAL | 실제 사전 명칭. 유한 int/float 및 ASCII 십진·지수 문자열을 float 후보로 변환. bool, NaN/Inf, 단위·설명·쉼표 문자열과 0으로 underflow하는 값은 거부 |
| INTEGER | int, 정수인 유한 float, ASCII 정수 문자열만 허용. SQLite signed 64-bit 범위 검사, 소수 문자열·반올림·절삭 금지 |
| TEXT | 문자열 앞뒤 공백만 제거. 숫자·날짜를 임의 문자열화하지 않음 |
| DATE | Python date 또는 정확한 ISO 날짜 문자열. datetime의 시간은 자정이어도 자동 삭제하지 않음 |
| DATETIME | Python datetime 또는 초까지 명시된 ISO 문자열. naive 유지, aware offset 유지. timezone 부여·UTC 환산 없음 |

DATE/DATETIME은 `value_date` TEXT를 공유한다. DATETIME 문자열의 소수초는 최대 6자리이며
알려지지 않은 offset을 뜻할 수 있는 `-00:00`은 거부한다. `Z`는 같은 UTC 의미의 `+00:00`으로
표현하고 원본 문자열은 유지한다. Excel Reader의 날짜 셀이 datetime으로 읽히면 DATE 변환은
차단된다. 시간 제거를 허용할지는 후속 명시적 정책이 필요하다.

None/빈 문자열/공백 문자열은 후보를 만들지 않는다. 일반 항목의 required/nullable 결측은
비차단 `MISSING_VALUE`로 알리고, 신규 core 필수 누락은 차단한다. 수식·Excel 오류는 결측보다
먼저 검사하며 계산하거나 cached result를 사용하지 않는다. Import 대상 변환 실패는 차단하고
실패 값의 후보는 만들지 않는다. 모델 생성 시 네 typed 필드의 exactly-one, 사전 자료형 일치와
유효값·1-based 행/열 위치를 검사한다. BLOCKED 행의 정상 부분 후보는 검토용이며 저장 불가다.
Summary의 create/use-existing 및 prepared_value_count는 READY 행만 센다.

문자열 `original_value`는 공백까지 보존하고, 성공한 숫자·날짜는 TEXT/ISO 표현으로 보존한다.
`unit_id`는 사전 값을 유지한다. 현재 Preview에는 확정 원본 단위 metadata가 없어
`original_unit=None`이며 헤더에서 추정하지 않는다. 등록된 단위변환도 자동 적용하지 않는다.
단위가 확인되었다는 의미는 아니므로 실제 Import 전 원본/사전 단위 확인 계약이 필요하다.

`ImportFieldPolicy(excluded_internal_names=frozenset(...))`는 Preview 표시 정책과 별개다.
internal_name으로 제외된 항목은 원본 표현도 준비하지 않는다. 식별코드 제외 시 행 전체를
차단한다. 기본 제외 목록은 비어 있으며 **실제 민감 field 목록 seed가 필요**하다.
고정 issue 메시지에는 원본 값을 넣지 않는다. 준비 객체는 런타임 내부용으로 UI/로그/Export에
통째로 직렬화하지 않는다. 입력·Workspace JSON·버전 1은 변경하지 않으며 결과를 저장하지 않는다.

사전 SELECT만 사용하고 DB 쓰기·transaction·schema/migration·QC 영구 저장·대표값 변경은 없다.
READY는 DB 저장 성공이나 사전/DB 상태 잠금을 뜻하지 않는다. 일관된 읽기는 호출자가 관리하며
Phase 6B는 실제 쓰기 직전에 출처·사전·기존 하천 상태를 다시 확인해야 한다.
T1의 B commit 후 C 실패에 대한 recovery/idempotency 계약은 Phase 6B/6C 전에 확정하며
이번 단계에서는 구현하지 않았다. 새 의존성은 없다.

## Phase 6B-1 Import Persistence Foundation

`repositories/import_persistence_repository.py`에 다음 6개 클래스를 제공한다.
각 클래스는 기존처럼 `Repository(connection)`으로 같은 SQLite 연결을 전달받는다.

| Repository | API |
| --- | --- |
| SourceFileRepository | create, get_by_id, find_by_hash |
| ImportHistoryRepository | create, get_by_id, get_by_batch_code, update_status, list/count_by_status |
| ImportSheetRepository | create, get_by_id, list/count_by_import_id |
| ImportColumnMappingRepository | create, get_by_id, list/count_by_import_sheet_id |
| SmallStreamRepository | create, create_prepared, get_by_stream_code, exists_by_stream_code, count |
| CharacteristicValueRepository | create, create_prepared, get_by_id, list/count_by_import_id, list/count_by_stream_code, count_by_import_sheet_id, get_provenance |

`create(**values)`의 키는 실제 migration 컬럼명이다. `original_path`, `file_extension`,
`file_modified_at`, `schema_version_id`, `mapping_status`, `transform_rule`을 사용한다.
자동 INTEGER PK는 DB가 발급하며, 생략한 값은 기존 DB DEFAULT/NULL/NOT NULL을 따른다.
ID 조회는 없으면 None, 목록은 PK 순서의 list, count는 정수다. 동일 file_hash 등록을 거부하지
않으며 `find_by_hash`는 비활성 포함 모든 일치 등록을 반환한다. None hash 조회는 빈 목록이다.
batch_code는 정확히 조회하고 UNIQUE 위반을 전달한다. UUID·hash·시각을 자동 생성하지 않는다.

쓰기에는 **호출자가 먼저 연 명시적 transaction이 필수**다. create/update는 BEGIN·COMMIT·
ROLLBACK을 수행하지 않고, transaction이 없으면 `TransactionRequiredError`로 거부한다.
여러 Repository에 같은 연결을 주고 기존 `database.connection.transaction(connection)`으로
묶는다. `repository.transaction()`은 이 helper를 반환하는 기존 스타일의 명시적 편의 API다.
호출자가 성공/실패 경계를 소유하며, 저장 예외가 발생한 업무는 호출자 경계에서 rollback한다.
반환된 레코드는 아직 commit되지 않은 행일 수 있다. 연결 생성·종료도 Repository 책임이 아니다.

`SmallStreamRepository.create_prepared(prepared_stream, timestamp=...)`와
`CharacteristicValueRepository.create_prepared(prepared_value, stream_code=..., timestamp=...,
import_id=..., import_sheet_id=..., mapping_id=..., reference_year=...)`는 Phase 6A 객체를 받아
필드를 그대로 전달한다. timestamp는 호출자가 기존 `utc_now_text()`로 준비한다.
신규 하천의 선택 core 값만 반영하고 기존 core UPDATE/UPSERT/REPLACE는 하지 않는다.
특성값의 source_column_index는 DB 컬럼이 아니며 mapping_id를 통해 추적한다.

Repository는 숫자·날짜 parsing, 단위환산, 민감 필드 선별, 관리코드 padding을 하지 않는다.
`create`는 검증된 값을 받는 하위 primitive이며 Phase 6A 검증을 대체하지 않는다.
typed value exactly-one은 기존 DB CHECK로도 거부된다. 사전 자료형 일치와 Excel 1-based
위치·매핑/시트/Import의 교차 소속 검증은 호출 Service가 책임진다. SQLite affinity를
자료형 검증기로 간주하지 않는다. FK는 기존 `connect_database`에서 활성화한다.

Import history의 6개 status는 DB CHECK를 따른다. `update_status(import_id, status, **changes)`는
finished_at, 행 집계, error_code/error_message만 추가 갱신할 수 있으며 생략 필드는 유지한다.
명시적 None은 NULL로 기록한다. 허용 상태 사이의 업무 전이를 제한하거나 완료 시각을 만들지 않는다.
settings_json은 opaque TEXT로 보존하며 임의 설정 구조를 정의하거나 credential 저장에 사용하지 않는다.

DB mapping_status/mapping_method는 NOT NULL TEXT이며 닫힌 enum CHECK가 없다.
설계의 MAPPED/IGNORED/AMBIGUOUS 등은 예시로, Draft의 AUTO_MAPPED/DO_NOT_MAP/NEEDS_REVIEW와
동일 목록이 아니다. 이번 primitive는 전달된 문자열을 그대로 보존하고 자동 adapter를 만들지 않는다.
Phase 6B-2에서 최종 저장 표현과 필요한 명시적 adapter를 정한다. dictionary_id=NULL인
UNMAPPED/DO_NOT_MAP metadata도 저장 가능하며 원본 셀 전체를 저장하지 않는다.

`get_provenance`는 특성값에 명시적으로 저장된 mapping/sheet/import FK와 이력의 source_file을
불변 묶음으로 조회한다. NULL 참조를 추정하거나 서로 다른 Import의 FK를 수정하지 않는다.
복수 SELECT의 일관된 snapshot이 필요하면 호출자가 읽기 transaction도 관리한다.
특성값 기본값은 DB의 IMPORT / UNREVIEWED / is_representative=0 / is_active=1이다.
원시 create에 명시한 상태·플래그는 전달하지만 현재 사용값 지정 workflow는 제공하지 않는다.
기존 대표값·stream_characteristic·QC·record_history를 자동 변경하지 않으며 삭제 API도 없다.

조회 모델 6개는 실제 schema 컬럼에 대응하는 frozen dataclass이며 Boolean은 bool로 반환한다.
경로·settings_json·error_message·원본/typed 값 등은 repr에서 제외한다. 레코드 전체를 일반
로그/Export로 직렬화하지 않는다. SQLite error code로 PK/UNIQUE, FK, 기타 제약을 구분하고
일반 SQLite 접근 오류도 고정 메시지의 PersistenceError 계열로 변환한다. 원문 오류를 출력하지 않는다.

저장소는 Phase 6B-2 실행 Service에서 재사용한다. 새 schema/migration/의존성은 없다.

## Phase 6B-2 Import Execution

`ImportExecutionService(connection).execute(request, field_policy=policy)`는 유휴 연결과
`ImportExecutionRequest`를 받는다. 입력은 Phase 6A `ImportPreparationResult`, 매핑 draft tuple,
호출자가 확인한 `SourceFileSnapshot`·`ImportSheetSnapshot`, 현재 사용자 ID다.
원본 Excel을 다시 읽거나 filesystem metadata를 조회하지 않는다. source의 실제 schema 필수값은
file_name·original_path이며 hash 등 선택 필드는 미제공 시 NULL을 보존한다.
sheet_index와 source row/column은 기존 Reader와 동일하게 1-based다.

명시적 `ImportFieldPolicy`가 필수이며 None 또는 정책 생략은 쓰기 없이 거부한다.
운영 민감 internal_name seed는 아직 확정되지 않았다. 호출자가 확인한 정책을 전달해야 하며,
synthetic test의 명시적 empty policy를 운영 기본값으로 간주하지 않는다.
Preflight에서 전체 행·사용자·사전·출처·매핑을 확인한다. BLOCKED가 하나라도 있거나 READY가
0개이면 실행하지 않는다. EXCLUDED의 payload는 저장하지 않는다. 저장 후보의 민감 internal_name,
자료형·단위 참조는 B에서도 다시 확인하며 정책 위반 후보를 조용히 누락시키지 않고 거부한다.

- A: 매 실행 source_file을 새로 생성하고 RUNNING import_history와 함께 commit한다.
  같은 hash는 허용한다. batch_code 미제공 시 UUID를 한 번 생성하고, 기존 batch는 상태와 관계없이
  재진입을 거부한다. A가 실패하면 source도 rollback하고 B/C를 시작하지 않는다.
- B: sheet·mapping·READY 신규 하천·특성값을 한 transaction으로 저장한다.
  어떤 행/저장 단계든 실패하면 sheet와 mapping까지 전부 rollback한다. 부분 Import는 없다.
  CREATE_STREAM은 core만 있어도 가능하며 기존 코드 충돌은 실패한다. USE_EXISTING_STREAM은
  B에서 존재 여부를 확인하고 기존 하천명/core를 변경하지 않는다.
- C: 별도 transaction에서 SUCCESS/FAILED·UTC 종료시각·지원되는 실제 counts를 기록한다.
  B 실패 진단은 고정 코드 `IMPORT_TRANSACTION_FAILED`와 고정 메시지만 저장한다.
  B commit 후 C 실패(T1)는 RUNNING 이력과 B 데이터를 남기고 `ImportFinalizeError`를 반환한다.
  이 예외의 `recovery_required` 및 result의 `data_committed`로 B 실패와 구분한다.
  자동 rollback·repair·retry는 없으며 recovery는 Phase 6C에 남겨둔다.

`ImportExecutionResult`는 불변이며 import/source ID, batch, 상태, B commit 여부, READY/EXCLUDED,
생성/재사용 행 수·특성값 수, 시작/종료시각을 제공한다. Preparation summary는 신뢰하지 않고
실제 행과 성공한 B 작업에서 계산한다. B rollback 시 생성/재사용/특성값 수는 모두 0이다.
DB total_rows는 READY+EXCLUDED, accepted_rows는 commit된 READY 수다. 성공 rejected_rows=0,
B 실패 accepted_rows=0·rejected_rows=NULL이다. QC 미실행이므로 warning_rows=NULL이다.
EXCLUDED를 rejected로 분류하지 않는다. schema에는 제외/특성값 개수 컬럼이 없어 해당 수는
result에서 제공하고, 영구 특성값 수는 import_id로 조회한다. T1의 history accepted_rows는 NULL이며
commit된 sheet의 accepted_rows와 실제 저장 자료가 복구 판단 근거다. sheet SUCCESS는 B commit
시점의 자료 저장 완료만 뜻하며 history 종료 성공이나 QC 통과를 뜻하지 않는다.

mapping_status는 draft 상태를 그대로 보존한다. 열린 TEXT이지만 NOT NULL인 mapping_method는
AUTO_MAPPED→AUTO, USER_MAPPED→USER, UNMAPPED/DO_NOT_MAP→NONE으로 저장한다.
NEEDS_REVIEW는 기존 명확한 AUTO_ALIAS/USER 방법을 보존한다. dictionary 없는 매핑 metadata는
저장하되 값을 만들지 않는다. user_confirmed는 USER_MAPPED/DO_NOT_MAP에서만 참이다.
현재 draft에 없는 source_unit/transform_rule은 추측하지 않고 NULL로 둔다. 특성값의 original_unit과
unit_id는 Prepared 값을 그대로 저장하며 재정규화·단위변환하지 않는다.
source column별 mapping_id를 현재 import/sheet/dictionary와 대조해 연결한다.
새 값은 DB default인 is_representative=0·quality_status=UNREVIEWED·is_active=1을 유지한다.
현재 사용값·stream_characteristic·QC·record_history는 변경하지 않는다.

활성 사용자만 허용하고 자동 계정 생성은 없다. dictionary_version_id는 호출자가 Preparation/
Mapping에 사용한 버전을 전달하면 존재 확인 후 저장하며, 미제공 시 현재 버전을 추측하지 않는다.
기존 Prepared 모델에는 버전 snapshot이 없어 사용 버전의 일치 보장은 호출자 계약이다.
schema_version_id는 현재 DB의 검증된 migration 기록에서 실제 PK를 읽는다.
settings_json은 sheet/header/data 위치와 dictionary_version_id만 whitelist로 결정성 있게 저장한다.
원본값·전체 경로·settings 전체·계정정보를 로그에 출력하지 않으며 입력/result repr에서도 숨긴다.
이 단계는 단일 시트 실행이며 multi-sheet orchestration이나 recovery를 구현하지 않는다.

## Phase 6C Import Recovery / Idempotency

`ImportRecoveryService(connection).inspect(import_id)`는 읽기 transaction의 동일 snapshot에서
상태와 import-owned artifact를 검사한다. `list_recovery_candidates()`는 시간 임계값 없이
현재 RUNNING의 검사 결과를 반환한다. 두 API 모두 데이터를 변경하지 않는다.

- `NO_PERSISTED_DATA`: sheet·mapping·관련 값이 없고 저장 개수 주장과 충돌하지 않는다.
  `can_retry=True`는 검토 후보 표시다. 실행 중인 프로세스의 부재나 중단을 증명하지 않으며,
  기존 batch의 재실행을 허가하지 않는다. 실제 재시도·새 batch 생성·FAILED 전환은 하지 않는다.
- `COMMITTED_CONSISTENT`: 6B-2 snapshot과 단일 SUCCESS sheet, 행 개수, 매핑 상태/방법 및
  값의 import/sheet/mapping·사전·단위·원본 행/열 연결이 일치한다. 명시적 성공 복구가 가능하다.
- `INCONSISTENT`: sheet 수·저장 개수·출처 등 알려진 계약에 모순이 있다. 자동 변경하지 않는다.
- `NOT_RECOVERABLE`: 지원하지 않는 상태/실행 metadata 또는 NULL mapping 등으로 근거가 부족하다.
  NULL 자체를 DB 손상으로 단정하지 않으며 SUCCESS 변경을 거부한다.
- `ALREADY_FINALIZED`: SUCCESS/FAILED/CANCELLED/ROLLED_BACK은 복구 대상이 아니다.

특성값은 import_id뿐 아니라 해당 sheet/mapping으로 들어오는 교차 참조도 검사한다.
값 원문·원본 헤더·파일 경로는 복구 projection에서 읽지 않는다. small_stream 개수나 생성 시각으로
Import 귀속을 추정하지 않는다. core-only 신규 하천은 특성값 0개이며 매핑 0개도 기존 실행 API에서
가능하므로, 단순한 값/매핑 유무로 실패를 판단하지 않는다.
기존 schema/snapshot에 독립된 기대 mapping/value 개수가 없어 두 기대값은 None으로 반환한다.
실제 개수와 distinct source row 수를 확인하고 accepted_rows 초과·중복 행/열/사전 연결을 거부한다.
이 검사는 B 원자성과 sheet를 B에서만 생성한다는 계약에 의존한다. 별도의 manifest가 없으므로
외부 조작에 의한 개별 값 누락까지 완전하게 증명하는 무결성 검사는 아니다.

`recover_success(import_id)`만 BEGIN IMMEDIATE 안에서 상태와 근거를 다시 확인하여
import_history의 SUCCESS·UTC finished_at·검증된 행 개수를 기록한다. 실패 시 해당 변경을 rollback한다.
이미 SUCCESS이면 `changed=False`로 반환하고, 다른 완료 상태나 불충분한 근거는 안전한 오류로 거부한다.
경쟁 호출은 잠금 후 재검사하여 의미 있는 갱신을 한 번만 수행한다. 불변 inspection/result에는
고정 reason code·ID·개수·판정만 제공하고 raw 값·설정 전체·경로를 노출하지 않는다.
source/sheet/mapping/stream/value·현재 사용값·QC·record_history는 생성/수정/삭제하지 않는다.
새 DB status·schema·migration·의존성·자동 retry·cleanup·다중 시트 실행은 추가하지 않았다.

## Phase 7B-1 Generic QC Engine

`QualityControlService(connection).evaluate(request, field_policy=policy)`는 읽기 전용 Finding을,
`run(request, field_policy=policy)`는 동일 검사를 수행한 뒤 새/기존 issue ID를 반환한다.
`QualityControlRequest`는 명시적 `characteristic_value_ids`와 `RequiredImportTarget` 목록을 받는다.
자동 전체 DB 검사나 현재 사용값 선택은 없다. 기존 `ImportFieldPolicy`를 반드시 명시적으로 전달하며,
등록된 민감 internal_name은 규칙 평가에서 제외한다. 운영 민감 항목 seed는 별도 확정이 필요하다.

지원 규칙은 quality_rule.dictionary_id로 연결한 활성 FLEX 항목에 한정한다.
연구 항목명·연구 임계값을 코드에 하드코딩하거나 실제 연구 규칙을 seed하지 않는다.

- `REQUIRED`: target_type=`STREAM_DICTIONARY`, dictionary.required=True인 명시적 규칙이다.
  RequiredImportTarget(stream_code, dictionary_id, import_id)의 SUCCESS Import 안에서
  활성 source_type=IMPORT 특성값이 존재하는지 검사한다. NULL typed 행을 찾지 않으며,
  다른 Import·보정값·현재 사용값을 대신 사용하지 않는다. required 플래그만으로 규칙을 만들지 않는다.
  CORE 필드 검사나 optional 항목의 REQUIRED 규칙은 지원하지 않고 설정 오류로 거부한다.
- `NON_NEGATIVE`: target_type=`CHARACTERISTIC_VALUE`, REAL/INTEGER 항목의 명시한 활성 value ID만
  검사한다. 음수만 Finding이며 0은 허용한다. 모든 숫자 항목에 자동 적용하지 않는다.
- `RANGE`: 같은 값 범위에서 parameters_json의 min/max 한쪽 또는 양쪽을 사용한다.
  include_min/include_max는 생략 시 inclusive이며 명시적 false는 exclusive다.
  숫자 경계·Boolean flag·min≤max·허용 키를 검증한다. NaN/Infinity·중복 JSON 키·타입 오류·
  unsupported rule/target은 고정 메시지의 설정 오류이며 data issue로 저장하지 않는다.
  REQUIRED/NON_NEGATIVE parameter는 NULL 또는 빈 객체만 지원한다.

활성 규칙 정의를 검증한 뒤 해당 dictionary와 명시적 scope에 맞는 규칙만 평가한다.
평가기는 SQL과 분리되어 있으며 저장된 typed 필드의 일관성만 확인한다. 재parsing·단위변환은 없다.
실제 schema의 `default_severity`를 그대로 issue severity에 복사한다. rule_version과 검증된
parameter JSON의 결정적 표현을 snapshot으로 저장하며 새 issue는 UNREVIEWED·is_active=1이다.
원본/비교 값은 이번 단계에서 모두 NULL로 두고 message/issue_type은 고정 문자열을 사용한다.

dedup은 active issue의 rule_id, value ID 또는 stream/dictionary/import scope, 출처,
issue_type, severity, rule version/parameter snapshot을 비교한다. NULL도 명시적으로 비교한다.
동일 판정은 기존 issue ID를 반환하며 검토 상태를 변경하지 않는다. 정의가 달라진 판정은 별도
issue로 보존한다. 평가·dedup·모든 issue INSERT는 하나의 BEGIN IMMEDIATE transaction이며,
중간 저장 실패 시 해당 실행의 issue 전체를 rollback한다. Repository는 commit하지 않는다.

Repository는 활성 규칙/issue 조회와 stream별 active severity 개수도 제공한다.
active ERROR가 있으면 ERROR, WARNING/INFO만 있으면 NEEDS_REVIEW, 없으면 NORMAL이다.
review_status와 독립적인 집계이며 NORMAL은 검사 실행 완료를 증명하지 않는다.
`run()`은 생성 전용 계약을 유지한다. 해소 반영은 아래 Phase 7B-2 `recheck()`를 사용한다.
관리코드·parsing QC 중복 구현, reference/statistical/unit/GIS QC, 자동 보정·DELETE,
stream/value/대표값/현재 사용값 변경 및 review workflow는 포함하지 않는다.

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
인증 테스트는 실제 Argon2id와 임시 SQLite로 정규화·중복·인증·비밀번호 변경·
비활성 계정·실패 rollback·비밀 비노출을 검증한다.
사전 테스트는 synthetic 분류/항목/단위/별칭으로 중복·필터·scope·변환·의미 보호·rollback을 검증한다.
Excel 테스트는 tmp_path에서 생성한 synthetic xlsx로 병합/빈/중복 헤더, native 값·수식·오류,
위치·빈/부분 행·Preview·자원 해제·원본 hash 동일성과 DB 접근 부재를 검증한다.
관리코드 테스트는 synthetic 문자열·숫자·서식으로 형식/폭·원본/후보 독립성·비교·불변성·
ExcelCell 연계·I/O 부재와 경계값 invariant를 검증한다.
매핑 테스트는 synthetic 사전/ExcelColumn과 임시 SQLite로 lookup 재사용·사용자 선택·
DB 쓰기 부재·사전 변경 후 재검토를 확인한다. Workspace 테스트는 tmp_path만 사용하여
JSON 필드 제한·소유권·hash·원자 저장 실패·삭제·원본 미변경을 검증한다.
Preview 테스트는 synthetic 사전·임시 DB에서 코드 선택·중복 semantic·표시 정책·행 보존·
Workspace 재생성과 SQLite authorizer를 통한 SELECT-only/commit 부재를 검증한다.
Preparation 테스트는 자료형 변환 경계·exactly-one·신규/기존 core 분리·정책 제외·결측·
원본 추적·결정성·Workspace 미변경과 SELECT-only/전체 DB 미변경을 검증한다.
Persistence 테스트는 tmp SQLite에서 6개 모델/schema 대조, 저장·출처 조회, FK/중복/제약 오류,
개별 rollback·공유 transaction의 원자성, 내부 commit 부재와 repr/오류 비노출을 검증한다.
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
  utils/timestamps.py             UTC 시스템 시각
  models/user.py / errors.py      사용자 모델·인증 오류
  repositories/user_repository.py 사용자 저장소
  security/passwords.py          Argon2id 비밀번호 처리
  services/auth_service.py       로컬 인증 백엔드
  models/dictionary.py           사전 6개 모델
  models/dictionary_errors.py    사전 application 오류
  repositories/dictionary_repository.py 사전 SQL 저장소
  services/dictionary_service.py 사전 관리·별칭 lookup·등록 변환
  models/excel.py / excel_errors.py Excel 원본 구조 모델·application 오류
  services/excel_reader.py       .xlsx 구조·헤더·행 읽기 전용 Service
  models/stream_code.py / stream_code_errors.py 관리코드 검증 결과·API 오류
  services/stream_code_service.py 관리코드 후보 정규화·생성·독립 검증·비교
  models/column_mapping.py / mapping_errors.py 매핑 draft·상태·오류
  models/workspace.py / workspace_errors.py 재개 metadata·오류
  services/column_mapping_service.py 별칭 후보·수동 선택·재개 사전 재검증
  services/workspace_service.py  사용자별 JSON 저장·원본 검증·삭제
  utils/file_hash.py             chunk 기반 SHA-256
  models/import_preview.py / import_preview_errors.py 런타임 Preview·표시 payload·오류
  repositories/stream_lookup_repository.py 소하천 PK 존재 여부 SELECT
  services/import_preview_service.py 행별 identity Preview·summary·재생성
  models/import_preparation.py / import_preparation_errors.py 저장 후보·준비 오류
  services/import_preparation_service.py 행별 저장 적격성·core/특성 분리·summary
  services/value_normalization_service.py I/O 없는 자료형 변환
  models/import_persistence.py / import_persistence_errors.py DB 조회 모델·안전한 저장소 오류
  repositories/import_persistence_repository.py Import 6개 저장소·Prepared 전달·출처 조회
tests/
  unit/                          설정·로깅
  integration/                   시작점·SQLite 제약·migration 검증
```

`ui`와 다른 업무 모듈은 해당 Phase에서 필요할 때 생성한다.
이후에도 UI → Service → Repository → Database 방향을 유지한다.
설계문서의 ‘구현 전’ 표현은 설계 기준 시점이며 현재 구현 상태는 이 README에서 설명한다.

## 자료 보호

실제 연구 Excel/CSV·운영 DB·workspace·백업·출력물과 민감 운영정보는 Git에 올리지 않는다.
기존 `.gitignore` 정책을 유지하며 synthetic fixture도 개별 검토 후에만 예외를 둔다.
UI PNG는 추적할 수 있으나 분석 출력은 `exports/` 같은 제외 경로에 저장한다.
원본 자료를 fixture라는 이름으로 복사하지 않는다.


## Phase 7B-2 QC Recheck / Issue Reconciliation

`QualityControlService.recheck(request, field_policy=policy, rule_ids=None)`는 기존
`QualityControlRequest`의 명시적 값 ID 및 `RequiredImportTarget`만 재검사한다.
선택적인 `rule_ids`는 중복 없는 양의 정수 tuple이며 생략하면 활성 규칙을 사용한다.
빈 tuple·없는 규칙 ID는 오류다. disabled 규칙이나 정책상 제외된 항목은 검사하지 않으며,
이를 문제 해소로 간주하지 않는다. 삭제된 규칙의 issue 정리는 제공하지 않는다.

기존 평가기와 dedup 키를 재사용한다. 동일한 활성 문제는 ID·검토 정보·snapshot을 유지하고,
실제로 검사한 scope/rule에서 사라진 문제만 `is_active=0`으로 보존한다.
재발은 새 행으로 기록하며 inactive 행을 재활성화하거나 DELETE하지 않는다.
규칙 version·severity·parameters가 바뀌어 dedup 키가 달라지면 기존 snapshot을 보존하고
검사 범위 내 이전 issue를 비활성화한 뒤 현재 정의의 새 issue를 남긴다.

내부 `QCCheckedScope`는 rule·값·소하천·사전·Import·시트·행·컬럼을 구분한다.
REQUIRED는 값 ID 없이 소하천/사전/Import 단위로 검사하며 다른 Import나 보정값은
해당 Import의 필수값 존재를 대신하지 않는다. 다른 scope와 Import parsing issue는 유지한다.
`BEGIN IMMEDIATE` 안에서 평가·조회·생성·비활성화·상태 집계를 수행하고 실패 시 모두 rollback한다.
연구값·대표값·참조 캐시·보정·단위변환은 변경하지 않는다. 현재 사용값/보정 업무는 후속 단계다.

불변 `QualityRecheckResult`는 `checked_count`(실제 평가한 규칙/대상 조합 수),
`finding_count`, `kept_issue_ids`, `created_issue_ids`, `deactivated_issue_ids`,
`qc_status`, `completed_at`(UTC)을 반환한다. `qc_status`는 요청 대상 소하천들의
활성 issue 전체를 집계한 상태로, 미검사/disabled 규칙의 기존 issue도 포함한다.
활성 ERROR는 ERROR, WARNING/INFO만 있으면 NEEDS_REVIEW, 없으면 NORMAL이다.
inactive issue와 review_status는 이 판정에 영향을 주지 않는다. 검사 수 0이나 NORMAL이
전체 규칙 검사를 증명하지는 않는다. schema 변경 없이 구현하며 별도 해소 시각 컬럼은 없다.


## Phase 7C-1 Reference Comparison QC

reference는 정답이 아니라 연구자가 선택한 비교 기준자료다. mismatch는 검토 대상이며
자동 보정이나 reference 값으로 덮어쓰기를 하지 않는다. 하상경사·소하천 연장·유역면적·
계획홍수량은 향후 rule registration 후보이고, 이번 단계에서 운영 규칙을 seed하지 않는다.

`QualityControlService.compare_reference(target_value_id, reference_value_id, rule_id,
field_policy=policy)`는 호출자가 지정한 활성 characteristic_value 두 개만 비교한다.
같은 stream_code와 dictionary_id, 활성 FLEX 사전항목이어야 한다. 같은 ID 비교도 허용하며
동일 값으로 평가한다. 대표값·최신/최초 자료·파일명·최신 계획 연도·source priority를 이용해
어느 쪽도 자동 선택하지 않는다. 관리코드 validator나 CORE 소하천명 비교를 추가하지 않는다.

규칙은 `rule_type=REFERENCE_COMPARE`, `target_type=CHARACTERISTIC_VALUE`이고
명시적인 dictionary_id가 필요하다. severity는 `quality_rule.default_severity`를 따른다.
연구 규칙 등록 기본 정책은 WARNING이지만 엔진이 이를 강제하거나 ERROR로 바꾸지 않는다.
Disabled 규칙은 검사 수 0을 반환하고 기존 issue를 유지한다. 잘못된 요청·규칙은 오류다.

비교 정책:

- INTEGER·REAL·TEXT 지원. DATE/DATETIME 및 CORE 항목은 configuration error.
- 기본은 exact 비교. REAL은 저장된 float의 십진 문자열을 정확한 유리수로 바꾸어 비교한다.
  이는 원본 Excel 소수의 복원이 아니며, `0.1 + 0.2`와 `0.3`의 저장값 차이를 숨기지 않는다.
- TEXT는 공백·대소문자까지 그대로 비교한다. fuzzy matching이나 이름 보정은 없다.
- parameters_json은 NULL/빈 객체 또는 `comparison`(`numeric`/`text`, 자료형과 일치),
  `absolute_tolerance` 또는 `relative_tolerance`를 지원한다. 두 tolerance의 동시 지정은 거부한다.
- 허용오차는 유한한 0 이상의 JSON 숫자만 허용한다. bool·문자열·음수·NaN/Infinity·중복 키·
  미지원 키(RANGE min/max 포함)는 거부한다. TEXT에는 tolerance를 허용하지 않는다.
- 절대 허용오차: `abs(target-reference) <= absolute_tolerance`이면 match.
- 상대 허용오차: `abs(target-reference) <= relative_tolerance * abs(reference)`이면 match.
  reference가 0이면 target도 0이더라도 비교 오류이며 exact fallback하지 않는다.
- 기본 연구 tolerance는 없다. 숫자 비교 연산은 유리수로 수행하여 경계 연산 반올림을 피한다.
- 표준화된 `unit_id`가 같아야 한다. 둘 다 NULL이면 단위 추정 없이 비교하지만,
  한쪽만 NULL이거나 서로 다르면 오류다. original_unit은 원본 출처 문자열이며 변환 근거로
  사용하지 않는다. 자동 단위변환 및 UNIT mismatch issue 생성은 Phase 7C-1에 포함하지 않는다.

Finding은 기존 불변 QCFinding이며 `REFERENCE_VALUE_MISMATCH`를 사용한다.
issue의 출처 컬럼은 target을 가리킨다. 양쪽 provenance의 연결을 검증하지만 reference 출처를
새 컬럼에 복제하지 않는다. raw target/reference는 message·repr·error에 넣지 않고
issue.original_value/compare_value는 NULL로 유지한다.

Schema를 변경하지 않고 reference identity를 다음 versioned snapshot으로 보존한다:

```json
{"format":"reference_compare_v1","rule_parameters":{"absolute_tolerance":0.01},"execution":{"reference_value_id":50}}
```

`rule_parameters`는 원래 quality_rule.parameters_json의 의미를 그대로 보존한다(NULL도 보존).
`execution`은 호출 입력이다. quality_rule 자체를 수정하지 않으며 reference ID를 영구 규칙
parameter로 등록하지 않는다. 기존 일반 QC snapshot 형식도 변경하지 않는다.
Reference ID는 snapshot 안의 논리적 식별자이며 전용 FK가 아니다. reference 자료 자체가
사후 변경되면 이 snapshot만으로 당시 숫자/문자열을 복원할 수는 없다.

Phase 7B-2 공통 reconciliation을 재사용한다. rule·target·reference 쌍과 target provenance가
검사 범위이며, 기존 dedup에 canonical snapshot이 포함되어 reference A/B가 합쳐지지 않는다.
같은 쌍의 동일 mismatch는 ID와 검토 이력을 유지한다. 해소되면 is_active만 0으로 변경하고
재발하면 새 행을 생성한다. 같은 쌍의 규칙 버전·정책·severity 변경은 이전 snapshot을 보존하며
이전 issue 비활성화 및 새 issue 생성을 수행한다. 다른 reference 쌍의 issue는 유지한다.
B를 선택했다는 이유만으로 A와의 문제를 해소하지 않는다. 다른 종류의 QC issue도 유지한다.
손상되거나 모르는 snapshot은 임의 해석하여 비활성화하지 않는다.

반환값은 기존 QualityRecheckResult다. 단일 BEGIN IMMEDIATE에서 검증·평가·dedup·저장·
비활성화·상태 집계를 수행하며 실패 시 모두 rollback한다. status는 target 소하천의 활성 issue
전체를 포함한다. 원본값·small_stream·현재 사용값·참조 캐시·보정 이력은 변경하지 않는다.

기존 evaluate/run/recheck는 reference 입력이 없으므로 REFERENCE_COMPARE를 처리하지 않는
기존 오류 계약을 유지한다. 활성 reference 규칙이 함께 등록되어 있다면 일반 재검사는
`recheck(..., rule_ids=(일반_규칙_ID, ...))`로 범위를 명시하고 reference 비교는 별도 API로 호출한다.
통합 batch orchestration, 기준자료 선택 UI, 과거 기준자료 비교는 이번 범위가 아니다.


## Phase 7C-2 Unit QC

Unit QC는 단위가 분석·비교에 적합한지 연구자에게 확인하도록 알리는 기능이다.
값이 틀렸다고 확정하거나 자동 환산하지 않는다. 기대 단위의 유일한 source-of-truth는
`data_dictionary.unit_id`, 실제 단위는 `characteristic_value.unit_id`다.
단위의 PK로 비교하며 이름·기호·dimension을 추론하지 않는다. `original_unit`은 출처 문자열로
그대로 보존하고, 현재 단위 identity나 매핑 입력으로 사용하지 않는다.

`QualityControlService.check_unit(characteristic_value_id, rule_id, field_policy=policy)`는
명시한 활성 값과 규칙 하나를 검사하고 기존 불변 `QualityRecheckResult`를 반환한다.
활성 FLEX 사전의 INTEGER/REAL만 지원한다. TEXT/DATE/DATETIME은 configuration error다.
규칙은 `target_type=CHARACTERISTIC_VALUE`이고 해당 dictionary_id에 연결되어야 한다.
parameters_json은 NULL 또는 빈 객체만 허용한다. expected unit을 규칙에 중복 저장하지 않는다.
Disabled 규칙은 검사 수 0으로 기존 issue를 보존한다. 일반 QC API의 기존 계약은 유지하므로
Unit 규칙은 이 API로 호출하고, 일반 재검사는 `rule_ids`로 일반 규칙을 명시한다.

- `UNIT_MATCH`: expected/actual ID가 같으면 Finding 없음, 다르면 `UNIT_MISMATCH`.
  expected가 있고 actual이 NULL이면 `UNIT_MISSING`.
- `UNIT_CONVERSION_MISSING`: 두 ID가 다를 때 직접 등록된 actual→expected 활성 변환을
  확인한다. 없으면 같은 이름의 issue를 생성한다. 같으면 변환이 필요 없으므로 Finding 없음.
  actual이 NULL이면 방향을 구성할 수 없어 configuration error이며 UNIT_MISSING을 대신 생성하지 않는다.
- 명시적 Unit 규칙에는 expected metadata가 필수다. expected가 NULL이면 actual 유무에
  관계없이 configuration error다. 단위가 필요 없는 항목에 규칙을 임의 등록하지 않는다.
- 참조된 expected/actual 단위가 없거나 비활성이면 configuration error다. 자동 교체하지 않는다.
- Severity는 각 rule.default_severity를 그대로 사용한다. 운영 규칙 seed는 생성하지 않는다.

변환 조회는 기존 DictionaryRepository를 확장해 방향별 모든 활성 후보를 확인한다.
실제 UNIQUE는 `(from_unit_id, to_unit_id, formula_type)`이므로 서로 다른 식 유형의 중복은
가능하다. 활성 후보가 둘 이상이면 ambiguity configuration error다. 하나뿐이어도 현재
지원하는 LINEAR가 아니거나 factor/offset이 유한한 숫자가 아니면 configuration error다.
비활성 후보는 제외하여 후보가 없으면 conversion-missing으로 처리한다.
NOT NULL 제약은 factor/offset 누락을 막는다. factor/offset은 유효성만 확인하며 실행하지 않는다.
역방향 추론·중간 단위 chain 탐색·dimension 추론은 하지 않는다.
UNIT_MATCH만 실행하면 변환 조회나 conversion-missing issue 생성을 수행하지 않는다.
Phase 7C-1 Reference Comparison은 여전히 단위 불일치를 거부하며 자동 변환하지 않는다.

기존 QCFinding과 target provenance를 재사용하고 고정 message만 제공한다.
issue.original_value/compare_value는 NULL이며 raw 단위명·기호·원본값을 추가하지 않는다.
규칙 설정과 실행 당시 단위 ID는 분리한 canonical snapshot에 남긴다:

```json
{"format":"unit_qc_v1","rule_parameters":null,"execution":{"actual_unit_id":2,"expected_unit_id":1}}
```

동일 rule/value/단위 쌍과 snapshot이면 기존 issue를 유지한다. 같은 값의 actual 단위나 사전의
expected 단위가 외부의 명시적 변경으로 바뀌면 이전 pair와 다른 issue로 식별한다.
검사 범위는 해당 rule/value/출처/Unit 검사 종류다. 그 범위의 이전 pair 문제는 비활성화하고
현재 문제를 새 행으로 남긴다. QC 자체는 단위 metadata를 수정하지 않는다.
해소 후 재발은 새 행으로 기록하며 inactive 재활성화·DELETE·review 정보 덮어쓰기는 없다.
변환 규칙 등록 후 재검사는 conversion-missing을 해소하지만 별도 UNIT_MATCH issue는 유지한다.
다른 규칙·값·소하천·사전·Reference Comparison issue는 변경하지 않는다.

검증·판정·dedup·저장·비활성화·상태 집계는 하나의 BEGIN IMMEDIATE에서 수행한다.
실패하면 전체 rollback하고 내부 SQL/오류·원본값·단위명·경로·JSON은 오류 메시지에 노출하지 않는다.
현재 상태는 대상 소하천의 활성 issue 전체 집계이며 검사 수와 별개다.
Schema/migration/dependency 추가, 원본/단위/대표값/캐시 수정, Import 매핑 변경은 없다.
단위 pair ID snapshot은 전용 FK나 단위 정의 전체 snapshot이 아니며,
실제 보정·승인된 환산·통합 batch orchestration은 후속 범위다.


## Phase 7C-3 Statistical Outlier Candidate QC

`STATISTICAL_OUTLIER`는 특성정보의 통계적 확인 후보를 찾는다. 잘못된 값이나 자동 오류로
판정하지 않으며 값 삭제·비활성화·보정·대표값 변경·분석 대상 자동 제외를 수행하지 않는다.
계측 수위/유량의 오측 관리와 다른 업무다. 3σ나 계측자료 IQR 1.5를 특성정보 기본값으로
적용하지 않는다. 단변량 IQR만 지원하고 z-score·ML·시계열·지역별 그룹·다변량 분석은 없다.

`QualityControlService.check_statistical_outlier(target_value_id, rule_id,
population_value_ids=(...), field_policy=policy)`는 명시적인 모집단과 target 하나를 검사하고
기존 불변 QualityRecheckResult를 반환한다. 규칙은 `target_type=CHARACTERISTIC_VALUE`,
활성 FLEX INTEGER/REAL 사전항목에 연결한다. V1에서는 default_severity가 INFO인 규칙만
허용하고 WARNING/ERROR는 configuration error다. Disabled 규칙은 실행 수 0으로 기존 issue를
보존한다. 일반 QC와 같은 호출에 암묵적으로 섞지 않으며 일반 재검사는 rule_ids를 명시한다.

parameters_json에는 `method: "IQR"`와 유한한 0 이상의 숫자 `multiplier`가 필수다.
multiplier=0은 Q1/Q3 바깥을 후보로 보는 명시적 정책이다. 기본 multiplier는 없다.
선택적인 `minimum_sample_size`는 1 이상의 정수다. 생략 시 수학적 계산 가능 최소인 1개만
요구하며, 이는 연구적 표본 적정성 기준이 아니다. 한 개 표본의 Q1/Q3는 그 값이어서 후보가 없다.
unknown parameter·중복 키·bool·부적합 자료형·NaN/Infinity는 거부한다. 표본 수 부족은 오류다.

모집단 계약:

- 중복 없는 양의 value ID tuple을 호출자가 명시하고 target ID를 반드시 포함한다.
  빈 목록·중복 ID·target 누락은 오류이며 서비스가 자동 추가하거나 제외하지 않는다.
- 모든 값이 존재하고 활성 상태이며 target과 동일 dictionary_id 및 동일 unit_id여야 한다.
  target 단위는 NULL을 허용하지 않고 활성 단위여야 한다. 단위 혼합·자동 환산은 없다.
  사전의 expected unit과의 일치 여부는 별도 Unit QC 영역이다.
- typed numeric 하나와 유한한 값을 검증한다. 잘못된 행을 통계에서 조용히 제거하지 않는다.
- representative나 모든 historical/source 값을 자동 선택하지 않는다. 같은 숫자의 서로 다른
  행은 그대로 표본으로 인정한다. 같은 소하천의 복수 행도 호출자가 선택했다면 각각 반영하므로
  소하천별 가중치가 의도에 맞는지는 모집단을 선택하는 연구자가 확인해야 한다.

Percentile 알고리즘은 `linear_n_minus_one_v1`로 고정한다. 숫자를 정렬하고 p=1/4 또는 3/4에서
h=(n−1)×p, i=floor(h), f=h−i로 두어 x[i]+f×(x[i+1]−x[i])를 계산한다.
f=0이면 x[i]다. INTEGER는 정수, REAL은 저장값의 십진 표현을 정확한 유리수로 사용하여
보간·경계 연산의 반올림을 피한다. 원본 Excel 수치 복원이나 암묵적 epsilon은 제공하지 않는다.
Q1=25%, Q3=75%, IQR=Q3−Q1이고 경계는 Q1−multiplier×IQR 및 Q3+multiplier×IQR이다.
경계 바깥만 후보이며 같은 값은 정상범위다. IQR=0이면 경계는 Q1=Q3 그대로다.

기존 불변 QCFinding에 `STATISTICAL_OUTLIER_CANDIDATE`와 INFO를 기록한다.
고정 message와 target provenance만 사용하며 원본값·Q1/Q3·bounds·단위명은 message/repr/error나
issue.original_value/compare_value에 저장하지 않는다. 반환 status는 target 소하천 전체의
활성 issue 집계이므로 다른 ERROR가 있다면 이 검사 결과와 별개로 ERROR일 수 있다.

`statistical_outlier_v1` canonical snapshot은 원래 rule_parameters와 execution을 분리한다.
execution에는 정렬한 population_value_ids, sample_size, dictionary_id, unit_id,
percentile_algorithm 및 population_identity를 보존한다. identity는 정렬된 ID·사전·단위의
canonical JSON에 대한 SHA-256이다. 숫자 자체는 hash 입력이나 snapshot에 포함하지 않는다.
ID 입력 순서는 identity에 영향을 주지 않으며 행의 중복 숫자는 유지한다.
모집단 구성은 복원할 수 있지만, 이후 같은 ID의 값이 바뀌면 당시 수치를 이 snapshot만으로
복원하지 못한다. ID는 전용 population FK가 아니며 snapshot 크기는 표본 수에 비례한다.

기존 reconciliation에 population identity 범위를 추가했다. 같은 rule/target/출처/모집단의
동일 후보는 ID·검토 이력을 유지하고 정상범위가 되면 issue만 비활성화한다. 재발은 새 행이며
재활성화·DELETE는 없다. 모집단 A/B는 별개 사건으로 보존하고 다른 모집단 issue를 해소하지 않는다.
같은 모집단에서 multiplier·최소 표본 정책·규칙 version이 바뀌면 이전 snapshot은 보존하면서
해당 범위의 이전 후보를 비활성화하고 현재 후보가 있으면 새 행을 만든다.
다른 QC 종류·target·모집단은 변경하지 않는다.

단일 BEGIN IMMEDIATE 안에서 모집단을 조회·평가하고 issue 저장·비활성화·상태 집계를 수행한다.
실패하면 모두 rollback하며 Repository 내부 commit은 없다. Schema/migration/dependency,
운영 규칙 seed, 실제 연구자료·운영 DB 접근은 추가하지 않았다.
Phase 7 전체 완료 판정은 이 개별 기능의 테스트 통과와 별도로 로드맵의 V1 규칙 선정 및
전체 Gate 검토가 필요하다. 이번 작업에서 Phase 8 구현은 시작하지 않는다.


## Phase 7 Final QC Gate / Phase 8 연계 계약

QC engine foundation과 운영 연구 rule set은 구분한다. 현재 7종 규칙의 실행·issue 생성·
재검사 기반을 제공하지만 실제 운영 rule set과 민감 항목 정책은 별도 검토·등록이 필요하다.
Reference 후보인 하상경사·소하천 연장·유역면적·계획홍수량은 실제 seed가 아니다.

Phase 8에서 새 current-use를 선택할 때는 **선택 대상 characteristic_value_id의 활성 issue**를
기준으로 판단해야 한다. active ERROR는 차단하고, WARNING 또는 INFO는 사용자 명시적 확인 후
선택 가능하다. 활성 issue가 없으면 QC 관점에서는 선택 가능하지만 값의 활성 상태 등 다른
Phase 8 업무 검증은 별도로 수행한다. review_status 변경으로 ERROR 차단을 해제하지 않는다.
통계 후보 INFO를 영구 선택 차단으로 해석하거나 기준자료/단위 불일치를 자동 보정하지 않는다.

현재 `QualityControlRepository.list_active_issues(stream_code)`는 value ID와 severity를
제공하므로 대상 ID로 필터링하여 이 판단이 가능하다. 소하천 aggregate는 다른 값의 issue도
포함하므로 선택 차단에 그대로 사용하지 않는다. Phase 8에서는 필요 시 값별 active severity
조회 API를 추가하고, 검사·사용자 확인·선택 변경·이력·캐시 갱신의 transaction 계약을 구현한다.
현재 Gate는 current-use 변경 기능을 추가하지 않는다. NORMAL은 검사 완료 보증도 아니다.

Generic 검사와 Reference/Unit/Statistical 검사는 명시적 API가 분리되어 있다.
일반 재검사는 rule_ids를 명시하여 호출한다. 통합 자동 batch 실행이나 규칙 관리 GUI는
제공하지 않는다. snapshot의 reference/population/단위 ID는 전용 FK가 아니며 당시 연구값을
복원하는 저장소가 아니다. 이 제한과 운영 rule 등록은 후속 검토 항목으로 유지한다.


## Phase 8A Current-use Selection Foundation

`CurrentValueService.select_current_value(characteristic_value_id, actor_user_id,
confirm_review_required=False, reason=None)`는 명시한 값을 현재 사용값으로 선택한다.
별도 request 모델 없이 ID와 keyword option을 받는다. 활성 사용자·값·소하천·사전·카테고리를
검증하며 deprecated 사전과 CORE는 거부한다. 기존 characteristic_value의 FLEX 자료형에
적용하고 unit/reference 차이를 자체 보정하거나 별도 선택 기준으로 추정하지 않는다.

정상 current-use는 같은 stream_code/dictionary_id에 활성 is_representative=1인 값이 하나이고
stream_characteristic이 바로 그 값을 참조하는 상태다. 실제 partial UNIQUE 조건은
is_representative=1 AND is_active=1이다. 캐시의 같은 stream/dictionary·활성·대표 flag를
선택 전후에 검증한다. flag-only/cache-only/불일치/비활성 캐시 등의 기존 비정상 상태는
CurrentValueInvariantError로 거부하며 자동 수리하지 않는다. inactive 과거 대표 flag는
활성 current-use에 포함하지 않고 그대로 보존한다. 캐시와 활성 대표가 모두 없으면 첫 선택이다.

QC Gate는 transaction 안에서 **대상 value ID의 활성 issue**를 재조회한다.
활성 ERROR는 confirmation=True여도 차단한다. WARNING/INFO만 있으면 정확한 bool True 확인이
필요하고, 활성 issue가 없으면 확인 없이 가능하다. NULL value ID issue·다른 값/소하천의
ERROR·inactive issue는 target Gate에 포함하지 않는다. quality_status 문자열이나 UI의 사전
조회 결과, 소하천 전체 aggregate를 선택 차단의 근거로 사용하지 않는다.
Reference WARNING·Unit WARNING/INFO·Statistical INFO도 동일 정책이다.
확인은 QC 해소·검토 상태 변경·자동 단위환산·reference 대체를 의미하지 않는다.

처리는 단일 BEGIN IMMEDIATE에서 사용자/대상 검증 → 값별 QC → 기존 current 검증 →
이전 flag 해제 → 새 flag 설정 → cache upsert → record_history → 최종 invariant 확인 순으로
수행한다. 예외나 commit 실패면 모두 rollback한다. 동시에 다른 값을 선택해도 직렬 처리하여
최종 flag/cache는 하나로 일치한다. 나중에 직렬 처리된 명시적 선택이 최종 current가 된다.
Repository는 SQL만 담당하고 정책·확인·invariant는 Service가 담당한다.

정상 current를 재선택하면 changed=False, history_id=None으로 반환하고 UPDATE·cache rewrite·
이력 생성을 하지 않는다. no-op 전에도 actor·target·QC는 재검증한다. 따라서 이미 current여도
새 활성 ERROR가 있으면 재선택 요청은 거부하지만 기존 current를 자동 해제하지는 않는다.

불변 CurrentValueSelectionResult는 changed, stream_code(repr 제외), dictionary_id,
previous_value_id, current_value_id, qc_status_before_selection, confirmation_required,
confirmation_used, history_id, completed_at(UTC)을 제공한다. 확인이 불필요했다면 사용자가
True를 전달해도 confirmation_used=False다. 연구값·경로·사유 원문을 result에 넣지 않는다.

record_history.change_type은 CURRENT_VALUE_CHANGE, table_name은 characteristic_value,
column_name은 is_representative다. record_key의 canonical JSON은 stream_code/dictionary_id,
old_value는 이전 value ID(NULL 허용), new_value는 새 ID와 QC 상태·확인 필요/사용 여부다.
actor_user_id와 changed_at을 기록하고 changed_by 사용자명 복제·raw 연구값 복제는 하지 않는다.
선택 사유는 nullable 컬럼에 맞춰 optional이며 이번 API는 민감 자유문구 저장을 피하기 위해
RESEARCHER_SELECTION / SOURCE_REVIEW / QC_REVIEW_CONFIRMED 고정 코드만 허용한다.
자유문구 사유 UX/보호 정책은 후속 검토 사항이다.

old/new 연구값에서 변경하는 것은 is_representative뿐이다. value_*·unit·original_value·
original_unit·provenance·is_active·기존 updated_at은 그대로 보존한다. 선택 시각은 cache와
history에 기록한다. 새 characteristic_value, correction, 자동 Import 선택, QC issue 변경,
자동 reference 교체·단위환산은 없다. Phase 8B correction과 구분하며 schema/migration/dependency
추가는 없다. 전달하는 actor ID의 활성 여부는 검증하지만 인증 세션 연결은 호출 계층 책임이다.

## Phase 8B USER_CORRECTION Value Creation

`CorrectionService(connection).create_correction(CorrectionRequest(...))`는 기존 값을
덮어쓰지 않고 새 characteristic_value와 보정 이력을 하나의 BEGIN IMMEDIATE transaction으로
생성한다. request는 source_value_id, actor_user_id, corrected_value, reason_code와 optional
corrected_unit_id를 받는 불변 모델이다. 결과 CorrectionCreationResult는 correction_value_id,
source_value_id, stream_code(repr 제외), dictionary_id, actor_user_id, history_id, created_at을
반환한다. request의 연구값은 repr에 표시하지 않는다.

source·actor·소하천·사전·카테고리가 존재하고 활성이어야 한다. deprecated 사전와 CORE는
거부한다. 새 값은 source의 stream_code/dictionary_id를 그대로 사용하며 다른 항목이나 하천으로
이동하는 API는 없다. active 보정값을 다음 보정의 source로 사용할 수 있다. 같은 source와 같은
입력도 별도 판단 이벤트로 INSERT하며 자동 deduplication/idempotency는 제공하지 않는다.
결과가 불확실한 요청을 무조건 재시도하지 말고 이력을 확인해야 한다.

자료형은 사전의 INTEGER/REAL/TEXT/DATE/DATETIME을 따른다. INTEGER는 bool을 제외한 signed
64-bit Python int만 허용하고 float/문자열을 정수로 바꾸지 않는다. REAL은 기존 normalize_cell
계약의 유한 int/float/숫자 문자열을 허용하며 NaN/Infinity/overflow/underflow를 거부한다.
DATE/DATETIME도 기존 parser를 재사용하여 유효한 ISO 문자열 또는 date/datetime을 저장하며
timezone-naive 값에 시간대를 붙이거나 UTC로 추정 변환하지 않는다. parser adapter의 임시 셀
좌표는 provenance로 저장하지 않는다. TEXT는 문자열 그대로 보존하고 trim/case 변환이나
공백을 결측으로 바꾸지 않는다. 빈 문자열/공백 문자열도 보존한다. 사전에 길이 제한 필드는
없으며 임의 제한을 만들지 않는다. None 보정은 nullable 사전여도 exactly-one typed CHECK를
만족하지 못하므로 거부한다. 이 API는 결측 삭제/비활성화 API가 아니다.

corrected_unit_id 생략(UnitInheritance.SOURCE)은 source.unit_id를 상속한다. 명시적 값은
dictionary.unit_id와 정확히 같아야 하며 None은 사전 기준 단위도 None일 때만 허용한다.
실제로 저장할 단위가 있으면 존재·활성을 검증한다. 단위 변경에도 corrected_value는 필수이며
사용자가 입력한 새 값과 단위를 저장할 뿐 자동 환산하지 않는다. 상속 단위가 기준 단위와
다른 것은 Unit QC에서 검토할 수 있도록 보존하며 QC 통과로 간주하지 않는다.
기준 단위 외 다른 단위를 명시하는 기능과 자동 변환은 제공하지 않는다.

새 행은 source_type=USER_CORRECTION, is_active=1, is_representative=0,
quality_status=UNREVIEWED다. original_value/original_unit/source_reference와
import_id/import_sheet_id/mapping_id/source_row는 모두 NULL이며 원본 Excel 출처를 복제하지
않는다. reference_year는 원래 값의 자료 기준 연도를 상속하며 현재 연도로 채우거나 별도
변경하지 않는다. created_at/updated_at은 공통 UTC helper의 같은 시각이다.

record_history.change_type=CORRECTION은 DATABASE_DESIGN의 기존 업무 용어를 따른다.
record_key는 stream_code/dictionary_id JSON, old_value는 직접 parent의 source_value_id JSON,
new_value는 correction_value_id와 event=USER_CORRECTION_CREATE JSON이다. actor_user_id,
reason, changed_at을 기록한다. reason_code는 Phase 8A의 RESEARCHER_SELECTION /
SOURCE_REVIEW / QC_REVIEW_CONFIRMED 중 하나를 필수로 받는다. 이 코드는 QC 완료 증명이 아니다.
자유문구 note, 사용자명 snapshot, raw 연구값/원본값/경로 복제는 없다. parent ID는 generic
history의 JSON에 있으므로 전용 FK가 아닌 Service 계약이다. source_reference에 별도 중복
연결을 만들지 않는다. source와 새 행·history를 저장 후 재조회 검증하며 history 실패,
최종 검증 실패, commit 실패는 새 값과 이력 모두 rollback한다. 동시 보정은 직렬 처리되고
각각 별도 행으로 보존된다. Repository는 SQL, Service는 검증·정책·transaction을 담당한다.

**보정 생성은 QC pass도 현재 사용값 선택도 아니다.** Phase 8B에서는 select_as_current와
즉시 선택 옵션을 제공하지 않는다. 필수 QC 완료를 신뢰성 있게 증명하는 영속 실행 기록이
현재 없기 때문이다. UNREVIEWED는 신규 행의 초기 상태일 뿐 QC 실행 이력이나 Phase 7의
active issue aggregate와 같지 않다. issue가 없다는 사실만으로 검사 완료를 증명하지 못한다.

권장 순서는 **보정 생성 → 필요한 QC API 명시 실행 → 연구자 검토 → Phase 8A 현재값 선택**이다.
자동 QC orchestration은 이번 범위에 포함하지 않는다. Phase 8A는 별도 transaction에서
대상 active ERROR 차단/WARNING·INFO 확인을 수행하지만 모든 필수 QC 실행 여부까지
강제하지는 않는다. 후속 호출 계층에서 검사 실행 안내와 검토 절차를 연결해야 한다.
별도 선택 실패 시 이미 생성한 보정값은 남고 기존 current-use는 유지된다. 생성+선택을
하나의 요청으로 가장하지 않으며 중첩 transaction도 만들지 않는다.

기존 characteristic_value의 값·단위·provenance·대표/활성 flag·updated_at, 현재값 캐시,
small_stream, 사전, 단위 사전, QC issue는 변경하지 않는다. 새 dependency/schema/migration,
UI, 실제 연구자료/운영 DB 접근, 자동 수정은 없다. 인증된 actor ID 전달은 호출 계층 책임이다.

## Phase 8C Current-use Maintenance

`CurrentValueMaintenanceService(connection)`은 `deactivate_value(value_id, actor_user_id,
confirm_current_use_loss=False, reason_code=...)`, `restore_value(value_id, actor_user_id,
reason_code=...)`, `rebuild_current_value_cache(actor_user_id, stream_code=None,
dictionary_id=None)`를 제공한다. 값 변경은 활성 actor와 Phase 8의 구조화 reason code가 필요하다.
캐시 재구축도 명시적 활성 actor 호출로 한정한다. 모든 변경은 BEGIN IMMEDIATE에서 이력과
최종 상태 검증을 함께 처리하고 실패 시 rollback한다. 이미 목표 상태인 요청은 no-op이다.

비대표값 비활성화는 `is_active`만 0으로 바꾸며 값·Import 출처·QC issue를 보존한다.
현재 사용값 비활성화에는 정확한 bool `confirm_current_use_loss=True`가 필요하다. 이때
대표 flag 해제, 캐시 행 제거, 값 비활성화와 DEACTIVATE 이력을 함께 저장하고 대체 값을
자동 선택하지 않는다. 복원은 비대표 비활성값의 `is_active`만 1로 바꾸고 RESTORE 이력을
남긴다. 비활성 과거 대표 flag=1인 값은 자동 현재값 복귀를 막기 위해 복원 요청을 거부한다.
복원은 QC 완료나 현재값 선택을 의미하지 않는다.

캐시는 활성 `is_representative=1` 값만을 기준으로 전체 또는 정확한 stream/dictionary pair를
재구축한다. 대표값이 없으면 캐시를 제거하고, 누락·잘못된 포인터는 캐시만 바로잡는다.
비활성 과거 대표 flag는 보존하며 선택 판단이나 값 변경을 하지 않는다. 정상 DB의 부분 UNIQUE가
활성 대표 중복을 막고, 재구축도 복수 대표를 발견하면 오류로 중단한다. 실제 캐시 포인터가
바뀐 pair에만 기술 이력 CACHE_REBUILD를 남긴다. 무변경 pair는 캐시 시각·이력을 갱신하지 않는다.
DEACTIVATE/RESTORE는 값 ID와 상태 전후, CACHE_REBUILD는 pair와 포인터 ID 전후만 이력에
기록하며 원시 연구값이나 경로를 복제하지 않는다.

## Phase 8 Final Gate

`tests/integration/test_phase_8_final_gate.py`는 합성 임시 DB에서 Import 출처 값 → 현재값
선택 → 보정 chain → 명시적 QC·재검사 → 현재값 변경 → 비활성화·복원 → 캐시 재구축과
이력·출처 보존을 검증한다. 활성 ERROR 차단, WARNING/INFO 명시적 확인, 비활성/무관 issue,
업무별 rollback 및 대표 flag·캐시 일치를 확인했다. Phase 8 전체 Gate를 통과해 Phase 9
진입이 가능하다. QC issue가 없다는 사실만으로 필수 검사 완료를 증명하지 않는 기존 계약은 유지한다.

## Phase 9A Read/Query Backend

`StreamReadService(connection).list_streams(StreamListRequest(...))`는 page(1부터),
page_size(1~100), 관리코드 정확/접두 또는 하천명 부분 검색, 시·도(2자리)·시군구(3자리)·
읍면동(3자리) 코드 필터와 허용 정렬을 받는다. 기본은 활성 하천의 관리코드 오름차순이다.
다른 정렬에는 관리코드를 tie-breaker로 사용한다. COUNT와 LIMIT/OFFSET은 DB에서 수행하고
한 페이지의 QC는 한 번에 집계한다. 100행 제한은 GUI의 일회 적재량과 QC IN batch의 기술적
상한이다. 결과는 total_count/page/page_size/total_pages와 불변 표시 행을 반환한다.

`get_stream_detail(stream_code, display_policy=...)`는 기본정보와 명시적으로 허용한 사전 항목의
현재 사용값 요약만 반환한다. `CharacteristicDisplayPolicy`의 기본 허용 목록은 비어 있으며,
항목 ID는 최대 200개까지 명시한다. 이 상한은 SQLite bind 수와 상세 화면 전송량을 제한한다.
운영 항목 allowlist를 임의 seed하지 않는다. 등록 파일명·시트명은 별도 표시 옵션이 True일
때만 반환하며 원본 경로·셀·header·QC message·계정정보는 표시 모델에 넣지 않는다.

현재값 상태는 활성 대표 flag와 cache·값 키가 일치하는 VALID_CURRENT, 둘 다 없는 UNASSIGNED,
불일치한 INCONSISTENT로 구분한다. 비활성 과거 대표는 현재값이 아니다. QC 표시는 활성 ERROR의
ERROR, 활성 WARNING/INFO의 NEEDS_REVIEW, 활성 issue가 없는 ACTIVE_ISSUES_NONE으로 구분하며
마지막 상태는 검사 완료를 증명하지 않는다. 조회는 SQLite read snapshot에서 SELECT만 수행하고
불일치를 자동 수리하지 않는다. Phase 9B에서 PySide6 앱 shell·로그인·목록 GUI를 연결했다.
9C 상세 GUI, 9D-2 Home GUI, 9D-3 작업이력 GUI와 9D-4 마이페이지를 제공하며 Phase 9 Final Gate를 통과했다.
9D-1 read backend는 활성 소하천 수, 활성 QC 오류/확인 필요 소하천 수, 연구 사전 상태,
bounded 최근 작업이력과 안전한 공개 사용자 profile을 DB SELECT projection으로 제공한다.
Phase 9D-2 Home GUI는 이 projection만 비동기로 조회한다. Phase 9D-3 작업이력 GUI는
지원되는 다섯 작업 유형의
안전한 공개 projection만 표시하며 원시 이력 값과 내부 ID는 표시하지 않는다.
Phase 9D-4 마이페이지는 공개 profile과 현재 사용자 최근 작업만 비동기로 조회하며 계정 수정이나
사용자 관리 기능을 제공하지 않는다. `tests/integration/test_phase_9_final_gate.py`는 Phase 9의
주요 화면 흐름, pagination·필터·resize, 안전 경계와 조회 전후 DB 불변성을 합성 데이터로 검증한다.

## Phase 9B 목록 GUI

기본 실행은 기존 migration runner로 DB를 준비하고 `AuthService`로 최초 사용자 등록/로그인을
진행한다. 인증 공개 사용자 정보만 GUI session에 보관하고 로그아웃 시 제거한다. 앱 shell은
09 소하천 조회만 실제 연결하며 다른 메뉴는 미구현 상태를 명시한다.

목록은 `StreamReadService`의 50행 DB pagination, 검색, 활성 소하천 기반 지역 선택지,
허용된 서버 정렬을 사용한다. 목록 상태는 오류/확인 필요/활성 문제 없음으로 표시하며 마지막은
QC 완료를 뜻하지 않는다. Qt worker마다 자체 SQLite 연결을 만들고 닫으며 요청 번호가 지난
결과는 화면에 반영하지 않는다. 조회 화면의 SQL·Repository 접근과 특성값 변경 기능은 없다.

## Phase 9C-0 Research Dictionary Bootstrap

`resources/research_dictionary_v1.json`은 24개 상위 특성 개념의 실제 저장 leaf와 기점·종점
계획정보를 분리해 정의한다. 토지이용 32개 원본 분류를 합치지 않으며 전체 70개 leaf,
5개 category, Excel에서 확인된 6개 unit, Phase 3의 ` | ` flattening과 호환되는 70개
qualified alias를 포함한다. 대표6·전국분석9 표시는 연구 우선순위 metadata이고
`analyzable`과 별개다.

`ResearchDictionaryBootstrapService.bootstrap()`은 manifest의 canonical JSON SHA-256을
`dictionary_version.description`에 기록한다. 기존 동일 정의는 재사용하고 internal name의
의미·자료형·단위·category 또는 alias 대상이 다르면 덮어쓰지 않고 전체 transaction을
rollback한다. 단위 차원과 미확정 단위는 추정하지 않고, unit conversion·QC rule·특성값·
현재 사용값을 생성하거나 변경하지 않는다.

`approved_display_policy()`는 승인된 internal name을 현재 활성·미폐기 사전 ID로 해석해
Phase 9A의 deny-by-default `CharacteristicDisplayPolicy`로 반환한다. bootstrap 전에는 빈
허용 목록이다. 서비스 Key, IP, CCTV/RTSP, 연락처와 인증정보는 manifest에 포함하지 않는다.
Phase 9C-0 자체는 상세 GUI를 만들지 않았고, 이어진 Phase 9C에서 이를 연결했다.

Phase 9C 상세 화면은 연구 사전이 초기화된 DB에서 승인 internal name을 활성 사전 ID로
batch 해석한다. 사전 미초기화, 현재값 미지정, 캐시 불일치, 활성 문제 없음, 조회 실패를
서로 다른 상태로 표시한다. 원본값·절대경로·raw QC message·내부 ID는 표시하지 않으며
화면에서 값·QC·사전·current-use를 변경할 수 없다. 특성·QC·출처·값 이력은 항목별 SQL이
아닌 bounded batch 조회를 사용한다.

## Phase 9C UI smoke DB

실제 로컬 DB와 분리된 합성 화면 검수 DB는 개발 전용 `tools/ui_smoke.py`로 만든다. 이 도구는
저장소의 `build` 폴더 바로 아래에 있는 `*ui_smoke*.db` 경로만 허용하며 기존 파일과 기본
로컬 DB를 덮어쓰지 않는다. 공식 `research-dictionary-v1`, 합성 소하천 5개, 화면 확인용
특성값·QC·출처를 만들고 실제 연구 Excel이나 기존 계정을 복사하지 않는다.

```powershell
.\.venv\Scripts\python.exe tools\ui_smoke.py create --db build\ui_smoke.db
.\.venv\Scripts\python.exe tools\ui_smoke.py run --db build\ui_smoke.db
```

첫 실행에서는 기존 최초 사용자 등록 화면에서 smoke DB 전용 계정을 만든다. 등록 직후 기존
Phase 8 Service로 합성 current-use와 보정 이력을 완성하며, 이후 같은 `run` 명령으로 로그인한다.
생성된 `build/ui_smoke.db`는 Git에서 제외되는 일회성 산출물이다.

## Phase 10A backend 계약

Phase 10A는 GUI 없이 Import/QC 화면에 필요한 읽기·검토 경계를 준비한다.
`Phase10ReadService`는 Import 이력과 동일 SHA-256 이력을 DB COUNT/LIMIT/OFFSET으로
조회하며 파일명만 반환한다. 기존 성공 Import의 동일 hash는 재Import 경고와 명시적
확인 대상이며 영구 금지는 아니다. 같은 batch code 중복 차단은 유지한다.
`Phase10ImportPolicyService`는 현재 연구 사전에서 승인된 항목과 안전한 소하천 기본정보만
Preview/Import 정책에 포함한다. 불명확한 단위는 `NEEDS_REVIEW`이며 자동 추정·변환하지
않는다. GUI는 내부 Preview 객체 대신 `to_display()` 결과만 사용해야 한다.

`Phase10ReadService`의 QC 목록·상세는 활성 issue의 안전한 필드만 반환하며 raw QC
message, note, 내부 ID, 경로를 화면에 표시하지 않는다. `QCReviewService`는 활성 작업자가
활성 issue에 대해 `UNREVIEWED → IN_REVIEW → CONFIRMED` 전이만 요청할 수 있게 한다.
동일 상태는 no-op이고 note/result는 선택 사항이며 각각 500/200자로 제한한다. 검토와
`QC_REVIEW` 감사이력은 한 transaction으로 기록한다. Home·작업이력·마이페이지의 공개
이력은 여섯 번째 event `QC_REVIEW`를 안전한 소하천·특성항목 대상으로 표시한다.

Phase 10A에서는 GUI를 구현하지 않았다. 한 실행의 Import 대상은 한 sheet이며 DB 저장 전까지만
취소한다. 저장 시작 후 worker/thread/connection을 강제 종료하지 않고 Service의 결과를
기다린다. 단계 기반 진행 상태를 사용하고 임의 퍼센트는 표시하지 않는다. Import 성공 후
workspace는 자동 삭제하지 않는다. DB 관리 cache rebuild는 기존 명시적 Service를 재사용하며
Backup/Restore는 Phase 14 범위다.

## Phase 10B Excel 작업 시작 화면

Sidebar의 **Excel 가져오기**는 `.xlsx` 선택 후 별도 worker에서 SHA-256과 workbook 구조를
확인한다. 연구 DB의 동일 hash 이력은 파일명 기반 경고로만 표시한다. 한 번에 한 worksheet를
선택하고 1-based 헤더 시작·종료행과 데이터 시작행을 지정한 뒤 **구조 확인**으로 조합된
헤더만 본다. 데이터 샘플·원본 절대경로는 화면에 표시하지 않는다. 숨김 worksheet는 선택할
수 있고 chartsheet와 빈 sheet는 제외한다. 확인한 범위는 연구 DB 밖의 사용자별 Workspace
draft로 명시적으로 저장·재개하며, 재개 시 원본 hash를 다시 검증한다. 컬럼 매핑·Preview
화면은 Phase 10C, 실제 DB Import 실행은 Phase 10D 범위다.

## Phase 10C 컬럼 매핑·Import Preview

저장된 10B 파일 구조에서 **다음: 컬럼 매핑**으로 이동한다. 원본 파일·hash·선택 sheet·
헤더와 연구 사전 상태를 worker에서 다시 확인한다. 기본은 공통 별칭만 사용하고, 사용자가
2024 전국 연구자료 범위를 명시적으로 선택한 경우에만 `NATIONAL_2024` 별칭의 정확한
일치 결과를 자동 제안한다. 허용된 활성 사전 항목을 수동 선택하거나 원본 열을 명시적으로
제외할 수 있다. 매핑 변경은 사용자별 Workspace에 저장하고 이전 Preview를 무효화한다.
민감 열은 값·헤더 metadata를 Preview/Workspace에 옮기지 않고 제외한다.

관리코드 검증과 Preview는 기존 Service를 사용하며 모든 원본 행을 worker에서 판정한다.
화면에는 관리코드·상태·안전한 사유만 최대 50행 표시한다. 원본 단위는 추정하지 않고
확인 필요로 안내한다. 연구 사전 미초기화·불일치와 원본 변경은 진행을 차단한다.
연구 사전 bootstrap은 별도 `import-core-dictionary-v1` 정의의 관리코드·네 구성요소·소하천명
6개도 같은 transaction에서 준비한다. 이 항목은 TEXT·CORE·비분석용이며 연구 leaf 70개,
research fingerprint와 상세 표시 allowlist에는 포함하지 않는다. core와 연구항목은 기존
ColumnMappingService에서 함께 매핑되지만 Preparation은 core를 `small_stream` 식별·기본정보로
분리하고 `characteristic_value` 후보로 만들지 않는다. **다음: Import 실행**은 Phase 10D까지
비활성이다. 10C Mapping/Preview는 bootstrap 이후 연구 DB를 변경하지 않고 Workspace만 저장한다.
기존 연구 사전 DB도 동일한 명시적 `ResearchDictionaryBootstrapService.bootstrap()`을 다시
실행하면 정의가 같은 연구항목은 재사용되고 누락된 core prerequisite만 원자적으로 추가된다.
이전에 저장한 미매핑 Workspace는 조용히 바꾸지 않으며 사용자가 **자동 매핑 다시 적용**을
실행해야 한다. 기존 stream의 다른 원본 하천명은 식별키로 쓰거나 DB master를 변경하지 않는다.
