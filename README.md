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
로그인 GUI·Excel 자동매핑/DB Import·QC 실행·업무 화면·분석은 아직 구현하지 않았다.

## 환경과 의존성

- Python **3.12.x**, Windows를 기본 대상으로 한다.
- 표준 `venv` + `pip`, `pyproject.toml` + setuptools의 `src` 패키지 구조를 사용한다.
  별도 패키지 관리자 없이 Python 기본 도구로 설치·검증하기 위한 선택이다.
- 실행 의존성은 Python 표준 라이브러리, 비밀번호용 argon2-cffi와 Excel 읽기용 openpyxl이다.
- 개발 도구는 pytest(테스트), ruff(lint·format)다. mypy는 도입하지 않았다.
- 향후 PySide6, pandas, matplotlib는 실제 사용하는 Phase에서 추가한다.
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
