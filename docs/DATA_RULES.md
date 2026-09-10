# 데이터 처리 규칙

이 문서는 `small-stream-research-tool`에서 원본 Excel을 읽고 탐색·매핑·표준화·검증하여 DB에 저장하기까지의 처리 규칙을 정의한다. `AGENTS.md`, `PROJECT_OVERVIEW.md`, `ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `QC_RULES.md`를 기준으로 작성했다. 현재는 설계 단계이며 기능 구현 완료를 뜻하지 않는다.

DB 구조는 DATABASE_DESIGN.md, 문제 탐지와 severity·review 처리는 QC_RULES.md를 따른다. 원본값·표준화값·QC 결과·대표값·사용자 보정값을 구분하고, 불확실한 연구자료 의미나 미확정 DB 필드를 추가하지 않는다.

## 1. 기본 원칙

- 원본 Excel 수정 금지
- 원본값 보존
- 자동 정리와 의미 변경 구분
- 불명확한 값 자동 수정 금지
- 불명확한 컬럼은 UNMAPPED
- 오류/불일치 자동 삭제 금지
- provenance 유지
- 연구자 판단이 필요한 사항은 Preview/QC로 전달

핵심 철학:  
“보기 좋게 자동 보정된 데이터”보다  
“원본과 처리 과정을 추적할 수 있는 신뢰 가능한 연구 DB”를 우선한다.  

## 2. 전체 데이터 처리 흐름

Source File Registration  
→ Workbook Inspection  
→ Sheet Inspection  
→ Header Detection  
→ Column Discovery  
→ Column Mapping  
→ Value Normalization  
→ Basic Validation  
→ Import Preview  
→ User Confirmation  
→ Transaction Import  
→ QC  
→ Representative Value Selection  

위 흐름은 대표 업무 순서다. QC_RULES.md에 따라 Preview 이전·중간의 구조/매핑/기본 검증, Import 직전 blocking validation, Import 이후 비교 QC, 사용자 보정 이후 재검사도 수행할 수 있다. QC를 Import 이후에만 허용한다는 의미는 아니다.

화면 흐름은 로그인 → 홈 → Excel 가져오기 → 컬럼 매핑 → 관리코드 검증 → Preview → 실제 Import다. DB 구축은 Import 대상 등록이며 QC 완료를 뜻하지 않는다.

## 3. 원본 파일

source_file을 이용한다.  

확인 대상:  

- 파일명
- 원본 경로
- 확장자
- 파일 크기
- 수정시각
- hash
- 등록시각

경로만 영구 식별자로 사용하지 않는다.  

동일 hash:  
중복 가능성을 알릴 수 있지만  
자동 삭제 또는 Import 차단하지 않는다.  

원본 파일:  

- 이동 금지
- 삭제 금지
- 이름 자동변경 금지
- 덮어쓰기 금지

## 4. Excel 구조

V1 기본:  
.xlsx  

.xlsm은 데이터 읽기 가능성을 검토할 수 있다.  
.xls는 V1 필수 범위로 확정하지 않는다.  

다음 구조를 고려한다:  

- multi-sheet
- multi-row header
- merged header
- 제목/설명 행
- 서로 다른 데이터 시작행
- 빈 행
- 컬럼 순서 차이
- 컬럼 추가/누락
- 동일 의미의 다른 컬럼명
- 단위가 header에 포함된 구조

모든 sheet를 자동으로 데이터 sheet라고 가정하지 않는다.  

## 5. Header Detection

header가 항상 첫 행이라고 가정하지 않는다.  

다음 정보를 탐색에 활용할 수 있다:  

- 비어있지 않은 셀 비율
- 문자열 패턴
- 병합 셀
- 다음 행과의 데이터형 차이
- 반복 구조

이것은 heuristic이다.  

자동 검출 결과는 Import Preview에서  
사용자가 확인할 수 있어야 한다.  

## 6. 병합 Header

병합셀의 상위 header를 이용해  
하위 컬럼의 구조를 복원할 수 있다.  

구조 설명용 예:  

유역특성 / 유역면적  
유역특성 / 평균고도  

이 예시는 실제 자료에서 확인한 표준항목이나 확정 DB 필드 목록이 아니다.  

다만 composite header를  
곧바로 표준 데이터항목으로 확정하지 않는다.  

source header와 normalized header를 구분한다.  

## 7. Header normalization

안전하게 허용 가능한 처리:  

- 앞뒤 공백 제거
- 연속 공백 정리
- 줄바꿈 정리
- Unicode normalization
- 명확한 장식문자 정리
- 대소문자 차이 정리
- 등록된 규칙에 따른 단위 분리

컬럼 의미를 바꾸는 normalization은 금지한다.  

## 8. Column Mapping

매핑은 다음 정보를 이용할 수 있다:  

- column_alias
- standard_name
- internal_name
- normalized header
- source_scope
- 사용자 직접 매핑

정확한 일치를 우선한다.  

fuzzy matching은 향후 추천 기능으로 사용할 수 있으나  
사용자 확인 없이 자동 확정하지 않는다.  

## 9. UNMAPPED

확실히 매핑할 수 없는 컬럼:  

mapping_status = UNMAPPED  

유지 정보:  

- source sheet
- source column
- source header
- normalized header

사용자가 이후:  

- 기존 dictionary item 연결
- 새 dictionary item 등록
- alias 등록
- 제외 선택(기존 DB 설계의 mapping_status 예시인 IGNORED)

중 선택할 수 있다.  

UNMAPPED 컬럼을 자동으로 새 dictionary item으로 생성하지 않는다.  


### V1 보관 및 재Import 정책

V1에서는 UNMAPPED 컬럼의 모든 셀 값을 별도 raw/staging DB에 복제하지 않는다. source file metadata/hash, import, sheet, source column 위치, source header, normalized header와 mapping_status=UNMAPPED 등 메타데이터를 저장한다.

사용자가 컬럼 의미를 확정하면 원본 Excel을 다시 선택·참조하여 새 mapping으로 재Import한다. 원본 위치가 바뀌었으면 file hash 등으로 동일 파일 여부를 검증할 수 있도록 한다.

characteristic_value와 data_quality_issue를 범용 raw cell 저장소로 사용하지 않는다. raw_cell/staging/unmapped_value 테이블을 V1에 추가하지 않는다. 미매핑 컬럼에 민감 운영정보가 포함될 수 있으므로 원본 셀을 무조건 DB에 복제하지 않는다.

## 10. 필수항목

data_dictionary.required를 사용하지만  
모든 Import에 동일하게 적용한다고 가정하지 않는다.  

Import 유형별로 필수항목이 다를 수 있다.  

예:  

- 소하천 기본정보
- 특성정보
- 향후 계측자료

Import type별 validation rule 확장을 고려한다.  

## 11. 소하천 관리코드

전체 식별자:  

stream_code = 소하천 관리코드 11자리  

구성:  

province_code: 2자리 TEXT  
city_county_code: 3자리 TEXT  
town_code: 3자리 TEXT  
stream_serial_no: 3자리 TEXT  

연결:  

province_code  
+ city_county_code  
+ town_code  
+ stream_serial_no  
=  
stream_code  

모두 TEXT.  

leading zero를 보존한다.  

관리코드를 INTEGER로 변환하지 않는다.  

구성요소만 있고 stream_code가 없으면  
명확한 규칙에 따라 생성 가능하다.  

둘 다 존재하면 생성 결과와 원본 stream_code를 비교한다.  

불일치는 QC로 전달하며 자동 수정하지 않는다. 명확한 구성요소의 연결로 누락된 전체 코드를 생성하는 것과 기존 오류 코드를 추정해 수정하는 것은 구분한다.  

DB는 전체 stream_code의 TEXT·11자리·숫자 형식과 구성요소 길이를 검사한다. 전체 코드와 구성요소 연결 일치는 Service validation으로 검사한다.

## 12. 관리코드 검증

검사 후보:  

- NULL
- 길이
- 허용문자
- 구성요소 길이
- 구성요소 연결 결과
- 동일 Import 내 중복
- 기존 DB와 충돌
- leading zero 손실 가능성
- Excel scientific notation 문제

관리코드는 산술값이 아니라 식별자다.  

## 13. 문자열 정규화

자동 허용:  

- 앞뒤 whitespace 제거
- 명확한 빈 문자열 → NULL
- 등록된 결측 표현 변환

하지만 "-" 등의 문자가  
실제 의미를 가질 수 있으므로  
전 컬럼 공통으로 무조건 결측 처리하지 않는다.  

의미 있는 행정명칭이나 문자열을 임의 수정하지 않는다.  

## 14. 숫자 정규화

고려:  

- Excel numeric cell
- 문자열 숫자
- 쉼표
- 공백
- 음수
- 소수
- scientific notation
- 단위 포함 문자열

안전하게 변환 가능한 경우만 변환한다.  

parse 실패:  

- 원본값 보존
- validation/QC
- 0으로 변환 금지

NULL과 0을 구분한다.  

## 15. INTEGER / REAL

INTEGER 항목에 3.0처럼  
정수로 정확히 표현 가능한 값의 허용 정책은 구현 시 정의한다.  

3.5처럼 실제 비정수값이면  
검증 대상이다.  

REAL 비교 시 floating point 오차를 고려하지만  
연구적 허용오차를 근거 없이 전역 설정하지 않는다.  

## 16. 날짜/시간

명확하게 해석 가능한 원본값만 변환하며 모호한 날짜를 자동 해석하지 않는다.

프로그램이 자체 생성하는 created_at, updated_at, registered_at, started_at, finished_at, reviewed_at, changed_at, applied_at 등의 시스템 시각은 **UTC 기준 ISO 8601 TEXT**로 저장한다. 권장 표현은 YYYY-MM-DDTHH:MM:SSZ다. 필요하면 fractional seconds를 사용할 수 있으나 프로젝트 전체 표현을 일관되게 유지한다. UI에서는 사용자 로컬 timezone으로 변환하여 표시할 수 있다.

원본 연구자료의 날짜/시간은 시스템 시각과 구분한다. 원본에 timezone 정보가 없으면 KST/UTC 등을 임의로 부여하지 않고 original_value를 보존한다. 원본 timezone을 알 수 있으면 해당 데이터 유형의 명시적 규칙에 따라 처리한다. V3 계측 시계열 구현 전 관측자료 timezone 정책을 별도로 상세화한다.

Service/Validator는 data_dictionary.data_type과 typed value 컬럼의 일치를 검증한다. DATE와 DATETIME 모두 V1에서는 value_date TEXT를 사용하며 Validator가 구분한다. DATE는 YYYY-MM-DD, DATETIME은 ISO 8601 형식이다. 원본 DATETIME에 timezone이 없으면 임의로 추가하지 않는다. 별도 value_datetime 컬럼은 추가하지 않는다.

## 17. 단위

표준 단위:  
unit_dictionary  

원본 단위:  
original/source unit 보존  

표준 단위:  
data_dictionary.unit_id  

자동 단위변환은  
unit_conversion에 명시적으로 등록된 경우만 허용한다.  

기본 선형 변환:  

converted = original * factor + offset  

임의 expression eval 금지.  

변환 규칙이 없으면 자동 환산하지 않는다.  

## 18. 소하천명

stream_name은 JOIN KEY가 아니다.  

JOIN 기본키:  
stream_code  

이름에 허용 가능한 자동처리:  

- 앞뒤 공백
- Unicode normalization

금지:  

- 오탈자 자동수정
- 접미사 자동삭제
- 유사도만으로 동일 하천 판정
- 최신 이름 자동선택

같은 stream_code에서 이름이 다르면 QC 대상이 될 수 있다.  

## 19. 행 처리

완전히 빈 행:  
skip 후보  

부분적으로 빈 행:  
자동 삭제 금지  

식별자가 없고 특성값만 있는 행:  
Preview/QC 대상  

한 행 위/아래로 밀린 것처럼 보여도  
자동 row shift 금지.  

## 20. Row Alignment

다음 패턴을 탐지 후보로 본다:  

- 첫 식별자 행의 특정 특성구간이 비어 있음
- 마지막에 식별자 없는 특성값 행
- 특정 열 구간이 반복적으로 일정 offset을 보임
- 기준자료 비교 시 인접 행 값이 일정 패턴으로 일치
- 식별정보와 특성정보 행 개수 불일치

이것은 자동수정 규칙이 아니라 탐지 규칙이다.  

“행 정렬 이상 의심”으로 QC에 전달한다.  

## 21. 중복

다음 유형을 구분한다:  

- 동일 stream_code 반복
- 동일 stream_code + dictionary item 반복
- 동일 source + 동일값
- 서로 다른 source + 동일값
- 서로 다른 source + 서로 다른 값

중복이라는 이유만으로 자동 삭제하지 않는다.

같은 관리코드가 기존 DB에 있다는 사실만으로 새 Import를 자동 오류·차단 처리하지 않는다. 기존 소하천과 연결하고 여러 출처·시점의 특성값을 보존하며 실제 충돌만 검토한다.

## 22. 결측

결측 ≠ 오류  

필수값:  
validation/QC  

선택값:  
허용 가능  

자동 금지:  

- 0 대체
- 평균 대체
- 중앙값 대체
- 인접값 보간

분석용 imputation은 향후 명시적으로 요청된 분석 데이터 처리에서 별도로 검토한다. V1 Import에서 보간을 수행하거나 원본값을 바꾸는 근거가 아니다.  

## 23. 이상치

이상치 ≠ 잘못된 데이터  

자연재난/수문자료의 극단값은  
실제 중요한 현상일 수 있다.  

통계적 이상치 탐지는 QC flag로 사용한다.  

자동 삭제/수정 금지.  

## 24. Cross-source comparison

기본 JOIN KEY:  
stream_code  

비교 가능:  

- 존재 여부
- stream_name
- characteristic value
- unit
- reference_year

서로 다른 출처의 연구값은 보존한다. 민감정보 제외 및 parse 실패값의 QC 보존 원칙을 따르며, 모든 값을 정상 typed value로 저장한다는 의미는 아니다.  

파일 수정시각/등록시각만으로  
어느 값을 정답으로 결정하지 않는다.  

## 25. characteristic_value

특성정보의 authoritative source of truth다.  

원본 Import 값은 overwrite하지 않는다.  

가능하면 다음을 추적한다:  

- stream
- dictionary item
- typed value
- original value
- original unit
- import
- sheet
- source row
- source column mapping
- reference year

유효한 typed value를 만들 수 없는 parse 실패값을  
정상 characteristic_value처럼 저장하지 않는다.  


value_number, value_integer, value_text, value_date 중 **정확히 하나만 NON-NULL**이어야 한다. characteristic_value는 실제 유효한 값을 저장한다. SQLite CHECK 표현은 DATABASE_DESIGN.md의 제약 감사에서 확인했다. 실제 DDL 실행 검증은 Phase 1에서 수행한다.

결측이면 NULL value를 가진 characteristic_value 행을 생성하지 않는 것을 원칙으로 한다. 필수값 결측은 validation/QC issue로 처리한다. data_dictionary.nullable은 해당 항목의 결측 허용 여부이며 NULL characteristic_value 행 생성 허가를 뜻하지 않는다.

Service/Validator는 data_dictionary.data_type과 typed value 컬럼의 일치를 검증한다. DATE와 DATETIME 모두 V1에서는 value_date TEXT를 사용하며 Validator가 구분한다. DATE는 YYYY-MM-DD, DATETIME은 ISO 8601 형식이다. 원본 DATETIME에 timezone이 없으면 임의로 추가하지 않는다. 별도 value_datetime 컬럼은 추가하지 않는다.

Import 출처는 source_file → import_history → import_sheet → import_column_mapping → 원본 source column으로 추적한다.

characteristic_value는 **mapping_id와 source_row**를 함께 사용하여 원본 Excel의 행·열 출처를 식별한다. mapping_id는 import_column_mapping.mapping_id를 참조한다. Import 값은 가능한 한 mapping_id를 저장한다. USER_CORRECTION / MANUAL / DERIVED 등 원본 Excel column mapping이 없는 값은 NULL을 허용한다.

characteristic_value에 source_file_id나 source_column을 중복 저장하지 않는다. Service는 mapping_id가 가리키는 import_sheet와 characteristic_value.import_sheet_id가 일치하고, mapping이 속한 import와 characteristic_value.import_id가 일치하는지 검증한다. import_id와 import_sheet_id가 함께 있으면 같은 Import 소속인지도 검증한다. 과도한 DB trigger는 사용하지 않는다.

DB provenance의 source_row, source_column_index, source_column 등 Excel 사용자 위치는 원칙적으로 **1-based**를 사용한다. Python/openpyxl/pandas 등 처리 도구의 내부 index 기준을 확인하여 저장 경계에서 명확하게 변환한다. 0-based 내부 index와 혼동하지 않는다. sheet_name을 주요 provenance로 사용하고 sheet_index는 표시·순서 보조정보로 구분한다.

## 26. Representative

동일:  

stream_code + dictionary_id  

에 활성 representative 최대 하나.  

대표값 변경:  

기존 대표값 해제  
→ 새 대표값 지정  
→ record_history  
→ stream_characteristic rebuild  

과정으로 처리한다.  

대표값은 원본을 삭제하거나 덮어쓰는 개념이 아니다.

UI의 **현재 사용값**은 기존 is_representative로 선택한 값이다. characteristic_value는 원본값과 새로 추가한 보정값을 보존하고, record_history는 보정·선택 변경을 기록하며, stream_characteristic은 현재 사용값의 ID를 보관하고 실제 값은 characteristic_value에서 조회하는 참조 캐시다. 별도 현재값 테이블을 만들지 않는다.

동일 stream_code + dictionary_id에 활성 현재 사용값은 최대 하나다. 새 자료 Import만으로 현재 사용값을 변경하지 않으며 사용자가 명시적으로 선택한다. 선택할 characteristic_value_id에 severity='ERROR' AND is_active=1인 issue가 있으면 지정할 수 없다. 활성 WARNING/INFO는 연구자가 확인한 뒤 명시적으로 지정할 수 있다. review_status 변경만으로 ERROR 차단을 해제하지 않는다. 기존 값을 삭제·덮어쓰지 않고 characteristic_value.is_representative 변경·stream_characteristic 참조 캐시 갱신·record_history 기록을 하나의 업무 transaction으로 처리한다. 어느 단계든 실패하면 전부 rollback하며 자동 선정은 금지한다.

## 27. 사용자 보정

원본 Import 값을 직접 수정하지 않는다.  

기본 흐름:  

원본값 보존  
→ 새 characteristic_value  
→ source_type = USER_CORRECTION  
→ QC/history 연결  
→ 필요 시 representative 변경  

으로 한다.

보정자는 record_history.actor_user_id로 연결한다. UI의 현재 사용값은 내부 is_representative이며 보정 등록 자체가 자동 선택을 뜻하지 않는다.

## 28. stream_characteristic

authoritative source가 아니다.  

stream_characteristic은 (stream_code, dictionary_id)별 현재 characteristic_value_id와 updated_at만 보관하는 재구축 가능한 참조 캐시다. 실제 값은 characteristic_value에서 조회하며 고정 연구 특성 컬럼이나 값 복제는 두지 않는다. 활성 is_representative를 기준으로 재구축하고 사용자 직접 수정은 금지한다.  

직접 편집하지 않는다.  

cache 오류가 있으면  
characteristic_value를 기준으로 Service를 통해 rebuild한다. 이는 파생 캐시 갱신이며 원본값 자동수정이나 대표값 자동선택이 아니다.  

## 29. Import Preview

DB 저장 전 최소 확인 대상:  

- 파일
- sheet
- header 범위
- data 시작행
- 원본 컬럼
- normalized header
- mapping status
- dictionary item
- source unit
- target unit
- sample value
- 필수항목 누락
- 관리코드 오류
- parse 오류
- UNMAPPED
- 제외 컬럼
- 민감정보 가능 컬럼

전체 행을 한 화면에 모두 보여줄 필요는 없다.  

요약 + sample + issue 중심 UI가 가능하다.

### 진행 중 Import 작업 저장: V1 로컬 workspace

V1은 Excel 가져오기 → Sheet/Header 선택 → 컬럼 매핑 후 프로그램을 종료해도 재실행·로그인 후 이어서 작업할 수 있도록 한다. 임시 선택 상태는 연구 DB 밖의 application data/workspace 아래 로컬 파일(JSON 등)에 저장한다. 경로 예시는 `workspace/import_draft_xxx.json`이며 실제 파일명 계약은 구현 단계에서 정한다. 연구 DB는 19개 테이블을 유지하며 Draft 테이블을 추가하지 않는다.

저장 후보는 사용자 ID, 원본 Excel 경로·hash, 선택 Sheet, Header 시작/종료 행, Data 시작 행, 컬럼 매핑 상태, 현재 작업 단계, 마지막 저장 시각이다. 행·컬럼은 1-based, 시스템 저장 시각은 UTC를 따른다. 원본 전체 셀·민감값·비밀번호·인증정보는 복제하지 않는다.

재개 시 원본 파일 존재와 hash 일치를 확인한다. 파일 이동·부재 또는 hash 불일치 시 자동 대체하지 않고 사용자에게 원본 파일 재지정을 요구한다. 재지정 파일도 검증하며 내용이 바뀐 파일에 이전 매핑을 자동 확정하지 않는다. 사전·매핑 유효성은 재개 시 다시 검증한다.

source_file은 원본 메타데이터, workspace는 미완료 작업, import_history는 실제 DB Import 실행 이력이다. Preview/매핑/Draft 저장은 import_history를 생성하지 않는다. workspace의 사용자 ID는 DB FK가 아니므로 Service가 현재 DB·로그인 사용자와의 소유 관계를 확인한다. DB 복원 후 같은 숫자 사용자 ID를 동일인으로 단정하지 않는다.

파일 형식 버전·원자적 저장·손상 대응·사용자별 접근·보존 기간·Import 성공 후 정리·비활성 계정 및 DB 복원 시 재연결 계약은 Phase 5 전 TODO다. 정리는 원본 Excel이나 Export 파일 자동 삭제를 뜻하지 않는다.

## 30. Import blocking

severity와 blocking은 별개다.  

파일 전체 blocking 후보:  

- 데이터 sheet 결정 불가
- 필수 식별구조 전체 부재
- DB schema incompatibility
- transaction 준비 실패

행 단위 rejection 후보:  

- 해당 행 관리코드 생성/검증 불가
- 필수값 치명적 parse 실패

전체 차단이 아닐 수 있는 예:  

- 선택항목 결측
- 일부 UNMAPPED
- WARNING 이상치
- 하천명 불일치

QC_RULES.md의 blocking 설계를 따른다.  

구체적인 최종 blocking rule은  
Import type별 구현 전에 확정한다.  

## 31. Import Transaction

### A. Import 실행 이력 생성

import_history의 status를 RUNNING으로 기록하고 **별도 transaction에서 COMMIT**한다.

### B. 실제 데이터 Import

import_sheet, import_column_mapping, small_stream 신규/관련 반영, characteristic_value 및 해당 Import와 함께 확정되어야 하는 관련 자료를 **하나의 업무 transaction**으로 처리하는 것을 기본으로 한다. 성공하면 COMMIT, 실패하면 ROLLBACK한다.

### C. 결과 이력 갱신

- 성공 후 별도 transaction에서 import_history.status를 SUCCESS로 갱신하고 finished_at을 기록한다.
- 실패 후 별도 transaction에서 import_history.status를 FAILED로 갱신하고 error_code, error_message, finished_at을 기록한다.

실제 데이터 transaction이 rollback되어도 Import 시도와 실패 이력은 보존한다. rollback된 import_sheet/import_column_mapping 등의 FK를 data_quality_issue가 강제로 참조하게 하지 않는다. Preview issue와 실패 진단정보의 영구 보존 범위는 별도 구현정책으로 정할 수 있다. V1에 import_error 테이블을 추가하지 않는다.

파일 선택·Preview만으로 import_history를 만들지 않는다. 실제 DB 반영 시작 시 RUNNING 이력에 created_by_user_id를 기록한다. 현재 사용자를 Service에서 전달하며 Import 성공과 QC 상태는 분리한다.

작업자 연결은 import_history.created_by_user_id, data_quality_issue.reviewed_by_user_id, record_history.actor_user_id에서만 추가하며 모두 app_user.user_id를 참조한다. 세 FK는 NULL을 허용한다(미검토 QC, 기존/작업자 미상 기록 등). 다만 새 로그인 사용자의 Import 실행·QC 검토·중요 변경은 Service가 해당 사용자 ID를 반드시 기록하며 임의 NULL로 누락하지 않는다.

세 사용자 FK의 ON DELETE는 RESTRICT로 설계한다. 계정은 물리 삭제 대신 is_active=0으로 비활성화하고 기존 사용자 행·표시정보·FK를 보존한다. CASCADE DELETE나 SET NULL로 과거 작업자를 지우지 않는다. record_history.changed_by는 기존 비구조화 작업자 텍스트로 유지하며 새 작업의 기준 식별자는 actor_user_id다.

A 이후 중단 또는 B COMMIT 이후 C 갱신 실패는 DATABASE_DESIGN.md의 T1에 따라 Phase 6 전에 복구 계약을 정한다. RUNNING만 보고 실제 데이터가 rollback되었다고 판단하거나 재Import하지 않는다.

과거 작업이력의 이름은 actor_user_id로 현재 app_user.display_name을 조회한다. V1 이름 snapshot은 추가하지 않는다. DB Restore 전 자동 안전백업을 만들고 성공 후 새 현재 DB의 record_history에 DB_RESTORE를 기록한다. 복원본의 계정 ID는 원래 DB 사용자와 동일하다고 단정하지 않는다.

## 32. Provenance

Import 출처는 source_file → import_history → import_sheet → import_column_mapping → 원본 source column으로 추적한다.

characteristic_value는 **mapping_id와 source_row**를 함께 사용하여 원본 Excel의 행·열 출처를 식별한다. mapping_id는 import_column_mapping.mapping_id를 참조한다. Import 값은 가능한 한 mapping_id를 저장한다. USER_CORRECTION / MANUAL / DERIVED 등 원본 Excel column mapping이 없는 값은 NULL을 허용한다.

characteristic_value에 source_file_id나 source_column을 중복 저장하지 않는다. Service는 mapping_id가 가리키는 import_sheet와 characteristic_value.import_sheet_id가 일치하고, mapping이 속한 import와 characteristic_value.import_id가 일치하는지 검증한다. import_id와 import_sheet_id가 함께 있으면 같은 Import 소속인지도 검증한다. 과도한 DB trigger는 사용하지 않는다.

DB provenance의 source_row, source_column_index, source_column 등 Excel 사용자 위치는 원칙적으로 **1-based**를 사용한다. Python/openpyxl/pandas 등 처리 도구의 내부 index 기준을 확인하여 저장 경계에서 명확하게 변환한다. 0-based 내부 index와 혼동하지 않는다. sheet_name을 주요 provenance로 사용하고 sheet_index는 표시·순서 보조정보로 구분한다.

## 33. 민감정보

main research DB에서 기본 제외 대상:  

- service key
- API key
- password
- 인증정보
- public/private IP
- CCTV IP
- RTSP URL
- 개인 연락처

탐지:  

- 등록 alias
- dictionary category
- header keyword rule
등을 사용할 수 있다.  

keyword만으로 완벽한 탐지를 보장한다고 가정하지 않는다.  

Preview에서 확인한다.  

민감정보 원본값을 로그/QC message에 출력하지 않는다. Preview sample에서도 secret을 노출하지 않으며, data_quality_issue의 original_value·compare_value·검토 메모에도 복사하지 않는다. 원본 보존은 민감정보를 연구 DB에 복제하는 근거가 아니다.

V1은 개인 PC의 로컬 계정으로 현재 작업자를 식별한다. 서버·팀 협업·동시편집·온라인 회원가입·이메일/휴대폰 복구·복잡한 권한 관리는 포함하지 않는다. 사용자가 없으면 최초 사용자 등록 화면으로 연결한다. app_user의 비밀번호는 평문으로 저장하지 않으며 자체 암호화·비밀번호 알고리즘을 만들지 않는다. 검증된 password hashing library를 사용하며 세부 library·알고리즘은 Phase 1A 인증 구현 직전에 확정한다. 이 선택은 Phase 0 또는 DB 컬럼 정의 자체의 차단 사유가 아니다.

로컬 앱 계정은 연구자료에서 가져온 운영 인증정보와 구분한다. app_user는 애플리케이션 인증·작업자 메타데이터이며 연구항목·일반 Export·QC 원본값·로그 대상이 아니다. 연구 Excel의 서비스 Key·비밀번호·IP·CCTV·RTSP·개인 연락처는 기존대로 연구 DB Import에서 제외한다. 계정 비활성화는 과거 이력을 지우지 않는다.

V1 login_id는 Service에서 앞뒤 공백 제거 → 소문자 정규화 → 허용 문자·길이 검증 후 저장한다. 영문자·숫자·점(.)·밑줄(_)·하이픈(-)만 허용하고 내부 공백은 거부한다. 정규화된 길이는 4~50자이며 대소문자만 다른 ID는 동일 계정이다. login_id는 NOT NULL UNIQUE이고 별도 정규화 컬럼은 없다. 이 제한은 display_name·department에 적용하지 않는다.

## 34. 데이터 사전 신규 등록

UNMAPPED를 신규 dictionary item으로 등록할 때 확인:  

- standard_name
- internal_name
- category
- data_type
- unit
- description
- analyzable
- required
- nullable
- alias/source_scope

사용자 확인 후 등록한다.  

자동 생성 금지.  

## 35. 데이터 사전 변경

이미 데이터가 존재하는 항목의 의미/data_type/unit/internal_name을  
단순 변경하여 과거 데이터 의미를 바꾸지 않는다.  

의미가 변경되면:  

기존 item deprecated  
→ 새 item 생성  

방식을 우선한다.  

## 36. 데이터 사전 Import/Export

V1에서 향후 지원할 수 있는 선택적 기능으로 dictionary 자체의 Import/Export를 고려한다. 현재 구현이 확정되었거나 완료된 기능은 아니다.  

검증 대상:  

- dictionary version
- duplicate internal_name
- alias collision
- unit 존재
- category 존재

불완전한 사전을 그대로 적용하지 않는다.  

## 37. Export

V1 결과 내보내기는 Excel(소하천 조회 결과·QC 결과·보정/변경 이력·기초통계)과 PNG(그래프)다. PDF는 제외한다. 내부 PK·로그·민감정보·app_user 인증정보는 일반 Export에서 제외한다. 원본 Excel을 덮어쓰지 않으며 내보낸 사용자 파일을 프로그램이 자동 삭제하지 않는다.

연구항목 선택·필요한 provenance 옵션을 제공하되 app_user hash를 포함하지 않는다.

## 38. 재현성

새 테이블·컬럼을 추가하지 않고 import_history.settings_json에 Import 실행 당시 normalization 설정, mapping 관련 설정/식별정보, Import option, 관련 application/module version 등의 재현성 설정을 snapshot으로 저장할 수 있도록 한다.

실제 mapping 상세 provenance의 authoritative record는 import_column_mapping이다. settings_json의 필드는 Import 구현 전에 versioned contract로 정의한다. 같은 원본·사전 버전·매핑·정규화 규칙·프로그램 버전 조건에서 가능한 한 동일 결과를 만들고, 사용자 mapping 판단과 보정은 이력으로 추적한다.

## 39. 성능

정확성 및 provenance를 성능보다 우선한다.  

큰 파일에서는 향후:  

- sheet 단위 처리
- preview sampling
- 필요한 경우 chunk 처리

를 검토할 수 있다.  

성능 최적화를 이유로 검증 단계를 제거하지 않는다.  

## 40. 명시적 자동처리 금지 목록

- 원본 Excel 덮어쓰기
- stream_code 숫자 변환
- 이름만으로 자동 Join
- fuzzy matching 자동 확정
- 이상치 자동 삭제
- 결측 자동 보간
- 다른 출처값으로 자동 교체
- 최신 파일 자동 우선
- row shift 자동수정
- UNMAPPED 자동 dictionary 생성
- 불명확한 단위 자동환산
- parse 실패값을 0으로 처리
- 원본 characteristic_value overwrite
- representative 자동 변경
- 민감 운영정보 일반 DB 저장/Export

## 41. QC_RULES.md와의 관계

DATA_RULES.md:  
데이터를 어떻게 읽고/정리하고/매핑하고/저장 준비하는지 정의.  

QC_RULES.md:  
그 과정에서 어떤 문제를 탐지하고  
severity/review를 어떻게 관리하는지 정의.  

두 문서의 책임을 구분한다.  

QC_RULES.md에서 이미 정의된:  

- ERROR/WARNING/INFO
- review_status
- blocking과 severity 분리
- row alignment
- 민감정보 QC
- representative QC

를 따른다. ERROR/WARNING/INFO는 심각도이며 review_status와 별개다. QC 검토 상태의 정의와 변경 흐름은 QC_RULES.md를 기준으로 한다.  

## 42. 구현 전 확인사항

- [ ] 실제 Excel 파일별 header 구조 확인
- [ ] header normalization 규칙 확정
- [ ] 결측 표현 기본 목록 확정
- [ ] source_scope 정책 확정
- [ ] Import type별 필수항목 정의
- [ ] blocking validation 규칙 확정
- [ ] 민감정보 탐지 alias/keyword 목록 확정
- [x] 전체 관리코드 숫자·11자리·TEXT 및 Service 연결 검증 확정
- [x] 시스템 시각 UTC 저장 및 원본 timezone 추정 금지 확정
- [ ] dictionary 초기 표준항목 확정
- [ ] 단위 변환 초기 목록 확정
- [x] 현재 사용값 지정 및 Q1(characteristic_value_id FK·is_active) 확정

## 확인 필요사항

### QC_RULES.md와의 대조 결과

| 검토 영역 | 결과와 적용 기준 |
| --- | --- |
| 데이터 처리 흐름 | 충돌 없음. 기본 검증·Preview 단계와 저장 후 QC·보정 후 재검사를 구분한다. |
| blocking 정책 | 충돌 없음. severity와 차단 여부를 분리하고 Import type별 정책을 구현 전에 확정한다. |
| 관리코드 | 충돌 없음. 11자리 TEXT·선행 0을 보존하며, 확인된 구성요소로 생성하는 처리와 오류 자동수정을 구분한다. |
| representative | 충돌 없음. 활성 대표값은 조합당 최대 하나이며 사용자 판단·이력·캐시 재구축을 따른다. |
| 자동수정 금지 | 충돌 없음. 안전한 형식 정규화 외 의미 변경·삭제·보간·행 이동·자동 대표값 선택은 금지한다. |
| 민감정보 | 충돌 없음. 연구 DB·일반 Export에서 제외하고 Preview·QC·로그에 secret을 노출하지 않는다. |

### 확정된 저장 정책과 남은 구현 사항

V1에서는 UNMAPPED 컬럼의 모든 셀 값을 별도 raw/staging DB에 복제하지 않는다. source file metadata/hash, import, sheet, source column 위치, source header, normalized header와 mapping_status=UNMAPPED 등 메타데이터를 저장한다.

사용자가 컬럼 의미를 확정하면 원본 Excel을 다시 선택·참조하여 새 mapping으로 재Import한다. 원본 위치가 바뀌었으면 file hash 등으로 동일 파일 여부를 검증할 수 있도록 한다.

characteristic_value와 data_quality_issue를 범용 raw cell 저장소로 사용하지 않는다. raw_cell/staging/unmapped_value 테이블을 V1에 추가하지 않는다. 미매핑 컬럼에 민감 운영정보가 포함될 수 있으므로 원본 셀을 무조건 DB에 복제하지 않는다.

data_quality_issue의 rule_version_snapshot TEXT NULL과 rule_parameters_snapshot_json TEXT NULL에 issue 생성 당시 quality_rule.rule_version과 parameters_json을 snapshot으로 보존한다. rule_parameters_snapshot_json은 JSON 형식 TEXT다.

rule_id는 계속 quality_rule의 FK로 유지한다. snapshot은 issue 생성 당시의 재현성 정보이며 현재 quality_rule 값을 대신하는 live reference가 아니다. 규칙이 변경되어도 과거 결과의 규칙 버전과 parameter를 확인할 수 있어야 한다.

V1에서는 별도 QC review history 테이블을 추가하지 않는다. data_quality_issue는 현재 review_status와 검토 정보를, record_history는 상태 변경·사용자 보정·대표값 변경 등 중요 변경 이력을 관리한다.

QC issue를 삭제하지 않는다. 재검사에서 새로운 issue가 생성될 수 있으며 과거 issue는 기존 review 상태와 record_history를 함께 보존한다. issue 간 lineage 전용 FK는 V1에 추가하지 않으며 실제 사용에서 필요성이 확인되면 향후 확장한다.

다음 정책은 현재 schema를 변경하지 않고 해당 기능 구현 전에 확정한다.

- source_scope 세부 명명정책과 mapping_method 세부 허용값
- INTEGER의 3.0 허용 규칙과 REAL 비교 tolerance
- Unicode/장식문자 세부 normalization과 기본 결측문자 목록
- 현재 사용값은 characteristic_value_id에 연결된 활성 ERROR로 제한한다. Q1 schema 결정은 완료했으며 재검사 범위·중복 결과 처리는 Phase 7에서 정한다.
- outlier 알고리즘과 row alignment 실제 탐지 알고리즘
- Preview issue 영구 저장 범위

대표값은 동일 stream_code + dictionary_id에 활성 값 최대 하나, 변경이력 기록, 자동 대표값 변경 금지를 유지한다. ERROR/WARNING 등의 의미를 무시하여 자동 선택하지 않는다. 연구자료 근거가 필요한 범위·threshold는 임의 생성하지 않는다.

Import settings_json의 versioned contract는 Import 구현 전에 정의한다. 캐시 참조 구조·로그인 ID 유일성·QC 값 FK/활성 필드와 기본 DDL 방향은 확정되었다. 재검사 세부 계약 등은 DATABASE_DESIGN.md의 non-blocking TODO를 따른다. SQL 문서 검증과 실제 DDL 테스트를 구분한다.
