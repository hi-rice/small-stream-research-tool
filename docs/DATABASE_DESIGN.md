# V1 데이터베이스 설계

이 문서는 `small-stream-research-tool`의 V1 SQLite DB 구현 기준이다. `AGENTS.md`, `PROJECT_OVERVIEW.md`, `ARCHITECTURE.md`의 원본 보존·추적성·계층 분리 원칙을 따른다. 현재는 설계 단계이며 이 문서가 DB, SQL schema, migration 또는 ORM 모델의 구현을 의미하지 않는다.

명시된 컬럼·키·제약조건과 검토 후보를 구분한다. ‘예’로 제시한 상태값은 아래에 별도 결정이 없는 한 확정된 CHECK 목록이 아니다. 각 컬럼 표의 NULL 허용 여부와 기본값은 제공된 설계를 그대로 따른다. 별도 FK·UNIQUE·CHECK가 명시되지 않은 경우 새로운 제약조건을 임의로 추가하지 않는다.

## 1. 공통 DB 원칙

DB:  
SQLite  

기본 설정:  
PRAGMA foreign_keys = ON  

원칙:  
- 연구 식별코드는 TEXT
- 선행 0 보존
- INTEGER PRIMARY KEY에는 불필요한 AUTOINCREMENT를 사용하지 않음
- 날짜/시간은 V1에서 ISO 8601 형식 TEXT를 기본으로 함
- BOOLEAN 개념은 SQLite INTEGER 0/1 + CHECK 사용
- FK가 있는 연구 데이터는 임의 CASCADE DELETE하지 않음
- 연구 원본은 가능한 한 물리 삭제하지 않음
- is_active/status/deprecated/history 방식 우선
- 필요한 검색 컬럼에는 INDEX 사용
- JSON이 필요한 설정성 데이터는 TEXT로 저장한다. import_history.settings_json과 quality_rule.parameters_json은 JSON 형식의 설정 데이터다.
- DB schema version을 관리함

## 2. V1 테이블 목록

V1의 기준 테이블은 다음과 같다.  

1. schema_version  
2. data_category  
3. dictionary_version  
4. unit_dictionary  
5. unit_conversion  
6. data_dictionary  
7. column_alias  
8. source_file  
9. import_history  
10. import_sheet  
11. import_column_mapping  
12. small_stream  
13. stream_relation  
14. characteristic_value  
15. stream_characteristic  
16. quality_rule  
17. data_quality_issue  
18. record_history  
19. app_user  

중요:  
import_error 테이블은 V1에서 만들지 않는다.  

파일/Import 자체 실패:  
import_history.error_code / error_message  

데이터 내용 문제:  
data_quality_issue  

로 관리한다.

기존 18개 연구·기반 테이블을 보존하고 로컬 앱 계정 app_user를 추가한 확정 V1 테이블 수는 **19개**다. Draft/Workspace는 V1 기능이며 연구 DB 밖의 로컬 workspace 파일로 저장한다.

## 3. schema_version

### 목적

SQLite DB schema의 적용 버전을 기록한다.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `schema_version_id` | INTEGER | PRIMARY KEY |
| `version` | TEXT | NOT NULL UNIQUE |
| `description` | TEXT | NULL |
| `migration_name` | TEXT | NULL |
| `app_version` | TEXT | NULL |
| `applied_at` | TEXT | NOT NULL |

### PK

`schema_version_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- FK: 별도 지정 없음.
- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.
- CHECK: 별도 명시된 확정 조건 없음. 검토 사항은 아래 규칙을 따른다.

### 제약조건 상세 및 운영 규칙

#### 삭제

일반 UI에서 삭제하지 않음.

### Schema version / 순차 migration

초기 DB부터 schema_version에 버전을 기록하고, 후속 DB 변경은 순차 migration으로 적용한다. 파일 구조 예시는 migrations/001_initial.sql, migrations/002_....sql이다. 이는 예정 구조이며 이번에는 SQL 파일이나 디렉터리를 생성하지 않는다.

migration runner는 Phase 1에서 구현 방식을 정한다. 적용 순서·이미 적용된 버전의 재적용 방지·실패 시 schema와 버전 기록의 일관성을 검증한다. schema_version을 실제 버전 판단에 사용하며 파일 존재만으로 적용 완료라고 간주하지 않는다.

## 4. data_category

### 목적

데이터 사전 항목의 분류 체계를 관리한다.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `category_id` | INTEGER | PRIMARY KEY |
| `category_key` | TEXT | NOT NULL UNIQUE |
| `category_name` | TEXT | NOT NULL |
| `parent_category_id` | INTEGER | NULL |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`category_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### FK

parent_category_id  
→ data_category.category_id  

#### CHECK

is_active IN (0,1)  

category_key는 내부 식별자이며 이름 변경과 분리한다.  

## 5. dictionary_version

### 목적

데이터 사전 버전 관리.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `version_id` | INTEGER | PRIMARY KEY |
| `version` | TEXT | NOT NULL UNIQUE |
| `description` | TEXT | NULL |
| `is_current` | INTEGER | NOT NULL DEFAULT 0 |
| `created_at` | TEXT | NOT NULL |

### PK

`version_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- FK: 별도 지정 없음.
- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### CHECK

is_current IN (0,1)  

#### 규칙

동시에 하나의 version만 is_current=1이 되도록 구현 시 보장한다.  
다음 부분 유일 인덱스로 최대 하나를 보장할 수 있다. 최초 등록 등 current가 0개인 상황까지 금지하는 제약은 아니다.

```sql
CREATE UNIQUE INDEX ux_dictionary_version_current
ON dictionary_version(is_current) WHERE is_current = 1;
```  

## 6. unit_dictionary

### 목적

표준 단위 정의.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `unit_id` | INTEGER | PRIMARY KEY |
| `unit_name` | TEXT | NOT NULL |
| `unit_symbol` | TEXT | NOT NULL UNIQUE |
| `dimension` | TEXT | NULL |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`unit_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- FK: 별도 지정 없음.
- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### CHECK

is_active IN (0,1)  

## 7. unit_conversion

### 목적

등록된 단위 간 변환 규칙.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `conversion_id` | INTEGER | PRIMARY KEY |
| `from_unit_id` | INTEGER | NOT NULL |
| `to_unit_id` | INTEGER | NOT NULL |
| `factor` | REAL | NOT NULL |
| `offset` | REAL | NOT NULL DEFAULT 0 |
| `formula_type` | TEXT | NOT NULL DEFAULT 'LINEAR' |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`conversion_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK


### 제약조건 상세 및 운영 규칙

#### FK

from_unit_id → unit_dictionary.unit_id  
to_unit_id → unit_dictionary.unit_id  

#### CHECK

is_active IN (0,1)  

#### UNIQUE

from_unit_id + to_unit_id + formula_type  

기본 선형 변환 개념:  
converted = original * factor + offset  

임의의 Python expression을 저장하거나 실행하는 용도로 사용하지 않는다.  

## 8. data_dictionary

### 목적

프로그램 전체 표준 데이터항목 정의.

특성정보뿐 아니라 향후 계측/분석 변수까지 확장 가능한 사전이다.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `dictionary_id` | INTEGER | PRIMARY KEY |
| `standard_name` | TEXT | NOT NULL |
| `internal_name` | TEXT | NOT NULL UNIQUE |
| `category_id` | INTEGER | NOT NULL |
| `data_type` | TEXT | NOT NULL |
| `unit_id` | INTEGER | NULL |
| `description` | TEXT | NULL |
| `storage_type` | TEXT | NOT NULL DEFAULT 'FLEX' |
| `analyzable` | INTEGER | NOT NULL DEFAULT 1 |
| `required` | INTEGER | NOT NULL DEFAULT 0 |
| `nullable` | INTEGER | NOT NULL DEFAULT 1 |
| `created_version_id` | INTEGER | NOT NULL |
| `deprecated_version_id` | INTEGER | NULL |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`dictionary_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### FK

category_id → data_category.category_id  
unit_id → unit_dictionary.unit_id  
created_version_id → dictionary_version.version_id  
deprecated_version_id → dictionary_version.version_id  

#### CHECK

data_type IN ('REAL','INTEGER','TEXT','DATE','DATETIME')  

storage_type:  
CORE / FLEX  

#### CHECK

storage_type IN ('CORE','FLEX')

기존 storage_type 컬럼과 허용값은 유지한다. CORE/FLEX를 근거로 stream_characteristic에 고정 연구 컬럼을 생성하거나 값을 중복 저장하지 않는다. 현재값 캐시는 두 분류 모두 동일한 dictionary_id→characteristic_value_id 참조 구조를 따른다.

#### CHECK

analyzable IN (0,1)  
required IN (0,1)  
nullable IN (0,1)  
is_active IN (0,1)  

#### 규칙

이미 데이터가 존재하는 표준항목의 의미, data_type, unit, internal_name을  
사용자가 임의로 바꾸는 방식은 피한다.  

의미가 달라지는 변경이면 새 항목 생성 + 기존 항목 deprecated를 원칙으로 한다.  

## 9. column_alias

### 목적

Excel 원본 컬럼명을 데이터 사전 항목에 연결.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `alias_id` | INTEGER | PRIMARY KEY |
| `dictionary_id` | INTEGER | NOT NULL |
| `alias_name` | TEXT | NOT NULL |
| `normalized_alias` | TEXT | NOT NULL |
| `source_scope` | TEXT | NOT NULL DEFAULT 'GLOBAL' |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`alias_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK


### 제약조건 상세 및 운영 규칙

#### FK

dictionary_id → data_dictionary.dictionary_id  

#### CHECK

is_active IN (0,1)  

#### UNIQUE

normalized_alias + source_scope  

#### 규칙

같은 scope에서 하나의 normalized alias가  
여러 dictionary item으로 자동 매핑되지 않도록 한다.  

자료 종류에 따라 같은 별칭의 의미가 다를 경우 source_scope를 구분한다.  

## 10. source_file

### 목적

등록된 원본 파일의 메타데이터 및 식별.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `source_file_id` | INTEGER | PRIMARY KEY |
| `file_name` | TEXT | NOT NULL |
| `original_path` | TEXT | NOT NULL |
| `file_extension` | TEXT | NULL |
| `file_size` | INTEGER | NULL |
| `file_hash` | TEXT | NULL |
| `file_modified_at` | TEXT | NULL |
| `source_description` | TEXT | NULL |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `registered_at` | TEXT | NOT NULL |

### PK

`source_file_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- FK: 별도 지정 없음.
- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### CHECK

is_active IN (0,1)  

#### 규칙

file_hash는 동일 파일 경고 등에 활용할 수 있지만  
무조건 UNIQUE로 강제하지 않는다.  

original_path는 파일의 영구 식별자로 간주하지 않는다.  
파일 이동 가능성이 있기 때문에 hash 및 등록이력을 함께 사용한다.  

프로그램이 원본 파일을 삭제하거나 덮어쓰지 않는다.  

## 11. import_history

### 목적

한 번의 Import 실행 단위를 기록.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `import_id` | INTEGER | PRIMARY KEY |
| `source_file_id` | INTEGER | NOT NULL |
| `created_by_user_id` | INTEGER | NULL; FK app_user.user_id, ON DELETE RESTRICT |
| `batch_code` | TEXT | NOT NULL UNIQUE |
| `import_type` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL |
| `started_at` | TEXT | NOT NULL |
| `finished_at` | TEXT | NULL |
| `total_rows` | INTEGER | NULL |
| `accepted_rows` | INTEGER | NULL |
| `warning_rows` | INTEGER | NULL |
| `rejected_rows` | INTEGER | NULL |
| `dictionary_version_id` | INTEGER | NULL |
| `schema_version_id` | INTEGER | NULL |
| `settings_json` | TEXT | NULL |
| `error_code` | TEXT | NULL |
| `error_message` | TEXT | NULL |
| `created_at` | TEXT | NOT NULL |

### PK

`import_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.
- CHECK: 아래 import status의 닫힌 목록을 적용한다.

### 제약조건 상세 및 운영 규칙

#### FK

source_file_id → source_file.source_file_id  
dictionary_version_id → dictionary_version.version_id  
schema_version_id → schema_version.schema_version_id  

status CHECK 허용값(기존 문서에 있던 상태만 사용):  
PENDING  
RUNNING  
SUCCESS  
FAILED  
ROLLED_BACK  
CANCELLED  

CHECK(status IN ('PENDING','RUNNING','SUCCESS','FAILED','ROLLED_BACK','CANCELLED'))를 적용한다. 새 상태를 추가하지 않는다.  

### Import transaction 경계

파일 선택·Preview 단계에는 실행 이력을 생성하지 않는다. 실제 DB 반영을 시작할 때 source_file 참조와 현재 작업자를 확인한다.

### A. Import 실행 이력 생성

import_history의 status를 RUNNING으로 기록하고 **별도 transaction에서 COMMIT**한다.

### B. 실제 데이터 Import

import_sheet, import_column_mapping, small_stream 신규/관련 반영, characteristic_value 및 해당 Import와 함께 확정되어야 하는 관련 자료를 **하나의 업무 transaction**으로 처리하는 것을 기본으로 한다. 성공하면 COMMIT, 실패하면 ROLLBACK한다.

### C. 결과 이력 갱신

- 성공 후 별도 transaction에서 import_history.status를 SUCCESS로 갱신하고 finished_at을 기록한다.
- 실패 후 별도 transaction에서 import_history.status를 FAILED로 갱신하고 error_code, error_message, finished_at을 기록한다.

실제 데이터 transaction이 rollback되어도 Import 시도와 실패 이력은 보존한다. rollback된 import_sheet/import_column_mapping 등의 FK를 data_quality_issue가 강제로 참조하게 하지 않는다. Preview issue와 실패 진단정보의 영구 보존 범위는 별도 구현정책으로 정할 수 있다. V1에 import_error 테이블을 추가하지 않는다.

#### status CHECK 적용 결정

RUNNING → SUCCESS 또는 FAILED의 기본 transaction 흐름을 유지하고 위 CHECK로 상태 오타를 막는다. PENDING/ROLLED_BACK/CANCELLED가 허용 목록에 있다는 이유로 Preview/Draft 이력을 생성하거나 새로운 취소 workflow를 구현하지 않는다. 해당 전이의 상세 업무 사용은 Phase 6에서 정하며 초기 DDL을 차단하지 않는다.

### Import 재현성

새 테이블·컬럼을 추가하지 않고 import_history.settings_json에 Import 실행 당시 normalization 설정, mapping 관련 설정/식별정보, Import option, 관련 application/module version 등의 재현성 설정을 snapshot으로 저장할 수 있도록 한다.

실제 mapping 상세 provenance의 authoritative record는 import_column_mapping이다. settings_json의 필드는 Import 구현 전에 versioned contract로 정의한다. 같은 원본·사전 버전·매핑·정규화 규칙·프로그램 버전 조건에서 가능한 한 동일 결과를 만들고, 사용자 mapping 판단과 보정은 이력으로 추적한다.

## 12. import_sheet

### 목적

하나의 Import에서 각 Excel sheet 처리 구조를 기록.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `import_sheet_id` | INTEGER | PRIMARY KEY |
| `import_id` | INTEGER | NOT NULL |
| `sheet_name` | TEXT | NOT NULL |
| `sheet_index` | INTEGER | NULL |
| `header_start_row` | INTEGER | NULL |
| `header_end_row` | INTEGER | NULL |
| `data_start_row` | INTEGER | NULL |
| `total_rows` | INTEGER | NULL |
| `accepted_rows` | INTEGER | NULL |
| `warning_rows` | INTEGER | NULL |
| `rejected_rows` | INTEGER | NULL |
| `status` | TEXT | NOT NULL |
| `created_at` | TEXT | NOT NULL |

### PK

`import_sheet_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- CHECK: status IN ('RUNNING','SUCCESS','FAILED'). 기존 Import 기본 실행 상태를 사용하고 새로운 상태명은 추가하지 않는다. 데이터 transaction이 rollback되면 sheet 행은 남지 않으며 영구 실패 이력은 import_history에 보존한다.

### 제약조건 상세 및 운영 규칙

#### FK

import_id → import_history.import_id  

#### UNIQUE

import_id + sheet_name  

DB provenance의 Excel 사용자 행·컬럼 위치는 원칙적으로 1-based다. 내부 index 기준을 확인해 저장 경계에서 변환한다. sheet_name은 주요 provenance이며 sheet_index는 표시·순서 보조정보다.

## 13. import_column_mapping

### 목적

원본 Excel 컬럼과 표준 데이터항목의 매핑 이력을 저장.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `mapping_id` | INTEGER | PRIMARY KEY |
| `import_sheet_id` | INTEGER | NOT NULL |
| `source_column_index` | INTEGER | NOT NULL |
| `source_header` | TEXT | NULL |
| `normalized_header` | TEXT | NULL |
| `dictionary_id` | INTEGER | NULL |
| `mapping_status` | TEXT | NOT NULL |
| `mapping_method` | TEXT | NOT NULL |
| `source_unit` | TEXT | NULL |
| `target_unit_id` | INTEGER | NULL |
| `transform_rule` | TEXT | NULL |
| `user_confirmed` | INTEGER | NOT NULL DEFAULT 0 |
| `created_at` | TEXT | NOT NULL |

### PK

`mapping_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK


### 제약조건 상세 및 운영 규칙

#### FK

import_sheet_id → import_sheet.import_sheet_id  
dictionary_id → data_dictionary.dictionary_id  
target_unit_id → unit_dictionary.unit_id  

mapping_status 예:  
MAPPED  
UNMAPPED  
IGNORED  
AMBIGUOUS  

mapping_method 예:  
AUTO_ALIAS  
AUTO_STANDARD_NAME  
USER  
NONE  

#### CHECK

user_confirmed IN (0,1)  

#### UNIQUE

import_sheet_id + source_column_index  

#### 중요

dictionary_id가 NULL인 UNMAPPED 컬럼을 허용한다.  

불확실한 컬럼을 임의 dictionary item에 연결하지 않는다.  


### UNMAPPED 보관 정책

V1에서는 UNMAPPED 컬럼의 모든 셀 값을 별도 raw/staging DB에 복제하지 않는다. source file metadata/hash, import, sheet, source column 위치, source header, normalized header와 mapping_status=UNMAPPED 등 메타데이터를 저장한다.

사용자가 컬럼 의미를 확정하면 원본 Excel을 다시 선택·참조하여 새 mapping으로 재Import한다. 원본 위치가 바뀌었으면 file hash 등으로 동일 파일 여부를 검증할 수 있도록 한다.

characteristic_value와 data_quality_issue를 범용 raw cell 저장소로 사용하지 않는다. raw_cell/staging/unmapped_value 테이블을 V1에 추가하지 않는다. 미매핑 컬럼에 민감 운영정보가 포함될 수 있으므로 원본 셀을 무조건 DB에 복제하지 않는다.

### 진행 중 Import 작업 저장: V1 로컬 workspace

V1은 Excel 가져오기 → Sheet/Header 선택 → 컬럼 매핑 후 프로그램을 종료해도 재실행·로그인 후 이어서 작업할 수 있도록 한다. 임시 선택 상태는 연구 DB 밖의 application data/workspace 아래 로컬 파일(JSON 등)에 저장한다. 경로 예시는 `workspace/import_draft_xxx.json`이며 실제 파일명 계약은 구현 단계에서 정한다. 연구 DB는 19개 테이블을 유지하며 Draft 테이블을 추가하지 않는다.

저장 후보는 사용자 ID, 원본 Excel 경로·hash, 선택 Sheet, Header 시작/종료 행, Data 시작 행, 컬럼 매핑 상태, 현재 작업 단계, 마지막 저장 시각이다. 행·컬럼은 1-based, 시스템 저장 시각은 UTC를 따른다. 원본 전체 셀·민감값·비밀번호·인증정보는 복제하지 않는다.

재개 시 원본 파일 존재와 hash 일치를 확인한다. 파일 이동·부재 또는 hash 불일치 시 자동 대체하지 않고 사용자에게 원본 파일 재지정을 요구한다. 재지정 파일도 검증하며 내용이 바뀐 파일에 이전 매핑을 자동 확정하지 않는다. 사전·매핑 유효성은 재개 시 다시 검증한다.

source_file은 원본 메타데이터, workspace는 미완료 작업, import_history는 실제 DB Import 실행 이력이다. Preview/매핑/Draft 저장은 import_history를 생성하지 않는다. workspace의 사용자 ID는 DB FK가 아니므로 Service가 현재 DB·로그인 사용자와의 소유 관계를 확인한다. DB 복원 후 같은 숫자 사용자 ID를 동일인으로 단정하지 않는다.

파일 형식 버전·원자적 저장·손상 대응·사용자별 접근·보존 기간·Import 성공 후 정리·비활성 계정 및 DB 복원 시 재연결 계약은 Phase 5 전 TODO다. 정리는 원본 Excel이나 Export 파일 자동 삭제를 뜻하지 않는다.

## 14. small_stream

### 목적

소하천의 기준 엔티티.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `stream_code` | TEXT | PRIMARY KEY NOT NULL |
| `province_code` | TEXT | NOT NULL |
| `city_county_code` | TEXT | NOT NULL |
| `town_code` | TEXT | NOT NULL |
| `stream_serial_no` | TEXT | NOT NULL |
| `stream_name` | TEXT | NOT NULL |
| `province_name` | TEXT | NULL |
| `city_county_name` | TEXT | NULL |
| `town_name` | TEXT | NULL |
| `river_system` | TEXT | NULL |
| `source_address` | TEXT | NULL |
| `source_latitude` | REAL | NULL |
| `source_longitude` | REAL | NULL |
| `end_address` | TEXT | NULL |
| `end_latitude` | REAL | NULL |
| `end_longitude` | REAL | NULL |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`stream_code` (TEXT PRIMARY KEY NOT NULL). SQLite 일반 rowid 테이블의 TEXT PK는 암묵적으로 NOT NULL이 되지 않으므로 명시한다.

### FK 및 UNIQUE/CHECK

- FK: 별도 지정 없음.
- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### CHECK

length(stream_code) = 11; stream_code NOT GLOB '*[^0-9]*'  
length(province_code) = 2  
length(city_county_code) = 3  
length(town_code) = 3  
length(stream_serial_no) = 3  
is_active IN (0,1)  

#### 중요

stream_code 및 구성요소는 TEXT다.  

프로그램 QC에서:  

province_code  
|| city_county_code  
|| town_code  
|| stream_serial_no  
=  
stream_code  

인지 검사한다.  

구성요소와 전체 코드의 실제 연결 일치는 Service validation 책임이며 DB 연결 CHECK는 추가하지 않는다. 오류를 자동 보정하지 않는다.

전체 코드의 기본 형식은 다음 CHECK로 보호한다. 구성요소는 위 길이와 TEXT/NOT NULL을 유지하며 Service가 숫자 구성과 연결 일치를 검증한다.

```sql
CHECK (typeof(stream_code) = 'text'
       AND length(stream_code) = 11
       AND stream_code NOT GLOB '*[^0-9]*'
       AND instr(stream_code, char(0)) = 0)
```

source_latitude/end_latitude는 값이 있으면 -90~90, source_longitude/end_longitude는 -180~180으로 기본 형식을 검사한다. 기존 NULL 허용을 유지한다.

```sql
CHECK (source_latitude IS NULL OR source_latitude BETWEEN -90 AND 90)
CHECK (end_latitude IS NULL OR end_latitude BETWEEN -90 AND 90)
CHECK (source_longitude IS NULL OR source_longitude BETWEEN -180 AND 180)
CHECK (end_longitude IS NULL OR end_longitude BETWEEN -180 AND 180)
```

각 행은 독립된 테이블 CHECK 절이며 DDL 작성 시 쉼표로 구분한다. 이는 위경도 형식 유효성이고 연구 QC 임계값이나 좌표계 추정 근거가 아니다. 미확인 투영좌표를 위경도로 간주하거나 자동 변환하지 않는다.  

소하천명을 JOIN KEY로 사용하지 않는다.  

## 15. stream_relation

### 목적

본류/지류 등 소하천 간 관계를 고정 컬럼이 아닌 관계형 구조로 관리.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `relation_id` | INTEGER | PRIMARY KEY |
| `stream_code` | TEXT | NOT NULL |
| `related_stream_code` | TEXT | NULL |
| `relation_type` | TEXT | NOT NULL |
| `relation_order` | INTEGER | NULL |
| `related_stream_name_raw` | TEXT | NULL |
| `source_import_id` | INTEGER | NULL |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`relation_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### FK

stream_code → small_stream.stream_code  
related_stream_code → small_stream.stream_code  
source_import_id → import_history.import_id  

relation_type 예:  
MAIN  
TRIBUTARY  

#### CHECK

is_active IN (0,1)  

#### 설명

원본 자료에 관련 하천명이 존재하지만 해당 related stream의  
관리코드를 확정할 수 없는 경우를 고려하여  
related_stream_code는 NULL을 허용하고  
related_stream_name_raw에 원본명을 보존할 수 있다.  

관계를 이름만으로 자동 확정하지 않는다.  

## 16. characteristic_value

### 목적

소하천 특성정보의 authoritative source of truth.

하나의 소하천/항목에 여러 출처의 값이 존재할 수 있으며
원본 및 대표값 선택 이력을 보존한다.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `characteristic_value_id` | INTEGER | PRIMARY KEY |
| `stream_code` | TEXT | NOT NULL |
| `dictionary_id` | INTEGER | NOT NULL |
| `value_number` | REAL | NULL |
| `value_integer` | INTEGER | NULL |
| `value_text` | TEXT | NULL |
| `value_date` | TEXT | NULL |
| `unit_id` | INTEGER | NULL |
| `original_value` | TEXT | NULL |
| `original_unit` | TEXT | NULL |
| `import_id` | INTEGER | NULL |
| `import_sheet_id` | INTEGER | NULL |
| `source_row` | INTEGER | NULL |
| `mapping_id` | INTEGER | NULL |
| `source_type` | TEXT | NOT NULL DEFAULT 'IMPORT' |
| `source_reference` | TEXT | NULL |
| `reference_year` | INTEGER | NULL |
| `is_representative` | INTEGER | NOT NULL DEFAULT 0 |
| `quality_status` | TEXT | NOT NULL DEFAULT 'UNREVIEWED' |
| `is_active` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`characteristic_value_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### FK

stream_code → small_stream.stream_code  
dictionary_id → data_dictionary.dictionary_id  
unit_id → unit_dictionary.unit_id  
import_id → import_history.import_id  
import_sheet_id → import_sheet.import_sheet_id  
mapping_id → import_column_mapping.mapping_id  

#### CHECK

is_representative IN (0,1)  
is_active IN (0,1)  

source_type 예:  
IMPORT  
USER_CORRECTION  
MANUAL  
DERIVED  

#### 중요

일반 Import 값이면 import provenance를 사용한다.  

사용자 보정 등 Import가 아닌 값은  
source_type/source_reference를 통해 구분한다.  

source_file_id를 중복 저장하지 않는다.  
파일은 import 관계를 통해 추적한다.  

#### typed value 규칙

value_number, value_integer, value_text, value_date 중 **정확히 하나만 NON-NULL**이어야 한다. characteristic_value는 실제 유효한 값을 저장한다. SQLite CHECK 표현은 DATABASE_DESIGN.md의 제약 감사에서 확인했다. 실제 DDL 실행 검증은 Phase 1에서 수행한다.

결측이면 NULL value를 가진 characteristic_value 행을 생성하지 않는 것을 원칙으로 한다. 필수값 결측은 validation/QC issue로 처리한다. data_dictionary.nullable은 해당 항목의 결측 허용 여부이며 NULL characteristic_value 행 생성 허가를 뜻하지 않는다.

Service/Validator는 data_dictionary.data_type과 typed value 컬럼의 일치를 검증한다. DATE와 DATETIME 모두 V1에서는 value_date TEXT를 사용하며 Validator가 구분한다. DATE는 YYYY-MM-DD, DATETIME은 ISO 8601 형식이다. 원본 DATETIME에 timezone이 없으면 임의로 추가하지 않는다. 별도 value_datetime 컬럼은 추가하지 않는다.

Import 출처는 source_file → import_history → import_sheet → import_column_mapping → 원본 source column으로 추적한다.

characteristic_value는 **mapping_id와 source_row**를 함께 사용하여 원본 Excel의 행·열 출처를 식별한다. mapping_id는 import_column_mapping.mapping_id를 참조한다. Import 값은 가능한 한 mapping_id를 저장한다. USER_CORRECTION / MANUAL / DERIVED 등 원본 Excel column mapping이 없는 값은 NULL을 허용한다.

characteristic_value에 source_file_id나 source_column을 중복 저장하지 않는다. Service는 mapping_id가 가리키는 import_sheet와 characteristic_value.import_sheet_id가 일치하고, mapping이 속한 import와 characteristic_value.import_id가 일치하는지 검증한다. import_id와 import_sheet_id가 함께 있으면 같은 Import 소속인지도 검증한다. 과도한 DB trigger는 사용하지 않는다.

DB provenance의 source_row, source_column_index, source_column 등 Excel 사용자 위치는 원칙적으로 **1-based**를 사용한다. Python/openpyxl/pandas 등 처리 도구의 내부 index 기준을 확인하여 저장 경계에서 명확하게 변환한다. 0-based 내부 index와 혼동하지 않는다. sheet_name을 주요 provenance로 사용하고 sheet_index는 표시·순서 보조정보로 구분한다.

#### 대표값

동일 stream_code + dictionary_id 조합에 대해  
활성 representative가 최대 하나만 존재하도록 한다.  

SQLite partial unique index로 아래 제약을 보장한다(실행하지 않은 DDL 명세):

```sql
CREATE UNIQUE INDEX ux_characteristic_value_active_representative
ON characteristic_value(stream_code, dictionary_id)
WHERE is_representative = 1 AND is_active = 1;
```

이 인덱스는 활성 현재 사용값을 최대 하나로 제한하며, 현재값이 반드시 하나 존재하도록 강제하지 않는다. 비활성 값을 현재값으로 사용하지 않는 것은 Service에서 추가 검증한다. 이전 선택 해제 → 새 선택 → 이력 → 캐시 갱신을 한 transaction으로 수행한다.  

#### 중요

QC/parse 실패로 유효값을 만들 수 없는 자료를  
억지로 characteristic_value에 정상값처럼 저장하지 않는다.  
필요한 문제는 data_quality_issue에서 관리한다.

UI의 **현재 사용값**은 기존 is_representative로 선택한 값이다. characteristic_value는 원본값과 새로 추가한 보정값을 보존하고, record_history는 보정·선택 변경을 기록하며, stream_characteristic은 현재 사용값의 ID를 보관하고 실제 값은 characteristic_value에서 조회하는 참조 캐시다. 별도 현재값 테이블을 만들지 않는다.

동일 stream_code + dictionary_id에 활성 현재 사용값은 최대 하나다. 새 자료 Import만으로 현재 사용값을 변경하지 않으며 사용자가 명시적으로 선택한다. 선택할 characteristic_value_id에 severity='ERROR' AND is_active=1인 issue가 있으면 지정할 수 없다. 활성 WARNING/INFO는 연구자가 확인한 뒤 명시적으로 지정할 수 있다. review_status 변경만으로 ERROR 차단을 해제하지 않는다. 기존 값을 삭제·덮어쓰지 않고 characteristic_value.is_representative 변경·stream_characteristic 참조 캐시 갱신·record_history 기록을 하나의 업무 transaction으로 처리한다. 어느 단계든 실패하면 전부 rollback하며 자동 선정은 금지한다.

동일 stream_code가 다른 Import에 이미 존재하는 것만으로 중복 오류를 확정하지 않는다. small_stream은 소하천 엔티티이고 characteristic_value는 여러 출처·시점·보정 값을 담는다.

## 17. stream_characteristic

### 목적

현재 사용되는 characteristic_value를 빠르게 찾는 rebuildable current-value cache/index다. authoritative value 저장소가 아니며 연구 특성별 고정 core 컬럼과 실제 값의 복제를 두지 않는다.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `stream_code` | TEXT | NOT NULL; 복합 PK 구성 |
| `dictionary_id` | INTEGER | NOT NULL; 복합 PK 구성 |
| `characteristic_value_id` | INTEGER | NOT NULL |
| `updated_at` | TEXT | NOT NULL; Service가 UTC ISO 8601 입력, 기본값 없음 |

### PK / FK / UNIQUE

- PRIMARY KEY (stream_code, dictionary_id): 하천·항목별 현재 값 참조는 최대 하나다. 두 컬럼에 NOT NULL을 명시한다.
- stream_code → small_stream.stream_code
- dictionary_id → data_dictionary.dictionary_id
- characteristic_value_id → characteristic_value.characteristic_value_id
- 세 FK는 ON DELETE RESTRICT / ON UPDATE NO ACTION이다. 원본 값을 삭제하며 캐시를 CASCADE 삭제하는 정책은 사용하지 않는다.
- 복합 PK와 같은 UNIQUE/일반 index를 중복 생성하지 않는다. characteristic_value_id와 dictionary_id 검색용 일반 index는 조회 계획에 따라 검토한다.
- created_at과 is_active는 추가하지 않는다. 현재값이 없는 조합은 캐시 행도 없으며 값의 활성 상태는 authoritative 행에서 확인한다.

### 운영·무결성

값은 캐시의 characteristic_value_id로 characteristic_value를 JOIN해서 조회한다. Service는 참조 값의 stream_code·dictionary_id가 캐시 키와 일치하고 is_active=1 AND is_representative=1인지 검증한다. 세 단일 FK는 존재만 보장하므로 이 교차 일치 조건을 FK 자체가 보장한다고 가정하지 않는다. 추가 복합 FK용 원본 UNIQUE나 trigger를 임의 도입하지 않는다.

현재 사용값 변경 Service는 기존 선택 해제 → 새 선택 → 캐시 갱신 → record_history를 한 transaction으로 처리한다. 직접 편집 UI는 제공하지 않는다. 활성 현재값이 없어진 조합의 캐시 제거는 파생 인덱스 정리이며 연구 원본 삭제가 아니다. 선택 없이 캐시를 만들거나 캐시 기준으로 원본을 덮어쓰지 않는다.

characteristic_value의 활성 is_representative 상태에서 언제든 전체/대상 범위를 재구축할 수 있다. DB 복원 후에도 참조·키·선택 상태를 재검증한다. **C1은 확정·해소되었으며 실제 연구 헤더 확인은 이 캐시 DDL의 선행 조건이 아니다.**

## 18. quality_rule

### 목적

QC 규칙 정의.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `rule_id` | INTEGER | PRIMARY KEY |
| `rule_code` | TEXT | NOT NULL UNIQUE |
| `rule_name` | TEXT | NOT NULL |
| `target_type` | TEXT | NOT NULL |
| `dictionary_id` | INTEGER | NULL |
| `rule_type` | TEXT | NOT NULL |
| `default_severity` | TEXT | NOT NULL |
| `parameters_json` | TEXT | NULL |
| `description` | TEXT | NULL |
| `rule_version` | TEXT | NOT NULL DEFAULT '1.0' |
| `is_enabled` | INTEGER | NOT NULL DEFAULT 1 |
| `created_at` | TEXT | NOT NULL |
| `updated_at` | TEXT | NOT NULL |

### PK

`rule_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### FK

dictionary_id → data_dictionary.dictionary_id  

#### CHECK

default_severity IN ('ERROR','WARNING','INFO')  
is_enabled IN (0,1)  

#### 규칙

QC 로직 자체의 구현 버전과 DB에 저장된 rule 정의가  
추적 가능하도록 rule_version을 사용한다.  

## 19. data_quality_issue

### 목적

Import/DB/QC 과정에서 발견된 개별 데이터 문제를 기록.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `issue_id` | INTEGER | PRIMARY KEY |
| `characteristic_value_id` | INTEGER | NULL; FK characteristic_value.characteristic_value_id |
| `is_active` | INTEGER | NOT NULL DEFAULT 1; CHECK(is_active IN (0,1)) |
| `rule_id` | INTEGER | NULL |
| `rule_version_snapshot` | TEXT | NULL |
| `rule_parameters_snapshot_json` | TEXT | NULL |
| `import_id` | INTEGER | NULL |
| `import_sheet_id` | INTEGER | NULL |
| `stream_code` | TEXT | NULL |
| `dictionary_id` | INTEGER | NULL |
| `source_row` | INTEGER | NULL |
| `source_column` | INTEGER | NULL |
| `issue_type` | TEXT | NOT NULL |
| `severity` | TEXT | NOT NULL |
| `original_value` | TEXT | NULL |
| `compare_value` | TEXT | NULL |
| `message` | TEXT | NOT NULL |
| `review_status` | TEXT | NOT NULL DEFAULT 'UNREVIEWED' |
| `review_result` | TEXT | NULL |
| `review_note` | TEXT | NULL |
| `reviewed_at` | TEXT | NULL |
| `reviewed_by_user_id` | INTEGER | NULL; FK app_user.user_id, ON DELETE RESTRICT |
| `created_at` | TEXT | NOT NULL |

### PK

`issue_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.

### 제약조건 상세 및 운영 규칙

#### FK

characteristic_value_id → characteristic_value.characteristic_value_id  
rule_id → quality_rule.rule_id  
import_id → import_history.import_id  
import_sheet_id → import_sheet.import_sheet_id  
stream_code → small_stream.stream_code  
dictionary_id → data_dictionary.dictionary_id  

#### CHECK

severity IN ('ERROR','WARNING','INFO')  

#### CHECK

review_status IN (  
'UNREVIEWED',  
'IN_REVIEW',  
'CONFIRMED',  
'CORRECTED',  
'DEFERRED'  
)  

#### 중요

stream_code 자체가 잘못되어 small_stream에 존재하지 않는 오류도  
기록할 수 있어야 하므로 stream_code는 NULL을 허용한다.  

원본 잘못된 관리코드는 original_value/message 등에 보존할 수 있다.  

QC issue는 수정 완료 후 삭제하지 않는다.  
CORRECTED 등의 상태로 이력을 남긴다.  


### 현재·과거 issue와 특정 값 연결

characteristic_value_id는 특정 authoritative value 대상 issue에 연결한다. 관리코드 형식 오류·Import 단계 문제·아직 값이 없는 issue는 NULL일 수 있다. ON DELETE RESTRICT / ON UPDATE NO ACTION으로 원본 참조를 보존한다. 값 ID를 연결한 경우 Service는 함께 기록한 stream_code·dictionary_id·출처가 해당 값과 모순되지 않는지 검증한다.

is_active=1은 현재 QC 판정 대상, 0은 과거 보존이다. 재검사에서 더 이상 현재 문제가 아닌 기존 issue는 물리 삭제 없이 is_active=0으로 바꾸고, 새 문제는 새 issue 행으로 추가한다. severity·rule snapshot을 새 결과로 덮어쓰지 않는다. review_status와 활성 여부는 독립적이므로 WARNING+CONFIRMED+active, ERROR+CORRECTED+inactive가 가능하다. 검토 상태 변경만으로 is_active를 자동 변경하지 않는다.

재검사가 성공한 대상 범위에서만 기존 활성 상태 변경과 새 issue 저장을 한 transaction으로 처리한다. 중단·실패한 검사를 근거로 기존 issue를 일괄 비활성화하지 않는다. 세부 재검사 범위·같은 문제의 반복 탐지 계약은 Phase 7에서 정하며 DB 초기 구현을 차단하지 않는다.

### 규칙 snapshot 및 검토 이력

data_quality_issue의 rule_version_snapshot TEXT NULL과 rule_parameters_snapshot_json TEXT NULL에 issue 생성 당시 quality_rule.rule_version과 parameters_json을 snapshot으로 보존한다. rule_parameters_snapshot_json은 JSON 형식 TEXT다.

rule_id는 계속 quality_rule의 FK로 유지한다. snapshot은 issue 생성 당시의 재현성 정보이며 현재 quality_rule 값을 대신하는 live reference가 아니다. 규칙이 변경되어도 과거 결과의 규칙 버전과 parameter를 확인할 수 있어야 한다.

V1에서는 별도 QC review history 테이블을 추가하지 않는다. data_quality_issue는 현재 review_status와 검토 정보를, record_history는 상태 변경·사용자 보정·대표값 변경 등 중요 변경 이력을 관리한다.

QC issue를 삭제하지 않는다. 재검사에서 새로운 issue가 생성될 수 있으며 과거 issue는 기존 review 상태와 record_history를 함께 보존한다. issue 간 lineage 전용 FK는 V1에 추가하지 않으며 실제 사용에서 필요성이 확인되면 향후 확장한다.

### 화면 상태와 DB 상태

자동 QC 화면 상태는 data_quality_issue.is_active=1인 issue만 집계한다. 활성 issue가 없으면 ‘정상’, 활성 ERROR는 없고 INFO/WARNING만 있으면 ‘확인 필요’, 활성 ERROR가 하나 이상이면 ‘오류’다. INFO는 정상 severity가 아니다. review_status는 사람의 검토 상태로 별도 유지하며 활성 여부와 혼합하지 않는다. 활성 issue가 없다는 집계는 검사 실행 완료를 증명하지 않으므로 실행 여부 안내와 구분한다.

| DB review_status | UI 표시 |
| --- | --- |
| UNREVIEWED | 미검토 |
| IN_REVIEW | 검토 중 |
| CONFIRMED | 확인 완료 |
| CORRECTED | 보정 완료 |
| DEFERRED | 보류 |

CONFIRMED는 원본 오류 확정이 아닌 연구자 확인이다. 검토 시 reviewed_by_user_id와 reviewed_at(UTC)을 기록하고 상태 변경은 record_history로 보존한다. QC 화면은 원본을 직접 덮어쓰지 않으며 특성정보 보정 관리로 연결한다. Import SUCCESS와 QC 확인 필요는 동시에 가능하다.

## 20. record_history

### 목적

사용자가 검토 후 수행한 주요 데이터 변경 이력.

### 컬럼

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `history_id` | INTEGER | PRIMARY KEY |
| `issue_id` | INTEGER | NULL |
| `import_id` | INTEGER | NULL |
| `table_name` | TEXT | NOT NULL |
| `record_key` | TEXT | NOT NULL |
| `column_name` | TEXT | NULL |
| `old_value` | TEXT | NULL |
| `new_value` | TEXT | NULL |
| `change_type` | TEXT | NOT NULL |
| `reason` | TEXT | NULL |
| `changed_by` | TEXT | NULL |
| `actor_user_id` | INTEGER | NULL; FK app_user.user_id, ON DELETE RESTRICT |
| `changed_at` | TEXT | NOT NULL |

### PK

`history_id` (INTEGER PRIMARY KEY). INTEGER 키에는 불필요한 AUTOINCREMENT를 사용하지 않는다.

### FK 및 UNIQUE/CHECK

- UNIQUE: 컬럼 표에 명시된 UNIQUE 외 별도 지정 없음. 부분 유일성 검토 사항은 아래에 구분한다.
- CHECK: 별도 명시된 확정 조건 없음. 검토 사항은 아래 규칙을 따른다.

### 제약조건 상세 및 운영 규칙

#### FK

issue_id → data_quality_issue.issue_id  
import_id → import_history.import_id  

change_type 업무 표현:  
IMPORT / QC_REVIEW / CORRECTION / CURRENT_VALUE_CHANGE / DEACTIVATE / RESTORE / BACKUP / DB_RESTORE

기존 INSERT/UPDATE/REPRESENTATIVE_CHANGE/USER_CORRECTION은 중요 변경의 과거 예시다. 용어 대응과 action별 기록 계약은 29.6절을 따른다.  

#### 중요

generic history이므로 target record에 직접 FK를 걸기 어렵다.  
무결성은 Service 계층에서 관리한다.  

changed_by는 기존 작업자 텍스트로 유지한다. 새 작업의 기준 작업자는 actor_user_id이며 이력의 사용자 FK와 역할은 아래 로컬 계정 설계를 따른다.  


### QC 검토·재검사 이력

V1에서는 별도 QC review history 테이블을 추가하지 않는다. data_quality_issue는 현재 review_status와 검토 정보를, record_history는 상태 변경·사용자 보정·대표값 변경 등 중요 변경 이력을 관리한다.

QC issue를 삭제하지 않는다. 재검사에서 새로운 issue가 생성될 수 있으며 과거 issue는 기존 review 상태와 record_history를 함께 보존한다. issue 간 lineage 전용 FK는 V1에 추가하지 않으며 실제 사용에서 필요성이 확인되면 향후 확장한다.

### 작업이력의 책임

record_history는 중요한 연구·운영 변경을 기록한다: Import, QC 검토, 특성정보 보정, 현재 사용값 변경, 비활성화·데이터 복원, DB 백업·DB 복원 및 기타 중요한 연구 데이터 변경. 검색·정렬·페이지 이동·일반 조회·단순 필터·그래프 유형 변경은 기록하지 않는다. 사용자에게 이력 수정·삭제 기능을 제공하지 않는다.

홈·마이페이지와 작업이력은 record_history를 공유하고 actor_user_id로 현재 app_user.display_name을 조회한다. V1 사용자명 snapshot 필드는 추가하지 않는다. DB Restore 전에 자동 안전백업을 만들고, 성공 후 새 현재 DB의 record_history에 복원 작업을 기록한다. 데이터 비활성화 복원은 RESTORE, DB 전체 복원은 DB_RESTORE로 구분한다. Backup/Restore 기술과 이벤트 대상 표현·복원된 DB의 작업자 연결은 Phase 14 전에 확정한다. 원래 DB의 최신 이력이 복원 DB에 자동 합쳐진다고 가정하지 않는다.

## 20A. app_user: 로컬 앱 계정

### 목적과 저장 경계

V1은 개인 PC의 로컬 계정으로 현재 작업자를 식별한다. 서버·팀 협업·동시편집·온라인 회원가입·이메일/휴대폰 복구·복잡한 권한 관리는 포함하지 않는다. 사용자가 없으면 최초 사용자 등록 화면으로 연결한다. app_user의 비밀번호는 평문으로 저장하지 않으며 자체 암호화·비밀번호 알고리즘을 만들지 않는다. 검증된 password hashing library를 사용하며 세부 library·알고리즘은 Phase 1A 인증 구현 직전에 확정한다. 이 선택은 Phase 0 또는 DB 컬럼 정의 자체의 차단 사유가 아니다.

로컬 앱 계정은 연구자료에서 가져온 운영 인증정보와 구분한다. app_user는 애플리케이션 인증·작업자 메타데이터이며 연구항목·일반 Export·QC 원본값·로그 대상이 아니다. 연구 Excel의 서비스 Key·비밀번호·IP·CCTV·RTSP·개인 연락처는 기존대로 연구 DB Import에서 제외한다. 계정 비활성화는 과거 이력을 지우지 않는다.

기존 SQLite의 애플리케이션 전용 테이블로 설계하여 아래 실제 FK를 유지하는 방향이다. 연구 데이터 조회·통계·일반 Export에서는 제외한다. 이는 비밀번호 hash를 보호하는 설계이며 DB 파일 전체 암호화나 OS 접근 통제를 제공한다고 가정하지 않는다.

### 컬럼과 확정 범위

app_user는 V1 정식 테이블이다. 목적상 필요한 PK·로그인 유일성·필수 계정 정보와 기존 시스템 시각·Boolean 표현을 아래처럼 정리한다. login_id의 문자·길이는 아래 확정 정책을 적용하며 복잡한 role 권한·임의 role 기본값은 추가하지 않는다.

| 컬럼 | SQLite 자료형 | NULL·기본값·키 선언 |
| --- | --- | --- |
| `user_id` | INTEGER | PRIMARY KEY |
| `login_id` | TEXT | NOT NULL UNIQUE; 정규화 소문자 ASCII, 길이 4~50 CHECK |
| `password_hash` | TEXT | NOT NULL; 평문 금지, 기본값 없음 |
| `display_name` | TEXT | NOT NULL; 기본값 없음 |
| `department` | TEXT | NULL; 기본값 없음 |
| `role` | TEXT | NULL; 기본값·허용값 CHECK 없음, V1 RBAC 용도 아님 |
| `is_active` | INTEGER | NOT NULL DEFAULT 1; CHECK(is_active IN (0,1)) |
| `created_at` | TEXT | NOT NULL; Service가 UTC 입력 |
| `updated_at` | TEXT | NOT NULL; Service가 UTC 입력 |
| `last_login_at` | TEXT | NULL; 최초 성공 로그인 전 NULL |

FK는 없다. login_id UNIQUE가 만드는 인덱스를 중복 생성하지 않는다. department/role은 필수 목적 정보가 아니므로 선택값으로 두고, role을 근거로 서버 권한 체계를 만들지 않는다. 계정은 물리 삭제하지 않고 is_active=0으로 비활성화한다. 자체 hashing 구현·평문 임시 저장·로그 출력은 금지한다.

**U1 확정:** V1 login_id는 Service에서 앞뒤 공백 제거 → 소문자 정규화 → 허용 문자·길이 검증 후 저장한다. 영문자·숫자·점(.)·밑줄(_)·하이픈(-)만 허용하고 내부 공백은 거부한다. 정규화된 길이는 4~50자이며 대소문자만 다른 ID는 동일 계정이다. login_id는 NOT NULL UNIQUE이고 별도 정규화 컬럼은 없다. 이 제한은 display_name·department에 적용하지 않는다.

등록·로그인 조회에 같은 정규화 절차를 적용한다. Researcher01 / researcher01 / RESEARCHER01은 모두 researcher01이다. 저장 값이 소문자 ASCII로 제한되므로 기본 BINARY 비교의 UNIQUE로 동일성을 보장할 수 있다. display_name과 department의 한국어 등을 login_id 규칙으로 거부하지 않는다.

다음 CHECK는 정규화된 저장 표현을 보호한다(실행하지 않은 SQL 명세). 소문자 변환 자체는 Service 책임이다.

```sql
CHECK (
  typeof(login_id) = 'text'
  AND length(login_id) BETWEEN 4 AND 50
  AND login_id NOT GLOB '*[^a-z0-9._-]*'
  AND instr(login_id, char(0)) = 0
)
```

하이픈은 문자 집합 끝의 리터럴이다. GLOB는 정규식이 아니므로 단순 '[0-9]*'를 숫자로만 이루어진 문자열 검사로 사용하지 않는다. NUL 등 제어문자는 허용 문자에 없으며 Service에서도 거부한다.

### 기존 테이블 연결과 보존 정책

작업자 연결은 import_history.created_by_user_id, data_quality_issue.reviewed_by_user_id, record_history.actor_user_id에서만 추가하며 모두 app_user.user_id를 참조한다. 세 FK는 NULL을 허용한다(미검토 QC, 기존/작업자 미상 기록 등). 다만 새 로그인 사용자의 Import 실행·QC 검토·중요 변경은 Service가 해당 사용자 ID를 반드시 기록하며 임의 NULL로 누락하지 않는다.

세 사용자 FK의 ON DELETE는 RESTRICT로 설계한다. 계정은 물리 삭제 대신 is_active=0으로 비활성화하고 기존 사용자 행·표시정보·FK를 보존한다. CASCADE DELETE나 SET NULL로 과거 작업자를 지우지 않는다. record_history.changed_by는 기존 비구조화 작업자 텍스트로 유지하며 새 작업의 기준 식별자는 actor_user_id다.

최초 사용자 등록, 로그인·로그아웃, 비활성 계정 로그인 거부, 현재 사용자·마이페이지·최근 작업 표시를 지원한다. 과거 record_history는 actor_user_id로 현재 app_user.display_name을 조회하므로 이름 변경이 과거 이력 표시에도 반영된다. 사용자명 snapshot 필드는 V1에 추가하지 않고 서버/다중사용자 확장 때 검토한다. changed_by를 새 이름 snapshot의 대체 필드로 사용하지 않는다. 온라인·이메일·휴대폰 복구는 없다. 비밀번호 분실 시 오프라인 운영 절차와 hashing library·알고리즘은 Phase 1A 전에 정한다.

## 21. provenance 규칙

Import 출처는 source_file → import_history → import_sheet → import_column_mapping → 원본 source column으로 추적한다.

characteristic_value는 **mapping_id와 source_row**를 함께 사용하여 원본 Excel의 행·열 출처를 식별한다. mapping_id는 import_column_mapping.mapping_id를 참조한다. Import 값은 가능한 한 mapping_id를 저장한다. USER_CORRECTION / MANUAL / DERIVED 등 원본 Excel column mapping이 없는 값은 NULL을 허용한다.

characteristic_value에 source_file_id나 source_column을 중복 저장하지 않는다. Service는 mapping_id가 가리키는 import_sheet와 characteristic_value.import_sheet_id가 일치하고, mapping이 속한 import와 characteristic_value.import_id가 일치하는지 검증한다. import_id와 import_sheet_id가 함께 있으면 같은 Import 소속인지도 검증한다. 과도한 DB trigger는 사용하지 않는다.

DB provenance의 source_row, source_column_index, source_column 등 Excel 사용자 위치는 원칙적으로 **1-based**를 사용한다. Python/openpyxl/pandas 등 처리 도구의 내부 index 기준을 확인하여 저장 경계에서 명확하게 변환한다. 0-based 내부 index와 혼동하지 않는다. sheet_name을 주요 provenance로 사용하고 sheet_index는 표시·순서 보조정보로 구분한다.

## 22. 시간/날짜 규칙

프로그램이 자체 생성하는 created_at, updated_at, registered_at, started_at, finished_at, reviewed_at, changed_at, applied_at 등의 시스템 시각은 **UTC 기준 ISO 8601 TEXT**로 저장한다. 권장 표현은 YYYY-MM-DDTHH:MM:SSZ다. 필요하면 fractional seconds를 사용할 수 있으나 프로젝트 전체 표현을 일관되게 유지한다. UI에서는 사용자 로컬 timezone으로 변환하여 표시할 수 있다.

원본 연구자료의 날짜/시간은 시스템 시각과 구분한다. 원본에 timezone 정보가 없으면 KST/UTC 등을 임의로 부여하지 않고 original_value를 보존한다. 원본 timezone을 알 수 있으면 해당 데이터 유형의 명시적 규칙에 따라 처리한다. V3 계측 시계열 구현 전 관측자료 timezone 정책을 별도로 상세화한다.

## 23. 삭제/FK 정책

아래는 각 테이블에 이미 선언한 모든 FK의 감사 목록이다. 원본·출처·사전·작업자 참조 보존 원칙에 따라 **모든 행의 ON DELETE RESTRICT / ON UPDATE NO ACTION**을 명시한다. 부모 PK를 직접 변경하는 업무는 없다. 자동 CASCADE UPDATE로 관리코드를 바꾸지 않는다. 부모 비활성화는 행 삭제가 아니며 FK가 유지된다. NULL 허용은 ‘처음부터 해당 참조가 없음’을 뜻하며 부모 삭제 때 SET NULL로 이력을 지우라는 뜻이 아니다.

| 자식 테이블 | FK 컬럼 → 부모 PK | NULL |
| --- | --- | --- |
| data_category | parent_category_id → data_category.category_id | 허용 |
| unit_conversion | from_unit_id, to_unit_id → unit_dictionary.unit_id | 둘 다 금지 |
| data_dictionary | category_id → data_category.category_id | 금지 |
| data_dictionary | unit_id → unit_dictionary.unit_id | 허용 |
| data_dictionary | created_version_id / deprecated_version_id → dictionary_version.version_id | 금지 / 허용 |
| column_alias | dictionary_id → data_dictionary.dictionary_id | 금지 |
| import_history | source_file_id → source_file.source_file_id | 금지 |
| import_history | dictionary_version_id → dictionary_version.version_id | 허용 |
| import_history | schema_version_id → schema_version.schema_version_id | 허용 |
| import_history | created_by_user_id → app_user.user_id | 허용 |
| import_sheet | import_id → import_history.import_id | 금지 |
| import_column_mapping | import_sheet_id → import_sheet.import_sheet_id | 금지 |
| import_column_mapping | dictionary_id → data_dictionary.dictionary_id | 허용 |
| import_column_mapping | target_unit_id → unit_dictionary.unit_id | 허용 |
| stream_relation | stream_code / related_stream_code → small_stream.stream_code | 금지 / 허용 |
| stream_relation | source_import_id → import_history.import_id | 허용 |
| characteristic_value | stream_code → small_stream.stream_code | 금지 |
| characteristic_value | dictionary_id → data_dictionary.dictionary_id | 금지 |
| characteristic_value | unit_id → unit_dictionary.unit_id | 허용 |
| characteristic_value | import_id → import_history.import_id | 허용 |
| characteristic_value | import_sheet_id → import_sheet.import_sheet_id | 허용 |
| characteristic_value | mapping_id → import_column_mapping.mapping_id | 허용 |
| stream_characteristic | stream_code → small_stream.stream_code | 금지 |
| stream_characteristic | dictionary_id → data_dictionary.dictionary_id | 금지 |
| stream_characteristic | characteristic_value_id → characteristic_value.characteristic_value_id | 금지 |
| quality_rule | dictionary_id → data_dictionary.dictionary_id | 허용 |
| data_quality_issue | characteristic_value_id → characteristic_value.characteristic_value_id | 허용 |
| data_quality_issue | rule_id → quality_rule.rule_id | 허용 |
| data_quality_issue | import_id → import_history.import_id | 허용 |
| data_quality_issue | import_sheet_id → import_sheet.import_sheet_id | 허용 |
| data_quality_issue | stream_code → small_stream.stream_code | 허용 |
| data_quality_issue | dictionary_id → data_dictionary.dictionary_id | 허용 |
| data_quality_issue | reviewed_by_user_id → app_user.user_id | 허용 |
| record_history | issue_id → data_quality_issue.issue_id | 허용 |
| record_history | import_id → import_history.import_id | 허용 |
| record_history | actor_user_id → app_user.user_id | 허용 |

위 표의 복수 컬럼은 각각 독립적인 단일 FK다. 총 39개 FK이며 모든 부모 키는 해당 테이블 PK로 정의되어 있다. schema_version, dictionary_version, unit_dictionary, source_file, small_stream, app_user 자체에는 FK가 없다. table_name/record_key는 generic history 대상 식별이므로 실제 FK로 가장하지 않고 Service가 검증한다.

캐시는 재구축 가능하지만 부모 하천의 물리 삭제를 허용할 필요가 없으므로 여기에도 RESTRICT를 적용한다. 캐시 재빌드는 자식 캐시를 재작성하는 작업으로 부모 삭제 정책과 다르다. 연구 이력 테이블에는 CASCADE/SET NULL을 사용하지 않는다. 실패 transaction의 rollback은 완료 자료의 DELETE가 아니므로 이 정책과 충돌하지 않는다.

잘못된 관리코드는 data_quality_issue.stream_code=NULL로 저장하고 민감정보를 제외한 original_value 등에 남긴다. FK를 비활성화하거나 존재하지 않는 코드를 FK 컬럼에 넣지 않는다. SQL FK만으로 mapping·sheet·import의 공통 소속이나 같은 숫자 사용자 ID의 DB 간 동일인 여부는 보장하지 못한다.

## 24. Index 전략

최소 검토 대상:  

small_stream:  
- province_name
- city_county_name
- stream_name

characteristic_value:  
- stream_code
- dictionary_id
- (stream_code, dictionary_id)
- import_id
- import_sheet_id
- representative partial unique index

import_history:  
- source_file_id
- status

import_sheet:  
- import_id

import_column_mapping:  
- import_sheet_id
- dictionary_id

stream_characteristic:
- dictionary_id
- characteristic_value_id

data_quality_issue:  
- (characteristic_value_id, is_active, severity): 값별 현재값 지정 차단 조회
- review_status
- severity
- stream_code
- import_id
- (stream_code, dictionary_id)

record_history:  
- record_key
- issue_id
- changed_at

위 목록은 검토 후보이며 최종 감사의 중복 제거·FK 인덱스 보완 기준은 29.1절을 따른다. PK/UNIQUE와 동일한 일반 인덱스를 중복 생성하지 않는다.  

## 25. V1 이후 확장 테이블

아래는 V1 이후의 미래 설계 영역이며 V1 테이블 수에 포함하지 않는다. 현재 생성하지 않는다.  

계측:  
measurement_station  
measurement_sensor (필요성 확인 후)  
aws_station  
stream_aws_link  

시계열:  
rainfall_observation  
stage_observation  
discharge_observation  
velocity_observation (필요 시)  
timeseries_extra  
derived_timeseries  

계측 품질/보정:  
measurement_calibration  
uncertainty_assessment  

홍수사상:  
flood_event  
analysis_event  

분석 재현성:  
analysis_module  
analysis_project  
analysis_run  
analysis_variable  
analysis_dataset  
analysis_result  
figure  

모형:  
equation_definition  
model  
model_parameter  
model_validation  

시스템:  
app_setting  
backup_history  

선택:  
stream_name_history  
event_timeseries_link  

GIS:  
V1 DB에 공간 테이블을 넣지 않는다.  
향후 GeoPackage 또는 별도 spatial extension을 검토한다.  

보안 운영정보:  
main research DB와 분리한다.  
필요하면 별도의 보호된 secure_operation 저장소를 설계한다.  

## 26. 아직 확정하지 않을 사항

다음 항목은 이 문서에서 임의 확정하지 않는다.  

- 실제 전국 특성정보 Excel의 의미가 불명확한 병합헤더 컬럼
- 노모그래프 정확한 수식
- 홍수사상 분리 기준
- 모형 초기값/제약조건/목적함수
- GIS schema
- 센서 세부 schema
- 운영정보 저장 schema
- V3 관측자료 timezone 세부 정책(시스템 시각 UTC 저장은 확정)

이들은 해당 단계에서 자료 검증 후 확정한다.  

## 27. ERD 관계 요약

아래 화살표는 부모 테이블에서 이를 참조하는 테이블로 향한다. 대표값 재구축은 FK 관계와 분리해 표시한다. 상세 FK는 각 테이블 절을 기준으로 한다.

```text
dictionary_version → data_dictionary (created_version_id / deprecated_version_id)
data_category → data_dictionary
unit_dictionary → data_dictionary → characteristic_value
unit_dictionary → unit_conversion (from_unit_id / to_unit_id)
unit_dictionary → characteristic_value / import_column_mapping
data_dictionary → column_alias / import_column_mapping / quality_rule

source_file → import_history → import_sheet → import_column_mapping
dictionary_version / schema_version → import_history
import_history / import_sheet / import_column_mapping → characteristic_value

small_stream → stream_relation (stream_code / related_stream_code)
import_history → stream_relation (source_import_id)
small_stream / data_dictionary → characteristic_value
small_stream / data_dictionary / characteristic_value → stream_characteristic
characteristic_value → data_quality_issue (characteristic_value_id, nullable)

quality_rule → data_quality_issue
import_history / import_sheet → data_quality_issue
small_stream / data_dictionary → data_quality_issue
data_quality_issue / import_history → record_history
app_user → import_history (created_by_user_id)
app_user → data_quality_issue (reviewed_by_user_id)
app_user → record_history (actor_user_id)
```

별도의 파생 흐름:

```text
characteristic_value → 대표값 선정·이력 기록 → stream_characteristic rebuild
```

`stream_characteristic.characteristic_value_id`는 authoritative 값의 실제 FK다. 캐시 재구축은 이 참조를 갱신하는 업무 흐름이며 FK의 존재 검사와 대표값/키 일치 검증을 구분한다.

## 28. 구현 전 확인사항

최종 감사 결과와 차단 항목은 다음 29절을 기준으로 한다. 시스템 UTC, mapping_id provenance, 1-based, UNMAPPED 메타데이터, A/B/C transaction, typed value 정확히 하나, QC snapshot과 원본 보존은 유지한다. 이번에 확정한 Draft·사용자명 표시·현재값·QC 집계·Backup/Restore 정책을 다시 미확정으로 취급하지 않는다.

## 29. SQLite DDL 직전 감사

이 절은 SQL 실행 결과가 아닌 문서·정적 감사다. 19개 테이블 정의를 확인했으며 DB·migration은 생성하지 않았다. 기존 컬럼 표의 NOT NULL/NULL/DEFAULT는 그대로 DDL에 옮긴다. 아래 명시적 보완은 기존 원칙의 SQL 표현이며 임의 연구 컬럼·임계값을 추가하지 않는다.

### 29.1 공통 선언과 19개 테이블 점검

- INTEGER PRIMARY KEY는 rowid 키이며 AUTOINCREMENT를 추가하지 않는다. small_stream의 TEXT PK와 stream_characteristic의 복합 PK 구성 컬럼에는 명시적 NOT NULL을 적용한다.
- 컬럼 표에 DEFAULT가 없으면 DDL에도 임의 기본값을 추가하지 않는다. 필수 시스템 시각은 Service가 UTC ISO 8601로 제공한다. updated_at은 SQLite가 자동 갱신하지 않으므로 Service가 갱신한다.
- 모든 Boolean은 기존 NOT NULL·0/1 CHECK를 유지한다. 날짜 TEXT·JSON TEXT의 형식과 사전 자료형 일치는 Service/Validator 계약이다. JSON 함수·STRICT 테이블·trigger를 새 필수 조건으로 넣지 않는다.
- 아래 ‘없음’은 해당 컬럼을 이번에 추가하지 않는다는 의미다. 상태로 관리하는 테이블에 is_active를 임의 추가하지 않는다.
- 일반 INDEX는 성능 목적이며 유일성 정책과 구분한다. 각 FK의 자식 검색 인덱스를 검토하되 PK/UNIQUE/복합 인덱스 선두로 이미 커버되면 중복 생성하지 않는다.

| 테이블 | PK | UNIQUE / 핵심 CHECK | created_at / updated_at | 활성 필드·대체 시각 | 일반 INDEX 감사 |
| --- | --- | --- | --- | --- | --- |
| schema_version | schema_version_id | version UNIQUE | 없음 / 없음 | applied_at; 활성 필드 없음 | version UNIQUE로 충분 |
| data_category | category_id | category_key UNIQUE; is_active 0/1 | 있음 / 있음 | is_active | parent_category_id 후보 |
| dictionary_version | version_id | version UNIQUE; is_current 0/1; current 부분 UNIQUE | 있음 / 없음 | is_current | 추가 필수 없음 |
| unit_dictionary | unit_id | unit_symbol UNIQUE; is_active 0/1 | 있음 / 있음 | is_active | 추가 필수 없음 |
| unit_conversion | conversion_id | (from_unit_id,to_unit_id,formula_type) UNIQUE; is_active 0/1 | 있음 / 있음 | is_active | from_unit_id는 UNIQUE 선두; to_unit_id 후보 |
| data_dictionary | dictionary_id | internal_name UNIQUE; data_type/storage_type/Boolean CHECK | 있음 / 있음 | is_active | category_id,unit_id,created_version_id,deprecated_version_id 후보 |
| column_alias | alias_id | (normalized_alias,source_scope) UNIQUE; is_active 0/1 | 있음 / 있음 | is_active | dictionary_id 후보 |
| source_file | source_file_id | is_active 0/1; file_hash UNIQUE 금지 | 없음 / 없음 | registered_at,is_active | file_hash 비유일 후보 |
| import_history | import_id | batch_code UNIQUE; status NOT NULL·닫힌 enum CHECK | 있음 / 없음 | started_at,finished_at,status | source_file_id,status,사용자·버전 FK 후보 |
| import_sheet | import_sheet_id | (import_id,sheet_name) UNIQUE; status CHECK | 있음 / 없음 | status | import_id는 UNIQUE 선두로 커버 |
| import_column_mapping | mapping_id | (import_sheet_id,source_column_index) UNIQUE; user_confirmed 0/1 | 있음 / 없음 | 활성 필드 없음 | sheet FK는 UNIQUE 선두; dictionary_id,target_unit_id 후보 |
| small_stream | stream_code TEXT NOT NULL | 전체 코드 숫자·길이/구성 길이·위경도·Boolean CHECK | 있음 / 있음 | is_active | province_name,city_county_name,stream_name 후보 |
| stream_relation | relation_id | is_active 0/1; 관계 UNIQUE 임의 추가 금지 | 있음 / 있음 | is_active | stream_code,related_stream_code,source_import_id 후보 |
| characteristic_value | characteristic_value_id | exactly-one; Boolean; 활성 현재값 부분 UNIQUE | 있음 / 있음 | is_active | stream+dictionary,단독 dictionary,unit/import/sheet/mapping FK 후보 |
| stream_characteristic | (stream_code,dictionary_id), 모두 NOT NULL | 복합 PK; authoritative 값 FK | 없음 / 있음 | 활성 필드 없음 | dictionary_id,characteristic_value_id 후보 |
| quality_rule | rule_id | rule_code UNIQUE; severity·is_enabled CHECK | 있음 / 있음 | is_enabled | dictionary_id 후보 |
| data_quality_issue | issue_id | severity·review_status·is_active CHECK | 있음 / 없음 | reviewed_at,is_active | (characteristic_value_id,is_active,severity),stream+dictionary,각 FK 후보 |
| record_history | history_id | 별도 UNIQUE/CHECK 없음 | 없음 / 없음 | changed_at; is_active 없음 | table_name+record_key,issue_id,import_id,actor_user_id,changed_at 후보 |
| app_user | user_id | 정규화 login_id UNIQUE·문자/길이 CHECK; is_active 0/1 | 있음 / 있음 | last_login_at,is_active | UNIQUE로 로그인 조회; 추가 필수 없음 |

일반 index의 이름·최종 조합은 Phase 1에서 실제 조회 SQL·계획에 맞춰 정한다. 이 후보가 모두 필수 인덱스라는 뜻은 아니다. characteristic_value의 전체 (stream_code,dictionary_id) 인덱스와 현재값 부분 인덱스는 포함 행이 달라 단순 중복이 아니다. 전체 복합 인덱스를 만들면 stream_code 단독 인덱스는 중복 검토 대상이다. 같은 원칙을 QC 조회에도 적용한다. record_key만으로 다른 테이블의 같은 키를 구분하지 않으므로 table_name과 함께 조회한다.

### 29.2 characteristic_value의 CHECK와 typed value

다음은 컬럼을 추가하지 않고 확정된 정확히 하나 규칙을 표현한 테이블 CHECK다.

```sql
CHECK (
  (value_number IS NOT NULL) +
  (value_integer IS NOT NULL) +
  (value_text IS NOT NULL) +
  (value_date IS NOT NULL) = 1
)
```

각 IS NOT NULL 결과는 0 또는 1이므로 합이 1이어야 한다. 4개 모두 NULL이거나 2개 이상 채운 행은 거부하며 숫자 0도 유효한 NON-NULL 값이다. 빈 문자열의 결측 의미는 CHECK가 추정하지 않는다. parse 실패·missing은 authoritative 행을 만들지 않는다.

SQLite 자료형 affinity만으로 value_integer의 실제 정수성이나 value_date의 날짜 유효성을 보장하지 않는다. data_dictionary의 REAL/INTEGER/TEXT/DATE/DATETIME과 선택 컬럼의 일치는 Service가 검증한다. 다른 테이블을 조회하는 CHECK를 만들지 않는다. DATE/DATETIME은 value_date TEXT를 공유하고 원본 timezone을 추정하지 않는다.

is_representative/is_active는 NOT NULL Boolean이며 16절의 부분 유일 인덱스가 활성 현재값 최대 하나를 보장한다. 여러 출처의 비대표값과 보정값은 계속 공존한다. 원본 typed value overwrite와 연구값 자동 선택은 허용하지 않는다.

### 29.3 provenance와 저장 전 검증

characteristic_value.mapping_id → import_column_mapping.import_sheet_id → import_sheet.import_id → import_history.source_file_id → source_file로 파일·시트·컬럼을 역추적한다. source_row와 source_column_index는 1-based이고 source_header, sheet_name, file_hash를 함께 이용한다. sheet_index는 순서 보조값이다.

단일 FK는 존재만 확인하므로 Service는 중복 보관한 import_id/import_sheet_id와 mapping의 소속 일치를 검사해야 한다. USER_CORRECTION/MANUAL/DERIVED의 mapping_id NULL은 허용한다. 새 Excel Import 값의 출처를 완전하게 추적하려면 실제 경로의 import_id/import_sheet_id/mapping_id/source_row와 원본 hash를 수집해야 한다. 현재 NULL 허용 schema만으로 출처 완전성을 강제하지 못하므로 수집 실패 시 처리·기존 참조 없는 자료의 예외는 Phase 6 계약에서 정한다. NULL을 허용한다는 이유로 정상 Import에서 출처 기록을 생략하지 않는다.

관리코드는 DB에서 TEXT·11자리·ASCII 숫자 형식을 검사하고 구성요소 길이를 유지한다. 연결 일치는 Service validation으로 검사하며 자동 보정하지 않는다. 위경도는 기존 nullable 컬럼에 14절의 형식 범위 CHECK를 적용한다. Excel 위치는 기존 1-based Service 검증을 유지하며 이번에 별도 위치 CHECK를 추가하지 않는다.

### 29.4 Import transaction 감사

A(RUNNING 별도 COMMIT) → B(실제 데이터 COMMIT/ROLLBACK) → C(SUCCESS/FAILED 별도 COMMIT)를 유지한다. A 전에 source_file 부모 행이 존재해야 하며 새 파일 등록을 A와 함께 확정할지 미리 등록할지는 ImportService 계약에 둔다. Preview/Mapping/workspace 저장은 import_history를 생성하지 않는다.

B의 실패는 이력 A를 지우지 않는다. 실패한 B의 sheet/mapping을 영구 QC의 FK로 남기지 않는다. 성공에서는 finished_at과 SUCCESS, 실패에서는 finished_at·error_code·error_message를 기록한다. 오류 문자열에 원본 민감값을 포함하지 않는다.

**Phase 6 전 TODO T1:** A 이후 강제 종료 또는 B COMMIT 이후 C 실패 시 RUNNING이 남을 수 있다. B가 이미 확정된 뒤 C 실패를 ‘데이터 rollback 완료/FAILED’로 잘못 처리하거나 자동 재Import해서는 안 된다. 성공한 B의 중요 IMPORT record_history를 B와 함께 보존하는 방향과 멱등한 C 재시도·시작 시 복구 판단 계약을 확정한다. 빈/전부 거부 Import도 고려하므로 단순히 characteristic_value 행 존재만으로 B 성공을 판정하지 않는다. 새 테이블을 추가하거나 A/B/C 경계를 합치지 않는다.

### 29.5 QC 활성 집계와 현재 사용값: Q1 확정

data_quality_issue.characteristic_value_id는 특정 authoritative 값의 nullable FK이고 is_active는 NOT NULL DEFAULT 1 / 0·1 CHECK다. active issue만 현재 집계에 쓰고 inactive는 이력으로 보존한다. 과거 severity·규칙 snapshot·review 상태를 새 결과로 덮어쓰지 않는다.

자동 QC 화면 상태는 data_quality_issue.is_active=1인 issue만 집계한다. 활성 issue가 없으면 ‘정상’, 활성 ERROR는 없고 INFO/WARNING만 있으면 ‘확인 필요’, 활성 ERROR가 하나 이상이면 ‘오류’다. INFO는 정상 severity가 아니다. review_status는 사람의 검토 상태로 별도 유지하며 활성 여부와 혼합하지 않는다. 활성 issue가 없다는 집계는 검사 실행 완료를 증명하지 않으므로 실행 여부 안내와 구분한다.

현재값 지정 시 해당 characteristic_value_id에 연결된 활성 ERROR가 있으면 거부한다. CONFIRMED나 CORRECTED로 검토 상태가 바뀌었어도 is_active=1인 ERROR는 차단한다. 활성 WARNING/INFO는 명시적 확인 후 선택 가능하다. 특정 값이 없는 issue의 NULL FK를 임의 후보 값에 연결하지 않는다. 그 issue는 파일/행/하천 등 해당 범위의 QC에 남으며, 이력의 현재값 차단을 위한 값 ID를 추측하지 않는다.

기존 characteristic_value.quality_status는 보존하되 현재값 차단의 authoritative 판정으로 사용하지 않는다. 판정은 data_quality_issue의 값 ID·severity·is_active 조건을 기준으로 한다. quality_status의 상세 표시/갱신 계약은 Phase 7~8에서 정할 수 있으며 초기 DB 구현을 막지 않는다.

재검사가 성공한 범위에서 기존 issue가 더 이상 현재 문제가 아니면 is_active=0으로 바꾸고 새 문제를 INSERT한다. 변경과 새 결과 저장을 한 transaction으로 처리해 실패 시 과거 활성 상태를 보존한다. 검사 범위·반복 탐지·문제 없는 실행의 UI 안내·복수 값 비교 시 issue 분할 방식은 Phase 7의 Service 계약이다. QC 실행 테이블이나 추가 FK를 요구하지 않으며 DB 차단 항목으로 남기지 않는다.

현재값 변경은 QC 조건 확인 → 이전 is_representative 해제 → 새 값 지정 → stream_characteristic 갱신 → record_history를 한 업무 transaction으로 처리한다. 대상 키 일치·활성값 여부를 Service에서 검증하고 부분 UNIQUE로 최대 하나를 보호한다. 어느 단계든 실패하면 선택·캐시·이력 모두 rollback한다. 새 ERROR 발견을 이유로 현재값을 자동 교체하지 않는다. 보정·비활성화·복원으로 현재값에 영향을 줄 때도 같은 일관성을 유지한다.

### 29.6 record_history 표현과 Backup/Restore

old_value/new_value는 TEXT NULL로 before/after를, reason은 TEXT NULL로 이유를, actor_user_id와 changed_at은 작업자와 UTC 시각을 표현한다. column_name·issue_id·import_id도 선택 필드다. 모든 작업에 모든 필드를 강제하지 않는다. generic 대상 table_name/record_key와 change_type,changed_at은 NOT NULL을 유지한다.

중요 작업 표현은 IMPORT, QC_REVIEW, CORRECTION, CURRENT_VALUE_CHANGE, DEACTIVATE, RESTORE(비활성 데이터 복원), BACKUP, DB_RESTORE(DB 전체 복원)다. 기존 예시 USER_CORRECTION/REPRESENTATIVE_CHANGE는 각각 CORRECTION/CURRENT_VALUE_CHANGE 의미에 대응한다. 이는 업무 용어 대응이며 전체 change_type CHECK 목록을 임의 확정하는 것이 아니다. 여러 값의 보정·선택 전후 ID 등 구조화 TEXT 표현은 Phase 8 전 계약으로 정의한다. 연구값 직접 overwrite나 클릭 로그 저장은 하지 않는다.

Restore 전 자동 안전백업 생성 → 복원 검증 → 새 현재 DB의 record_history에 DB_RESTORE 기록 방향을 확정한다. 안전백업 실패 시 복원을 계속 진행하지 않는 오류 처리와 SQLite backup/WAL/연결 종료/파일 전환 기술은 Phase 14에서 검증한다. DB_RESTORE는 사용자 요청의 ‘RESTORE 작업 이력’에 해당하며 데이터 복원 RESTORE와 구분한 명칭이다.

**Phase 14 전 TODO B1:** 복원본에 현재 actor_user_id가 없거나 같은 ID가 다른 사람일 수 있다. 원래 DB 세션의 숫자 ID를 그대로 기록하면 FK 실패 또는 잘못된 귀속이 발생한다. 복원된 계정 확인/재인증·작업자 미상 표현을 결정하고 일반 신규 작업의 사용자 필수 원칙과 복구 예외를 구분한다. 비밀번호도 백업 시점으로 돌아갈 수 있다.

table_name/record_key의 DB 전체 작업 대상 표현, 복원 후 이력 기록 실패 시 완료 판정, 안전백업 보관·복구 절차는 Phase 14 전에 확정한다. 기존 schema 변경 없이 generic history로 표현하는 방향을 유지한다. 복원본에는 백업 이후 최신 이력이 없으며 안전백업에 보존된 이력을 자동 병합하지 않는다. 캐시는 characteristic_value 기준으로 재검증한다. 백업 파일은 app_user hash를 포함하는 전체 DB이므로 일반 Excel Export와 다르게 다루고 자격증명을 UI/로그에 출력하지 않는다.

### 29.7 데이터 사전·분석·민감정보

사전의 data_type, unit_id, nullable, analyzable, required, is_active, category_id, 별칭과 버전 FK는 동적 매핑·분석 선택을 지원한다. nullable은 원본 항목 결측 허용이며 NULL typed 행 허용이 아니다. mean/median/std/min/Q1/Q3/max 및 Histogram/Boxplot/Scatter의 수치축은 data_type IN ('REAL','INTEGER')와 analyzable=1을 기준으로 선택한다. 분석 결과 저장 테이블은 추가하지 않는다. 통계 정의·결측 분모·QC 포함 정책은 Phase 11 전에 결정한다.

source_file.file_hash는 중복 경고용이며 UNIQUE를 추가하지 않는다. source_file 및 연구자료는 비활성화를 우선하고 원본 디스크 파일을 자동 삭제하지 않는다. UNMAPPED는 메타데이터만 보관한다. 헤더·경로·오류 문구에도 민감정보가 포함될 수 있으므로 characteristic 값뿐 아니라 Preview/Export/로그/history/settings_json/workspace의 불필요한 secret 복사를 차단한다. 원본 보존은 운영정보를 연구 DB로 가져오는 근거가 아니다.

일반 UI 설정은 QSettings/local config, Import Draft는 별도 로컬 workspace에 저장한다. 두 저장소는 연구 DB 테이블이 아니며 19개 목록에 포함하지 않는다.

### 29.8 구현 착수 판정과 잔여 항목

**READY WITH NON-BLOCKING TODOS.** C1·U1·Q1과 기본 형식 CHECK·순차 migration 방향이 확정되어 실제 Phase 1 DB 구현을 막는 설계 항목은 없다. Phase 0 기반 및 Phase 1 구현은 이후 사용자의 해당 작업 요청 범위에서 진행할 수 있다. 이번 작업은 설계문서만 수정하며 구현 완료·테스트 통과를 뜻하지 않는다.

| 항목 | 확정 결과 또는 남은 작업 | 시점 |
| --- | --- | --- |
| C1 | 4개 컬럼의 현재값 참조 캐시, 복합 PK와 3개 FK | 해소 |
| U1 | trim→소문자→허용 문자/4~50자 검증, 정규화 login_id UNIQUE | 해소 |
| Q1 | 값 FK·is_active, 활성 ERROR 차단·재검사 과거 보존 | 해소 |
| S1 | 전체 관리코드 숫자·길이 CHECK, 구성 연결 Service 검증, nullable 위경도 CHECK, 닫힌 상태 CHECK, 순차 migration | 설계 해소; runner·인덱스 계획·실제 제약 테스트는 Phase 1 구현 작업 |
| A1 | hashing library/알고리즘 및 오프라인 분실 대응 | Phase 1A 전 |
| W1 | workspace 형식·소유권·원자 저장·손상/정리·복원 후 재검증 | Phase 5 전 |
| T1 | A/B/C 중단 복구와 완료 판별·멱등성 | Phase 6 전 |
| Q2 | QC 재검사 범위·반복 탐지·복수 대상·실행 안내, quality_status 표시 계약 | Phase 7~8 전 |
| H1 | generic history 대상/old-new 구조화 계약 | Phase 8 전 |
| B1 | 안전백업·복원된 계정 연결·이력 기록 실패 대응 | Phase 14 전 |

일반 index의 최종 조합·migration runner는 합의된 정책을 구현하는 Phase 1 작업이며 사전 사용자 결정이 필요한 blocker가 아니다. 닫힌 enum/Boolean은 명시한 CHECK를 사용하고 자유 텍스트/예시 상태를 새로운 enum으로 임의 확장하지 않는다. 연구 threshold·기본 사전·단위·민감정보 탐지 목록·통계 정의는 기존대로 해당 Phase에서 자료 근거를 확인한다.

### 29.9 SQLite 호환성 근거와 검증 한계

SQLite 공식 문서의 [CREATE TABLE](https://www.sqlite.org/lang_createtable.html), [SQL Expressions](https://www.sqlite.org/lang_expr.html), [Partial Indexes](https://www.sqlite.org/partialindex.html), [Foreign Key Support](https://www.sqlite.org/foreignkeys.html)를 대조했다. CHECK, 부분 UNIQUE 인덱스와 명시적 FK action은 SQLite로 표현 가능하다. CHECK에는 다른 테이블을 조회하는 subquery를 넣지 않는다. FK는 연결마다 foreign_keys=ON으로 활성화하고 실제 구현에서 확인한다.

공식 문서·표현식 검토와 실제 DDL 실행 시험을 구분한다. 이번에는 DB 생성·SQL 실행을 하지 않았다. Phase 1에서 배포 런타임의 SQLite 버전·FK 활성화, NULL/다중 typed 거부, 대표값 중복, 참조 삭제 거부, 재초기화·migration을 실제 검증한다.
