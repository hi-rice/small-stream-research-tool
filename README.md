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
로그인 GUI·DB Import·QC 실행·업무 화면·분석은 아직 구현하지 않았다.

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

실제 Excel Import orchestration A→B→C는 Phase 6B-2, recovery는 Phase 6C에 남겨둔다.
source_file 참조 확인은 설계에 있지만 등록을 A에 포함할지 앞 단계에 둘지는 명시되지 않았다.
이 배치와 T1 recovery/idempotency, settings snapshot, 매핑 상태 표현, 민감 필드·단위 확인 계약은
실제 실행 Service 구현 전에 확정한다. 새 schema/migration/의존성은 없다.

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
