# V1 개발 로드맵

이 문서는 small-stream-research-tool V1의 단계별 목표·산출물·검증 기준을 정의한다. 현재는 설계 단계이며 아래 모듈·파일·테스트는 모두 앞으로 만들 예정인 항목이다. 현재 구현되거나 설치되었다고 가정하지 않는다.

원본 Excel → 구조 탐색 → 데이터 사전 기반 표준화 → 소하천 관리코드 기준 연결 → 품질검사 → 연구 DB 구축 → 조회/분석 → 표·그래프/Excel Export를 수행하는 Windows 로컬·오프라인 연구지원 프로그램을 목표로 한다.

## 기본 개발 원칙

- AGENTS.md, PROJECT_OVERVIEW.md, ARCHITECTURE.md, DATABASE_DESIGN.md, DATA_RULES.md, QC_RULES.md를 기준으로 한다.
- 예정 기술은 Python 3.12, SQLite, PySide6, pandas, openpyxl, matplotlib, pytest, PyInstaller다. 실제 구성과 실행 명령은 Phase 0에서 확인한다.
- Windows 우선, offline-first를 적용한다. 기본 기능은 인터넷 없이 동작해야 한다.
- UI → Service → Repository → Database를 따른다. UI는 SQL이나 Repository를 직접 호출하지 않는다.
- DB와 데이터 처리 계층을 먼저 검증하고 Phase 9부터 본격적인 GUI를 연결한다.
- 정확성과 provenance를 개발 속도보다 우선한다. 원본 보존·민감정보 제외·자동수정 금지 원칙을 지킨다.
- V1은 19개 테이블을 유지한다. raw/staging/import_error/별도 QC history/backup_history 테이블을 임의로 추가하지 않는다.
- 이전 Phase의 테스트와 Gate 통과 후 다음 Phase로 진행한다. 이 문서는 전체 구현·commit 실행 허가가 아니다.
- 예상 모듈명은 ARCHITECTURE.md의 src/small_stream_research_tool 아래 책임 영역을 설명하며 실제 파일명·클래스명을 고정하지 않는다.

## Phase 번호와 UI 의존성

기존 Phase 0~16 번호를 유지하고 Phase 1 DB/schema와 Phase 2 사전 사이에 **Phase 1A 사용자/인증 기반**을 삽입한다. 총 18개 단계이며 V1 종료는 Phase 16이다. AGENTS.md도 같은 순서를 사용한다. UI부터 구현하지 않는다.

설계 최종 검증 → 기반 → DB/schema → 사용자/인증 → 사전 → Excel 해석 → 관리코드 → 매핑/Import → QC → 보정/history → UI → 분석 → Export → 백업 → 패키징 순서다.

## 공통 데이터 계약

- stream_code와 구성요소는 TEXT이며 선행 0을 보존한다. 이름을 JOIN KEY로 사용하지 않는다.
- characteristic_value는 typed value 정확히 하나만 NON-NULL이다. 결측만 있는 행은 만들지 않고 필수값 결측은 validation/QC로 처리한다.
- mapping_id와 source_row로 원본 행·열을 추적하고 Service에서 mapping·sheet·import 일치를 검증한다. Excel 위치는 1-based다.
- UNMAPPED는 메타데이터만 보관하고 원본을 재선택·참조하여 재Import한다. 모든 셀 값을 복제하지 않는다.
- 시스템 시각은 UTC ISO 8601 TEXT다. 원본 timezone은 추정하지 않는다. DATE/DATETIME은 value_date TEXT와 사전 자료형으로 구분한다.
- Import는 RUNNING 별도 commit → 실제 데이터 transaction → SUCCESS/FAILED 별도 갱신이다. settings_json은 실행 설정 snapshot, 상세 mapping은 import_column_mapping을 기준으로 한다.
- QC rule_id, rule_version_snapshot, rule_parameters_snapshot_json을 보존한다. severity와 review_status를 구분하고 과거 issue 및 중요 변경이력을 유지한다.
- 대표값 최대 하나, 보정값 별도 생성, record_history와 캐시 rebuild를 지킨다. 대표값·행 이동·이상치 삭제를 자동 처리하지 않는다.

## Phase 0. 프로젝트 기반 구성

### 목표

실제 Python 프로그램 개발을 시작할 수 있는 안정적인 프로젝트 골격을 만든다.

### 필요한 이유

실행과 테스트의 공통 기반이 있어야 이후 오류가 환경 문제인지 업무 로직 문제인지 구분할 수 있다.

### 주요 구현 내용

구현 대상:  

- Python package 구조
- pyproject.toml
- dependency 관리
- src layout
- tests 구조
- config 구조
- logging 기본 구조
- application entry point
- pytest 설정
- .gitignore
- 기본 README 정리
- 개발/실행 명령 정리

예상 구조의 방향:  

src/  
  small_stream_research_tool/  

tests/  

docs/  

단,  
ARCHITECTURE.md의 구조를 우선한다.  

### 예상 모듈

src/small_stream_research_tool의 app·config·utils, tests, pyproject.toml, .gitignore, README.md. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

Python 3.12 package import, entry point 실행, pytest 최소 smoke test. 로그에 민감정보가 없는지 확인한다.

### 완료 기준

- Python 3.12 환경에서 package import 성공
- pytest 실행 성공
- 최소 smoke test 통과
- application entry point 실행 가능
- 아직 실제 GUI/DB 기능은 만들지 않음

### 다음 단계 진입 조건

설계 감사의 판정과 사용자 요청 범위를 확인한 뒤 착수한다. 초기 commit은 별도 허가된 작업에서 수행한다. C1/U1/Q1과 기본 DDL 정책은 확정되었으며 기반 테스트와 Gate를 통과하면 요청 범위에서 Phase 1로 진행할 수 있다. 공통 Phase Gate도 만족해야 한다.

## Phase 1. SQLite Database Foundation

### 목표

V1의 19개 테이블을 안정적으로 생성하고 schema version을 관리할 수 있게 한다.

### 필요한 이유

자료를 저장하기 전에 DB가 지켜야 할 관계와 제약을 먼저 검증해야 한다.

### 주요 구현 내용

구현 대상:  

- DB connection 관리
- SQLite 설정
- schema initialization
- schema_version
- 19개 V1 table
- PK/FK
- CHECK
- UNIQUE
- partial unique index
- 필요한 일반 index
- transaction helper
- repository foundation

DATABASE_DESIGN.md를 authoritative source로 사용한다.  

임의로 테이블을 추가하거나 제거하지 않는다.  

특히 확인:  

- stream_code TEXT
- characteristic_value typed value exactly one
- characteristic_value.mapping_id
- representative partial unique constraint
- data_quality_issue QC rule snapshot
- FK 및 ON DELETE 정책
- soft delete / deactivate 원칙

stream_characteristic은 (stream_code,dictionary_id) 복합 PK, characteristic_value_id FK, updated_at으로 구성한 현재값 참조 캐시다. 고정 연구 컬럼·실제 값 복제를 두지 않는다. QC에는 nullable characteristic_value_id FK와 is_active를 추가한다. 19개 테이블 수는 유지한다.  

초기 DB부터 schema_version을 기록하고 migrations/001_initial.sql, 002_....sql 등의 순차 migration을 적용한다. runner·적용 실패 rollback·재적용 방지와 인덱스 실행 계획은 이 Phase의 구현·검증 작업이다. 이번 문서 작업에서 SQL 파일을 생성하지 않는다.

### 예상 모듈

database의 연결·초기화·schema version·transaction 모듈, repositories 기반, tests/integration. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

19개 테이블·39개 FK, Boolean/상태 CHECK, typed value 0개/2개 거부·정확히 1개 허용, 대표값 중복 차단, 캐시 복합 PK와 값 FK, QC 값 FK·active 기본값, login_id 정규화 표현·길이·UNIQUE, 관리코드 숫자/길이, nullable 위경도 범위, 재초기화·순차 migration/version 일관성을 검증한다.

### 완료 기준

- 빈 DB 생성 성공
- 19개 테이블 확인
- constraint 테스트
- FK 테스트
- duplicate representative 차단 테스트
- schema version 확인
- DB 재초기화/재실행 안정성 확인

### 다음 단계 진입 조건

ON DELETE RESTRICT / ON UPDATE NO ACTION, exactly-one CHECK와 부분 UNIQUE 명세는 감사에서 정리했다. 확정된 C1/U1/Q1·관리코드·좌표·상태 CHECK·순차 migration을 구현하고 실제 제약·FK 테스트 통과 후 Phase 1A로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 1A. 로컬 사용자/인증 기반

### 목표
app_user와 현재 작업자를 화면에 의존하지 않는 Service/Repository 계층에서 지원한다.

### 필요한 이유
Import·QC·보정 이력을 로그인 사용자와 연결하려면 업무 기능보다 먼저 인증 기반이 필요하다.

### 주요 구현 내용
최초 사용자 등록, 로그인 검증, 현재 작업자 전달, 사용자 비활성화, 세 user FK 정책을 구현할 예정이다. login_id는 trim→소문자→ASCII 영문/숫자/._- 및 4~50자 검증으로 정규화해 저장·조회하며 별도 정규화 컬럼은 추가하지 않는다. display_name/department는 이 제한 대상이 아니다. 온라인 회원가입·협업·복잡한 권한 모델은 만들지 않는다.

### 예상 모듈
AuthService, UserRepository와 app 조립 책임의 후보이며 아직 파일은 없다.

### 테스트
사용자 없는 상태, 최초 등록, 로그인 성공/실패, 비활성 로그인 차단, 평문/hash 비노출, 사용자 비활성화 후 기존 Import·QC·이력 연결 보존을 검증한다.

### 완료 기준
인증 관련 blocking 정책과 테스트를 완료하고 사용자 ID를 업무 Service로 전달할 수 있다.

### 다음 단계 진입 조건
hashing library/알고리즘·최초 등록/오프라인 복구 정책을 확정하고 Gate 통과 후 Phase 2로 진행한다.

## Phase 2. Data Dictionary Foundation

### 목표

다양한 Excel 컬럼을 표준 연구항목으로 연결할 데이터 사전 시스템을 구축한다.

### 필요한 이유

표준항목과 별칭 기준이 있어야 원본 컬럼을 추측 없이 연결할 수 있다.

### 주요 구현 내용

구현 대상:  

- data_category
- dictionary_version
- unit_dictionary
- unit_conversion
- data_dictionary
- column_alias

Repository / Service 구현.  

기능:  

- category 등록/조회
- dictionary item 등록/조회
- alias 등록
- source_scope
- unit 등록
- unit conversion 등록
- dictionary version 관리
- inactive/deprecated 처리
- validation

아직 실제 연구자료의 모든 표준항목을  
임의로 대량 등록하지 않는다.  

실제 초기 dictionary 항목은  
연구자료 확인 후 별도 작업으로 구축한다.  

### 예상 모듈

repositories의 DictionaryRepository 책임, services의 DictionaryService 책임, models, tests/unit·integration. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

허용된 등록·조회·변경, 비활성화, 의미 변경 시 deprecated 처리, source_scope별 alias 충돌, 단위 참조, 현재 사전 버전 유일성.

### 완료 기준

- 표준항목 CRUD 중 허용된 작업 동작
- 물리삭제 방지
- alias collision 검증
- unit validation
- dictionary version 추적
- 테스트 통과

### 다음 단계 진입 조건

source_scope와 초기 단위·별칭 정책을 확인하고 사전 테스트 통과 후 Phase 3로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 3. Excel Workbook Inspector

### 목표

DB Import 전에 Excel의 구조를 안전하게 파악한다.

### 필요한 이유

시트·헤더·데이터 시작행을 먼저 파악해야 잘못된 위치의 값을 가져오는 일을 막을 수 있다.

### 주요 구현 내용

구현 대상:  

- Excel file reader
- workbook metadata
- sheet 목록
- sheet dimensions
- multi-sheet inspection
- merged cells inspection
- candidate header detection
- multi-row header 처리 기반
- data start row 탐색
- sample rows
- source column metadata
- normalized header

원본 Excel을 수정하지 않는다.  

V1 기본:  
.xlsx  

실제 Excel 자료를 테스트 fixture로 직접 복사하지 말고  
민감정보 없는 synthetic fixture를 만든다.  

필요하면 실제 자료는 개발자가 로컬에서  
수동 검증용으로만 사용할 수 있도록 한다.  

### 예상 모듈

importers의 reader·sheet inspector·header detector, 구조 결과 models, tests/fixtures. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

단일/다중 행 헤더, 병합 헤더, 제목 행, 빈 행, 여러 시트의 synthetic xlsx. 읽기 전후 원본 hash와 1-based 위치를 확인한다.

### 완료 기준

- 단일 header Excel
- multi-row header
- merged header
- 제목 행 존재
- 빈 행 포함
- multi-sheet

테스트 통과.  

### 다음 단계 진입 조건

구조 후보와 sample이 원본 위치를 보존하고 테스트가 통과하면 Phase 4로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 4. Management Code Engine

### 목표

소하천 자료 연결의 핵심 식별자인 11자리 소하천 관리코드를 안전하게 처리한다.

### 필요한 이유

이름 차이에 영향을 받지 않고 소하천을 연결하려면 식별자 처리가 먼저 안정되어야 한다.

### 주요 구현 내용

구현 대상:  

- province_code
- city_county_code
- town_code
- stream_serial_no
- stream_code

모두 TEXT.  

기능:  

- component validation
- code composition
- existing code comparison
- length validation
- leading zero preservation
- Excel numeric/scientific notation 방어
- duplicate detection 지원

구성요소와 기존 stream_code가 불일치해도  
자동 수정하지 않는다.  

### 예상 모듈

UI와 분리된 관리코드 검증·구성 모듈, services 연계, tests/unit. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

정상·선행 0 코드, 구성요소 누락·길이 오류·연결 불일치, 중복, Excel 숫자·과학적 표기 입력. 추정 복원과 자동 덮어쓰기가 없는지 확인한다.

### 완료 기준

- 정상 코드
- leading zero
- 구성요소 누락
- 길이 오류
- 구성 결과 불일치
- Excel numeric input

테스트 통과.  

### 다음 단계 진입 조건

확정된 숫자·길이·TEXT 형식과 Service 구성요소 연결 검증을 구현하고, Excel 입력 처리 세부 규칙과 테스트를 확인한 뒤 Phase 5로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 5. Column Mapping & Import Preview

### 목표

Excel 컬럼을 DB에 넣기 전에 무엇이 어떤 표준항목으로 연결되는지 확인한다.

### 필요한 이유

사용자가 저장될 항목과 제외 항목을 확인한 뒤 Import하도록 준비하는 단계다.

### 주요 구현 내용

구현 대상:  

- header normalization
- exact mapping
- alias mapping
- source_scope
- mapping status
- UNMAPPED
- 제외 선택(기존 DB 설계의 IGNORED 표현 사용)
- user mapping model
- Import Preview model
- required-field validation
- sensitive-column detection

중요:  

fuzzy matching 자동 확정 금지.  

UNMAPPED를 자동 dictionary 생성하지 않는다.  

민감정보 값을 Preview/log에 노출하지 않는다.  

Preview에서는 최소:  

- sheet
- source column
- source header
- normalized header
- mapping status
- dictionary item
- unit
- sample
- validation issue

를 확인 가능하도록 한다.  

이 Phase에서는 GUI 전체를 만들 필요 없다.  
Service/model 수준의 Preview 결과를 먼저 구현한다.

V1 Draft 저장·재개 기반도 이 Phase에서 구현한다. 사용자 ID·원본 경로/hash·Sheet/Header/Data 행·매핑·현재 단계·저장 시각 등 선택 상태만 로컬 workspace 파일(JSON 등)에 저장하며 연구 DB 테이블을 추가하지 않는다. 파일 존재·hash 검증, 이동/불일치 시 사용자 재지정, 셀·민감값 미복제, 종료 후 재개를 검증한다. W1 형식/원자 저장/소유권/정리 계약을 먼저 정한다.  

문자열·숫자·날짜·단위의 normalization과 typed value 기본 검증도 이 단계에서 준비한다. Phase 6이 검증된 값을 저장하도록 하며 GUI는 아직 붙이지 않는다.  

### 예상 모듈

importers의 mapper·normalizer·validator, services의 ImportService 책임, Preview·사용자 매핑 models. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

정확한 별칭 매핑, UNMAPPED, ambiguous·중복 매핑, 필수항목, 민감 header·sample 차단, 정상/실패 값 정규화, 관리코드 연계.

### 완료 기준

- known alias 자동매핑
- unknown → UNMAPPED
- ambiguous mapping 탐지
- sensitive header 탐지
- required mapping 검증
- mapping provenance 생성
- 테스트 통과

### 다음 단계 진입 조건

Import type별 필수값·blocking, normalization·결측 표현과 mapping_method 정책을 확정하고 Preview 계약 테스트 통과 후 Phase 6으로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 6. Import Engine & Provenance

### 목표

검증된 Preview 결과를 실제 DB에 안전하게 저장한다.

### 필요한 이유

검증 결과를 저장하면서 원본 출처와 실패 이력까지 보존해야 연구 DB로 사용할 수 있다.

### 주요 구현 내용

구현 대상:  

- source_file
- import_history
- import_sheet
- import_column_mapping
- small_stream
- stream_relation
- characteristic_value

Import transaction 정책은  
DATABASE_DESIGN.md와 DATA_RULES.md를 따른다.  

기본 흐름:  

import_history RUNNING commit  
→ actual data transaction  
→ SUCCESS / FAILED history update  

실패 시 실제 data transaction rollback.  

Import provenance:  

source_file  
→ import_history  
→ import_sheet  
→ import_column_mapping  
→ characteristic_value  

characteristic_value:  

- source_row
- mapping_id
- original_value
- original_unit
- typed value

를 적절히 보존한다.  

UNMAPPED 실제 셀값은 V1 DB에 별도 저장하지 않는다.  

### 예상 모듈

ImportService·ImportRepository·StreamRepository·CharacteristicRepository 책임, importers의 importer, database transaction 연계. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

성공 Import, 데이터 저장 중 실패·rollback, FAILED 이력 보존, source hash·중복 파일 경고, mapping_id/source_row 역추적, mapping/시트/import 불일치 거부, 민감값·UNMAPPED raw 셀 미저장.

### 완료 기준

- 정상 Import
- 실패 rollback
- FAILED history 유지
- source hash 기록
- provenance 역추적
- duplicate file warning
- sensitive field 제외
- 테스트 통과

### 다음 단계 진입 조건

settings_json·실패 진단 및 T1(A/B/C 중단 복구·B 완료 판별·멱등성) 계약을 정하고 저장 통합 테스트 통과 후 Phase 7로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 7. QC Engine

### 목표

Import된 데이터의 문제 가능성을 자동으로 탐지하되 자동수정하지 않는다.

### 필요한 이유

저장된 값의 문제 가능성을 연구자에게 제시할 공통 규칙 실행 체계가 필요하다.

### 주요 구현 내용

QC_RULES.md를 authoritative source로 사용한다.  

Priority A부터 구현한다.  

예:  

- management code
- required field
- data type
- duplicate code
- required mapping
- sensitive column

그 후 Priority B:  

- stream name conflict
- characteristic conflict
- unit mismatch
- dictionary mapping
- representative integrity

Priority C는 V1 범위와 난이도를 보고 순차 구현:  

- range
- outlier
- row alignment
- reference year
- cache consistency

중요:  

ERROR/WARNING/INFO와  
review_status를 분리한다.  

QC issue 생성 당시:  

- rule_id
- rule_version_snapshot
- rule_parameters_snapshot_json

을 보존한다.  

자동수정하지 않는다.  

Phase 4~6의 저장 전 검증을 없애거나 이 단계로 미루지 않는다. 기존 검증을 공통 QC 체계에 연결한다. 대표값·캐시 규칙은 준비된 테스트 데이터로 검증하고 Phase 8의 실제 업무 연동 테스트를 추가한다. Priority C의 초기 구현 범위와 근거를 기록하고 V1에서 하기로 한 항목은 최종 Gate 전 완료한다.  

### 예상 모듈

qc의 engine·rules·result, QCService·QualityRepository 책임, tests/unit·integration. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

규칙 실행, issue 생성, severity/review 독립성, 규칙 변경 후 과거 snapshot 보존, 민감값 비노출, 영향 범위 재검사·과거 issue 보존, 자동수정 부재.

### 완료 기준

- rule execution
- issue creation
- severity
- review status
- snapshot
- sensitive-value masking
- 재검사
- 테스트 통과

### 다음 단계 진입 조건

값별 characteristic_value_id와 is_active를 사용하고 재검사 범위·반복 탐지·실행 안내 계약을 정한다. 성공 범위의 과거 issue 비활성화·새 issue 저장 원자성, 활성 ERROR 차단과 review 독립성을 검증한다. 선정한 V1 규칙 근거와 테스트 통과 후 Phase 8로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 8. Representative & History

### 목표

여러 출처의 특성값 중 연구에 사용할 대표값을 관리한다.

### 필요한 이유

출처별 값을 보존한 채 분석에 사용할 값을 명시적으로 정해야 한다.

### 주요 구현 내용

구현 대상:  

- representative selection
- representative change
- stream_characteristic rebuild
- record_history
- user correction
- deactivate/restore
- QC 상태 연계

원본 characteristic_value overwrite 금지.  

사용자 보정:  

original  
→ USER_CORRECTION value  
→ QC/history  
→ 필요 시 representative 변경  

### 예상 모듈

StreamService·CharacteristicRepository·HistoryRepository 책임, 캐시 rebuild 모듈, tests/integration. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

대표값 최대 하나, 선택·캐시·이력 어느 단계든 실패 시 전체 rollback, 캐시 키와 참조 값 일치, 원본 값 미복제·재구축, 활성 ERROR 차단과 WARNING/INFO 확인, 보정값 별도 생성·원본 보존, 비활성/복원을 검증한다.

### 완료 기준

- 대표값 최대 하나
- 대표값 변경 이력
- correction 원본 보존
- cache rebuild
- inactive value 처리
- 테스트 통과

### 다음 단계 진입 조건

확정된 현재값 정책(대상 값 ID의 활성 ERROR 신규 지정 금지, WARNING/INFO는 확인 후 명시적 지정)을 구현하고 이력·캐시·QC 통합 테스트 통과 후 Phase 9로 진행한다. 공통 Phase Gate도 만족해야 한다.

Phase 8 Final Gate 통과: 합성 임시 DB의 Phase 7 QC·Phase 8A/B/C 전체 값 lifecycle에서
원본 출처, QC issue, 현재값 불변조건, 캐시 재구축, 이력 및 업무별 rollback을 검증했다.
Phase 8 완료 기준을 충족하여 Phase 9 진입이 가능하다. Phase 9 구현은 아직 시작하지 않았다.

## Phase 9. 로그인·홈·소하천 조회 GUI

00 로그인·최초 사용자 등록, 01 홈, 09 소하천 조회, 14 작업이력, 15 마이페이지를 기존 Service에 연결한다. 최근 작업은 record_history를 공유한다.

Phase 9A Read/Query Backend 완료: 목록 검색·지역 코드 필터·정렬·DB pagination과 제한된
상세/현재값/QC/출처 표시 모델을 제공한다. Phase 9B 앱 shell·로그인·목록 GUI와 9C 상세 GUI를
구현했고, 9D-2 Home GUI·9D-3 작업이력 GUI·9D-4 마이페이지도 제공한다. Phase 9 Final Gate는
합성 임시 DB의 전체 읽기 전용 화면 흐름과 DB 불변성 검증을 통과했다. Phase 9 완료 기준을 충족했다.
실제 Windows 최종 육안 검수와 scrollbar 등 visual polish는 별도 후속 확인 항목이다.

Phase 9B 구현: PySide6 앱 시작·최초 사용자 등록/로그인·로그아웃·앱 shell과 09 소하천
목록의 검색·지역 연동 필터·서버 정렬·DB 페이지 조회를 연결했다. 지역 선택지는 조회 Service가
활성 소하천의 실제 코드/명칭을 읽는다. 9C 상세는 후속 단계에서 구현했으며,
9D-2 Home GUI, 9D-3 작업이력 GUI와 9D-4 마이페이지를 제공하며 최종 Gate를 통과했다.

Phase 9C-0 구현: schema migration과 분리한 versioned JSON 연구 사전과 원자적 bootstrap
Service를 제공한다. 실제 70개 저장 leaf와 qualified alias, 확인된 단위만 등록하며 동일 정의는
재사용하고 충돌은 전체 rollback한다. 승인 internal name을 현재 dictionary ID로 해석하는
deny-by-default 상세 표시 정책 기반을 제공한다. Phase 9C 상세 GUI 자체는 후속 작업이다.

Phase 9C 구현: 목록 선택의 관리코드로 상세를 다시 조회하고 기본정보·좌표, 연구 사전의
category별 승인 특성, 유효한 현재 사용값, 활성 QC와 별도 검토상태, 제한된 출처 및 값 이력을
읽기 전용으로 표시한다. batch 조회와 worker별 SQLite 연결, stale 응답 차단을 유지한다.
Phase 9C-UI는 Figma 09 정보구조에 맞춰 앱 shell, 검색·목록, 선택 요약 및 상세 presentation을
정렬했다. 기존 조회 Service와 domain 상태 문구는 유지하며 미구현 분석·내보내기 동작은 연결하지 않는다.
Phase 9D-1 read backend는 GUI 없이 Home·작업이력·마이페이지용 bounded SELECT projection을
제공한다. 활성 소하천·QC aggregate·연구 사전 상태, 실제 다섯 종류의 record_history event,
공개 사용자 profile과 최근 작업을 안전하게 조회하며 raw JSON·내부 ID·password hash·절대경로를
public model에 포함하지 않는다. Phase 9D-2는 로그인 landing Home에서 활성 소하천·QC 집계·
연구 사전 상태와 최근 5개 작업을 이 projection으로 표시한다. Phase 9D-3은 다섯 작업 유형의
변경이력을 50건 단위로 조회하고
작업 유형·안전한 작업자 option·11자리 관리코드 필터를 제공한다.
Phase 9D-4는 Topbar 사용자 영역에서 현재 작업자의 공개 profile과 최근 최대 5개 작업을 조회하며
계정 수정 기능은 제공하지 않는다. Phase 9 Final Gate에서 로그인·Home·목록·상세·작업이력·
마이페이지·로그아웃과 pagination·필터·resize, 조회 전후 DB 불변성을 통합 검증했다.

### 목표

연구자가 코드 없이 DB를 조회하고 검토할 수 있게 한다.

### 필요한 이유

검증된 Service 위에 화면을 붙여 저장 규칙을 화면 코드에 중복 구현하지 않도록 한다.

### 주요 구현 내용

이 Phase부터 본격적으로 PySide6 GUI를 만든다.  

기능 후보:  

- 소하천 목록
- 관리코드 검색
- 지역 필터
- 하천 상세
- 특성정보 조회
- 출처 확인
- representative 표시
- QC 상태 표시
- Import history 조회

UI는 Service를 호출한다.  

UI에서 SQL/Repository 직접 호출하지 않는다.  

### 예상 모듈

ui의 조회·목록·상세 화면, app 조립, 기존 Service 호출, GUI 검증. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

관리코드 검색, 지역 필터, 상세·출처·대표값·QC·Import 이력 표시, synthetic 대량 데이터 사용성, UI의 직접 SQL/Repository 접근 부재.

### 완료 기준

- 기본 검색/조회
- 상세정보
- provenance 확인
- QC 표시
- 대량 데이터에서도 기본 사용성 확보

### 다음 단계 진입 조건

연구자가 코드 없이 조회하고 출처를 확인할 수 있으며 이전 테스트가 통과하면 Phase 10으로 진행한다. 공통 Phase Gate도 만족해야 한다.

Phase 9 Final Gate를 통과하여 Phase 10 진입이 가능하다.

## Phase 10. Import·사전·QC·보정·DB관리·환경 GUI

02~08 화면과 10 DB 관리, 16 설정을 연결한다. DB 관리에서 특성값 직접 수정은 금지하며 08 보정으로 연결한다. UI 설정은 QSettings/local config, Draft는 연구 DB 밖의 로컬 workspace 파일을 사용한다. Phase 5에서 마련한 저장·재개 Service를 GUI에 연결한다. Backup/Restore의 실제 기능은 Phase 14에서 연결·검증하며 이 단계에서 완료로 간주하지 않는다.

### 목표

앞에서 구현한 데이터 관리 기능을 연구자가 GUI에서 사용할 수 있게 한다.

### 필요한 이유

조회 화면 다음으로 입력·매핑·검토 작업을 연결하면 전체 데이터 관리 흐름을 검증할 수 있다.

### 주요 구현 내용

기능:  

- 파일 선택
- Workbook inspection
- sheet 선택
- header 확인
- mapping
- UNMAPPED 처리
- dictionary 등록
- Import Preview
- Import 실행
- QC issue 목록
- issue 상세
- review status 변경
- correction
- representative 변경

위험한 작업은 확인 절차를 둔다.  

### 예상 모듈

ui의 등록·사전·매핑·Preview·QC 화면, 기존 Service 연계. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

파일 선택부터 시트·헤더 확인, UNMAPPED 사용자 처리, Preview·Import·검토·보정·대표값 변경까지 GUI 흐름. 취소·위험 작업 확인·민감값 비노출.

### 완료 기준

연구자가 Python 코드를 직접 수정하지 않고도  
Excel → Preview → Import → QC 검토  
흐름을 수행할 수 있음.  

### 다음 단계 진입 조건

Python 코드 수정 없이 Excel → Preview → Import → QC 검토를 완료하고 테스트가 통과하면 Phase 11로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 11. Basic Statistics

V1 통계는 유효 N, 결측, 평균, 중앙값, 표준편차, 최소, Q1, Q3, 최대와 지역별 비교다. 그래프는 Histogram, Boxplot, Scatter plot이다. 수치형 항목 선택은 data_dictionary.data_type과 analyzable을 기준으로 동적으로 구성하며 Figma 예시 컬럼을 하드코딩하지 않는다. 결측 집계 대상·통계 정의·QC 포함 정책은 구현 전에 확인하며 연구 threshold는 만들지 않는다.

### 목표

구축한 소하천 특성정보를 기초적인 연구 분석에 활용한다.

### 필요한 이유

신뢰 가능한 조회·대표값 기반 위에서 분석 대상을 명시적으로 선택해야 한다.

### 주요 구현 내용

V1 분석 예:  

- count
- missing count
- mean
- median
- standard deviation
- min
- max
- quantile
- group comparison
- selected variables

분석 대상은  
data_dictionary.analyzable 등을 참고한다.  

QC 상태를 무시하고 자동 분석하지 않는다.  

분석 전 포함 데이터의 품질상태를  
사용자에게 확인할 수 있도록 한다.  

연구자료에 없는 threshold를 임의 생성하지 않는다.  

### 예상 모듈

analysis의 descriptive·group_statistics, AnalysisService 책임, 변수·필터 선택 UI. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

정답을 확인할 수 있는 synthetic 값의 count·결측수·평균·중앙값·표준편차·분위수·그룹비교, 필터 재현, analyzable·QC 안내, 결측과 0 구분.

### 완료 기준

- 변수 선택
- 대상 하천 필터
- 기초통계
- 결과 재현
- 결측 처리 명시
- 테스트 통과

### 다음 단계 진입 조건

통계 정의·결측 집계 대상·포함/제외 정책을 명시하고 결과 테스트 통과 후 Phase 12로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 12. Basic Charts

### 목표

기초 분석 결과를 시각적으로 확인한다.

### 필요한 이유

수치 결과를 그림으로 확인하되 변수·단위·표본수·필터를 함께 해석할 수 있어야 한다.

### 주요 구현 내용

V1 후보:  

- histogram
- box plot
- scatter plot

그래프에는 가능한 경우:  

- 변수명
- 단위
- 표본수
- 필터 조건

을 표시한다.  

GIS 지도는 V1 범위가 아니다.  

PNG 저장 기반은 Phase 13 ExportService 흐름에 통합한다. UI 직접 출력이나 중복 출력 경로를 만들지 않는다.  

### 예상 모듈

analysis의 시각화 모듈, matplotlib 연계, 차트 UI, PNG 출력 기반. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

Histogram·Boxplot·Scatter plot 중 선정 범위, 변수·단위·표본수·필터 표시, 결측/오류 입력, GUI 연계와 PNG 저장.

### 완료 기준

- 변수 선택
- 그래프 생성
- 단위 표시
- PNG 저장
- 오류 데이터 처리
- GUI 연계

### 다음 단계 진입 조건

선정한 그래프의 생성·표시·저장이 검증되면 Phase 13에서 Export 흐름을 통합한다. 공통 Phase Gate도 만족해야 한다.

## Phase 13. Excel / PNG Export

V1 결과 내보내기는 Excel(소하천 조회 결과·QC 결과·보정/변경 이력·기초통계)과 PNG(그래프)다. PDF는 제외한다. 내부 PK·로그·민감정보·app_user 인증정보는 일반 Export에서 제외한다. 원본 Excel을 덮어쓰지 않으며 내보낸 사용자 파일을 프로그램이 자동 삭제하지 않는다.

### 목표

연구보고서 및 후속 분석에서 사용할 결과를 외부 파일로 안전하게 출력한다.

### 필요한 이유

조회·분석 결과를 연구보고서에서 쓰려면 안전하고 일관된 파일 출력이 필요하다.

### 주요 구현 내용

Excel Export 후보:  

- 소하천 조회 결과(선택한 기본·특성정보 및 현재 사용값)
- QC 결과
- 보정/변경 이력
- 기초통계

기본 제외:  

- 민감정보
- 내부 로그
- 불필요한 내부 PK

provenance 포함 Export는 별도 옵션으로 둘 수 있다.  

원본 Excel을 overwrite하지 않는다.  

### 예상 모듈

ExportService, exporters의 Excel·PNG, Export UI, tests/integration. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

xlsx 재읽기로 컬럼명·단위·선택 항목 확인, PNG 출력 확인, 민감정보·내부 로그·불필요 PK 제외, provenance 옵션, 원본 덮어쓰기 거부.

### 완료 기준

- xlsx export
- PNG export
- 단위/컬럼명 확인
- 민감정보 제외
- 원본 overwrite 방지
- 테스트 통과

### 다음 단계 진입 조건

Excel/PNG 출력과 기존 원본 보존 테스트 통과 후 Phase 14로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 14. Backup / Recovery / Operational Safety

### 목표

실제 연구자료 사용 중 실수로 DB를 손상시키는 것을 방지한다.

### 필요한 이유

실제 연구자료 적용 전에 백업과 복구 절차를 검증해 실수와 실패에 대응해야 한다.

### 주요 구현 내용

기능:  

- DB backup
- 중요 작업 전 backup
- backup metadata
- restore 절차
- 작업 실패 복구
- source file 보호

Restore 전 자동 안전백업을 생성하고, 성공 후 새 현재 DB의 record_history에 DB_RESTORE 작업을 기록한다. 데이터 비활성화 복원의 RESTORE와 구분한다. 복원된 사용자 ID의 동일인 여부·재인증, 백업 후 최신 이력의 안전백업 보존, 이력 기록 실패 대응을 B1에 따라 확정한다. 정확한 SQLite backup/restore·WAL·파일 전환 기술은 이 Phase에서 결정한다.

물리삭제보다 deactivate를 우선한다.  

backup metadata는 새 연구 DB 테이블 추가의 근거가 아니다. 19개 테이블을 유지하며 로컬 관리 정보의 표현·저장 위치는 구현 전에 정한다. 복구 시험은 테스트 DB로 수행한다.  

### 예상 모듈

BackupService, database 백업·복구 기반, 로컬 backup metadata 처리, 복구 UI·운영 절차 문서. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

테스트 DB 백업·복원, 값·이력·무결성 비교, 실패 시 일관성, 원본 파일 보호, 중요 작업 전 백업, 비활성화 우선 동작.

### 완료 기준

- backup 생성
- test DB restore
- 실패 시 데이터 일관성 확인
- 사용자 실수 대응 절차 문서화

### 다음 단계 진입 조건

백업 metadata 표현·저장 위치와 복구 절차를 정하고 테스트 DB 복구가 검증되면 Phase 15로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 15. Windows Packaging

### 목표

개발환경이 없는 Windows PC에서도 프로그램을 실행할 수 있게 한다.

### 필요한 이유

개발 환경과 분리된 Windows에서도 핵심 기능과 로컬 데이터 경로가 동작해야 한다.

### 주요 구현 내용

PyInstaller 기반.  

확인:  

- SQLite DB 경로
- config 경로
- log 경로
- export 경로
- backup 경로
- bundled resource
- Windows path
- Korean filename/path
- OneDrive 경로 가능성

인터넷 연결 없이 실행 가능해야 한다.  

### 예상 모듈

PyInstaller 패키징 설정·리소스 구성, app·config 경로 처리, 배포 안내. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

개발환경 없는 clean PC의 오프라인 실행, 한글 파일/경로·OneDrive 경로, DB/config/log/export/backup 경로, 리소스, Import·조회·QC·분석·Export·백업.

### 완료 기준

- Windows 실행파일 생성
- clean PC 테스트
- Excel Import
- DB 조회
- QC
- 분석
- Export
- backup

핵심 흐름 end-to-end 확인.  

### 다음 단계 진입 조건

패키징된 프로그램의 핵심 흐름과 기존 테스트가 통과하면 Phase 16 최종 검증으로 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase 16. V1 Final Validation

### 목표

전체 workflow와 원본 보존·추적성·복구를 검증하여 V1 완료 여부를 판정한다.

### 필요한 이유

기능별 성공만으로 놓칠 수 있는 전체 연결과 원본 보존을 최종 확인해야 한다.

### 주요 구현 내용

최종 검증.  

실제 연구자료를 적용하기 전  
synthetic fixture로 전체 workflow 검증.  

그 후 권한 있는 로컬 환경에서  
실제 연구자료를 이용한 수동 검증을 수행할 수 있다.  

확인:  

Excel  
→ inspection  
→ mapping  
→ preview  
→ import  
→ QC  
→ representative  
→ browse  
→ statistics  
→ chart  
→ export  

추가 확인:  

- 원본 파일 미변경
- 관리코드 TEXT 유지
- provenance 추적
- row alignment 자동수정 없음
- 이상치 자동삭제 없음
- 민감정보 DB/Export 제외
- transaction rollback
- history 유지
- backup/restore

### 예상 모듈

전체 통합 검증 시나리오·synthetic fixtures·검증 기록, 필요한 범위의 기존 모듈 수정. 모두 예정 구조이며 기존 아키텍처의 책임 분리를 따른다.

### 테스트

Excel → inspection → mapping → preview → import → QC → representative → browse → statistics → chart → export 전체 흐름과 원본 미변경, 코드 TEXT, provenance, 자동 행 이동·이상치 삭제 없음, 민감정보 제외, rollback·이력·backup/restore.

### 완료 기준

전체 workflow 및 추가 보존·복구 검증이 통과하고 검증 기록을 남긴다. 실제 자료 검증은 권한 있는 로컬 환경에서 가능한 경우 수행하며 수행 여부와 한계를 기록한다.  

### 다음 단계 진입 조건

최종 Gate를 모두 통과하면 V1 완료로 판정한다. 후속 버전은 별도 요청·범위 확인 후 진행한다. 공통 Phase Gate도 만족해야 한다.

## Phase Gate

각 Phase 종료 시 아래 항목을 확인한다. Gate를 통과하지 못하면 다음 Phase로 넘어가지 않는다.

1. 관련 테스트 통과
2. 기존 테스트 regression 없음
3. 문서와 코드 일치
4. 새로운 schema 변경 필요 여부 확인 및 필요한 설계 결정 완료
5. 연구자료 의미를 추정하여 구현한 부분 없음
6. 민감정보 노출 없음
7. 다음 Phase 진행 가능 여부와 남은 조건 확인

이 문서의 테스트는 미래 완료 기준이며 현재 실행 결과가 아니다. 미완료 사항을 테스트 약화나 임시 하드코딩으로 숨기지 않는다.

## 개발 중 설계 변경

DATABASE_DESIGN.md, DATA_RULES.md, QC_RULES.md와 다른 구현이 필요하면 문제 확인 → 설계 영향 확인 → 문서 수정 → 테스트 수정/추가 → 구현 순서로 진행한다. 코드부터 임의 변경하지 않는다.

충돌 내용, 변경 필요 이유, 영향 범위, 제안 수정안을 먼저 보고한다. 문서 수정도 해당 작업의 허용 범위에서 수행한다. 로드맵은 코드·DB·migration·Git 작업의 자동 허가가 아니다.

## Git 개발 단위

Phase 전체를 무조건 하나의 commit으로 만들 필요는 없다. 기능 단위의 작은 commit을 권장한다. Phase 1은 DB connection, schema initialization, constraints, Repository foundation으로 나눌 수 있다. 미완성·깨진 상태를 기준점으로 삼지 않고 검증된 변경을 기록한다.

## V1 이후 로드맵

| 버전 | 확장 방향 |
| --- | --- |
| V2 | 분석 프로젝트, 분석 실행 이력, 재현성 강화와 고급 통계분석 |
| V3 | 강우·수위·유량 시계열 및 계측자료 |
| V4 | 홍수사상 분리, 강우-유량 관계, 수위/수심-유량 관계, 비선형 모형, 노모그래프 개발·보정·검증 |
| Future | GIS, GeoPackage/spatial DB, ML/DL. 개요 문서의 V5 확장 방향에 해당 |

V1의 Import·QC snapshot과 후속 분석 프로젝트 재현성 기능을 구분한다. 후속 버전을 이유로 시계열·모형 테이블을 V1에 미리 추가하지 않는다. 노모그래프/FPL/홍수사상 분리의 정확한 공식과 기준은 연구보고서 확인 전에 구현하지 않는다. 임의 공식·threshold를 만들지 않는다.

## 기존 설계와의 대조 및 확인 필요사항

- V1은 app_user를 포함한 19개 테이블이다. Draft는 V1 기능이며 연구 DB 밖의 로컬 workspace 파일로 저장한다.
- C1은 현재값 참조 캐시로, U1은 정규화 login_id로, Q1은 값 FK·is_active로 확정되었다. 활성 ERROR 차단과 검토 상태 분리는 DB 초기 구현을 막는 미정사항이 아니다.
- 과거 작업이력은 사용자 FK로 현재 display_name을 표시하며 V1 사용자명 snapshot을 추가하지 않는다.
- Restore 전 자동 안전백업, 성공 후 복원 DB에 DB_RESTORE 기록은 확정이다. B1의 기술·사용자 귀속·실패 대응은 Phase 14 전에 정한다.
- SQLite 제약의 문서상 호환성을 검토했다. 실제 DDL 테스트는 Phase 1이며 이번 감사에서 DB를 생성하지 않았다.
- Figma 실제 화면은 확인하지 못했다. 제공된 텍스트 UI 요구를 사용하고 예시 컬럼을 schema로 취급하지 않는다.
- Phase 0~16과 1A 순서를 유지한다. 자료 의미·QC 임계값·자동 보정·시계열·GIS·ML·서버 권한모델을 추가 확정하지 않는다.

## 현재 개발 시작점

최종 감사 판정은 **READY WITH NON-BLOCKING TODOS**다. C1/U1/Q1 및 기본 CHECK·순차 migration 정책이 확정되어 실제 Phase 1 DB 구현을 막는 설계 항목은 없다. 19개 테이블을 유지하며 Phase 0 기반과 Phase 1은 해당 작업 요청 및 Gate에 따라 시작할 수 있다.

이후 사용자의 명시적 요청 범위에서 착수한다. migration runner·실제 DDL/인덱스 검증은 Phase 1 구현 작업이다. 인증 library는 Phase 1A, workspace 상세는 Phase 5, Import 중단 복구는 Phase 6, history 계약은 Phase 8, 통계 정의는 Phase 11, Backup/Restore 기술은 Phase 14 전에 결정한다.

이번 감사는 설계문서 수정만 수행하며 코드·DB·migration·UI·commit/push를 실행하지 않는다.
