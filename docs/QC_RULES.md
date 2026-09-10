# 데이터 품질검사(QC) 규칙

이 문서는 `small-stream-research-tool`의 V1 QC 원칙, 규칙 분류, 심각도와 검토 상태, 사용자 검토 및 재검사 흐름을 정의한다. 현재는 설계 단계이며 기능·규칙·테스트의 구현 완료를 의미하지 않는다. QC는 연구자의 판단을 지원하며 원본값을 자동 수정하거나 삭제하지 않는다.

AGENTS.md와 PROJECT_OVERVIEW.md, ARCHITECTURE.md, DATABASE_DESIGN.md, DATA_RULES.md를 기준으로 한다. 확정된 저장 정책을 반영하며 수치 임계값이나 미확인 연구항목을 임의로 추가하지 않는다.

## 1. QC 목적

QC의 목적은 다음과 같다.  

- 데이터 구조 오류 탐지
- 식별자 오류 탐지
- 필수정보 누락 탐지
- 자료형 오류 탐지
- 단위 문제 탐지
- 중복 탐지
- 자료 간 불일치 탐지
- 이상값 탐지
- 행 정렬 이상 가능성 탐지
- 연구자의 검토 및 판단 기록
- 수정 이후 재검사 지원

QC 결과만으로 원본값을 자동 삭제하거나 수정하지 않는다.  

## 2. QC 기본 원칙

다음 원칙을 적용한다.  

1. 원본값 보존
2. 탐지와 수정 분리
3. severity와 review_status 분리
4. 이상치와 오류 구분
5. 자료 간 불일치와 오류 구분
6. 자동수정 금지
7. 검토 결과 이력 보존
8. 수정된 issue도 삭제하지 않음
9. QC 규칙과 버전을 추적 가능하게 함
10. 연구 의미가 불명확하면 확정 판정하지 않음

## 3. Severity

severity는 문제의 기술적/연구적 중요도를 나타낸다.  

V1:  

ERROR  
WARNING  
INFO  

### ERROR

정상적인 Import 또는 데이터 활용을 어렵게 만드는 명확한 문제.  

예:  

- 필수 관리코드 없음
- 관리코드 형식 오류
- 필수값의 명확한 자료형 변환 실패
- DB 무결성 위반 가능성

### WARNING

데이터는 보존할 수 있지만 연구자의 확인이 필요한 문제.  

예:  

- 동일 관리코드의 하천명 차이
- 자료 간 특성값 불일치
- 범위 이상 의심
- 이상치
- 행 정렬 이상 의심
- 단위 불일치

### INFO

오류라고 볼 수 없지만 사용자가 참고할 가치가 있는 상태.  

예:  

- 선택항목 결측
- 동일값 반복
- 자동 매핑 결과 관련 참고정보

중요:  
구체적인 severity는 개별 quality_rule에서 설정할 수 있어야 한다.  
위 예시를 모든 상황의 절대 기준으로 하드코딩하지 않는다.

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

### 활성 issue와 개별 값 연결

data_quality_issue.characteristic_value_id는 특정 값의 nullable FK이며 is_active=1인 issue만 현재 집계에 사용한다. 값이 없는 관리코드/Import 오류에서는 FK가 NULL일 수 있다. 성공한 재검사에서 기존 문제가 현재 문제에 해당하지 않으면 is_active=0으로 보존하고 새 문제는 새 행으로 추가한다. review_status 변경만으로 활성 여부를 바꾸지 않는다. WARNING+CONFIRMED+active와 ERROR+CORRECTED+inactive 모두 가능하다.

재검사 범위 내 과거 issue 비활성화와 새 issue 저장은 한 transaction으로 처리한다. 실패·중단한 재검사를 이유로 과거 issue를 일괄 비활성화하지 않는다. 반복 탐지·복수 값 대상 표현·실행 안내는 Phase 7 계약으로 정하며 DB schema 구현을 차단하지 않는다.

## 4. Review Status

review_status는 연구자의 검토 진행 상태다.  

V1:  

UNREVIEWED  
IN_REVIEW  
CONFIRMED  
CORRECTED  
DEFERRED  

의미:  

### UNREVIEWED

아직 검토하지 않음  

### IN_REVIEW

검토 중  

### CONFIRMED

QC가 탐지한 상태를 확인했지만 원본값을 수정하지 않음.  
실제 오류가 아닌 정상적인 값이라고 확인한 경우도 포함할 수 있다.  

### CORRECTED

검토 결과 별도의 보정값/수정값을 등록함.  

### DEFERRED

현재 자료만으로 판단하기 어려워 추후 확인하기로 함.  

severity와 review_status는 독립적이다.  

예:  
ERROR + CORRECTED  
WARNING + CONFIRMED  
WARNING + DEFERRED  
등이 가능하다.  

## 5. QC Rule 구조

quality_rule은 최소 다음 개념을 가진다.  

- rule_code
- rule_name
- target_type
- dictionary_id
- rule_type
- default_severity
- parameters_json
- description
- rule_version
- is_enabled

QC 로직은 코드에 구현되더라도  
규칙의 식별자와 버전을 DB에서 추적 가능해야 한다.  

규칙 이름만으로 로직을 판단하지 않는다.  

## 6. QC 실행 시점

QC는 여러 시점에서 실행될 수 있다.  

### A. Import Preview 이전/중간

- 구조
- header
- mapping
- 관리코드
- 자료형
- 필수값

### B. Import 직전

- blocking validation

### C. Import 이후

- 중복
- 자료 간 비교
- 대표값 관련 상태
- 이상치
- 범위
- 행 정렬 패턴

### D. 사용자 보정 이후

- 재검사

### E. 향후 분석 전

- 분석에 필요한 변수의 품질상태 확인

동일 규칙이 모든 단계에서 반드시 실행되어야 한다는 의미는 아니다.  

## 7. Blocking과 Severity 구분

ERROR라고 해서 모든 경우 전체 파일 Import를 막는다고 가정하지 않는다.  

blocking 여부와 severity는 별개의 개념으로 설계할 수 있다.  

예:  

파일 전체 Import를 막을 가능성이 높은 경우:  

- 데이터 시트 자체를 결정할 수 없음
- 필수 식별구조 전체 없음
- DB transaction 불가
- schema incompatibility

행 단위 거부 가능:  

- 특정 행의 관리코드 생성 불가능
- 특정 행의 필수값 치명적 오류

저장 후 QC 가능:  

- 하천명 불일치
- 일부 특성값 불일치
- 이상치
- 선택항목 결측

정확한 blocking 정책은 Import type별로 정의 가능해야 한다.  

## 8. 관리코드 QC

검사 후보:  

- `MC001`: 관리코드 NULL
- `MC002`: 관리코드 길이 오류
- `MC003`: 허용되지 않은 문자
- `MC004`: 구성요소 누락
- `MC005`: 구성요소 길이 오류
- `MC006`: 구성요소 연결값과 stream_code 불일치
- `MC007`: 동일 Import 내 관리코드 중복
- `MC008`: 기존 DB와 관리코드 충돌

MC001~MC008은 검사 후보를 구분하기 위한 예시 코드다. 구현 전에 최종 rule_code 체계를 확정한다.  

중요:  
관리코드는 TEXT다.  
leading zero 손실 가능성도 탐지 대상이다.  

코드 오류를 자동 수정하지 않는다.  

## 9. 필수값 QC

검사:  

- required field NULL
- required field blank
- Import type별 필수항목 누락

data_dictionary.required만으로 모든 상황을 결정하지 않는다.  

Import type별 required rule을 둘 수 있도록 한다.  

## 10. 자료형 QC

검사 예:  

- REAL 변환 실패
- INTEGER 변환 실패
- DATE 변환 실패
- DATETIME 변환 실패
- 예상하지 않은 문자열
- 정수 항목에 비정수값

Parse 실패값을 0으로 저장하지 않는다.  

원본값을 issue에 남길 수 있도록 한다.  


value_number, value_integer, value_text, value_date 중 **정확히 하나만 NON-NULL**이어야 한다. characteristic_value는 실제 유효한 값을 저장한다. SQLite CHECK 표현은 DATABASE_DESIGN.md의 제약 감사에서 확인했다. 실제 DDL 실행 검증은 Phase 1에서 수행한다.

결측이면 NULL value를 가진 characteristic_value 행을 생성하지 않는 것을 원칙으로 한다. 필수값 결측은 validation/QC issue로 처리한다. data_dictionary.nullable은 해당 항목의 결측 허용 여부이며 NULL characteristic_value 행 생성 허가를 뜻하지 않는다.

Service/Validator는 data_dictionary.data_type과 typed value 컬럼의 일치를 검증한다. DATE와 DATETIME 모두 V1에서는 value_date TEXT를 사용하며 Validator가 구분한다. DATE는 YYYY-MM-DD, DATETIME은 ISO 8601 형식이다. 원본 DATETIME에 timezone이 없으면 임의로 추가하지 않는다. 별도 value_datetime 컬럼은 추가하지 않는다.

## 11. 중복 QC

중복 유형을 구분한다.  

### A. 동일 Import 내 동일 stream_code

### B. 동일 stream_code + dictionary_id

### C. 동일 source에서 동일 특성값 반복

### D. 서로 다른 source에서 동일값

### E. 서로 다른 source에서 서로 다른 값

D는 반드시 오류가 아니다.  

여러 연구자료가 같은 값을 포함하는 정상적인 상황일 수 있다.  

중복 탐지 결과만으로 데이터를 삭제하지 않는다.

다른 Import에 동일 stream_code가 존재해도 자동 중복 오류가 아니다. 여러 출처·시점의 값 보존을 전제로 실제 중복·충돌의 의미를 구분한다.

## 12. 소하천명 불일치 QC

동일 stream_code에 서로 다른 stream_name이 존재하면  
WARNING 후보로 처리한다.  

자동 수행 금지:  

- 더 긴 이름 선택
- 최신 파일 이름 선택
- 문자열 유사도 기준 선택
- 다수결 선택
- 접미사 제거 후 자동 동일화

두 이름과 출처를 사용자에게 보여주고 판단하도록 한다.  

## 13. 특성값 불일치 QC

동일:  

stream_code + dictionary_id  

에 서로 다른 값이 존재할 수 있다.  

비교 시 고려:  

- source
- reference_year
- unit
- dictionary version
- original value
- normalized value

단위가 다른 경우 단위 정규화 가능 여부를 먼저 확인한다.  

서로 다른 값이라고 해서 자동으로 최신값을 representative로 만들지 않는다.  

## 14. 결측 QC

결측을 다음과 같이 구분한다.  

필수값 결측:  
ERROR 또는 해당 rule severity  

선택값 결측:  
INFO 또는 검사를 생략할 수 있음  

분석 필수변수 결측:  
분석 실행 단계에서 별도 WARNING/ERROR 가능  

결측값 자동 보간 금지.  

## 15. 단위 QC

검사 예:  

- source unit 없음
- source unit과 표준 unit 차이
- 등록되지 않은 unit
- conversion rule 없음
- conversion 실패
- 동일 항목에서 비정상적으로 여러 단위 사용

단위 차이가 있다고 무조건 오류로 판단하지 않는다.  

명시적인 conversion rule이 있다면  
표준단위로 변환할 수 있다.  

원본값/원본단위는 보존한다.  

## 16. 범위 검사

물리적 또는 연구적으로 명확한 범위가 있는 항목에  
range rule을 적용할 수 있다.  

예:  
위도/경도처럼 일반적인 기술 범위가 명확한 데이터.  

하지만:  

유역면적  
하상경사  
하천연장  
유량  
수위  

등의 실제 연구값에 대해  
근거 없는 전역 최소/최대값을 임의 설정하지 않는다.  

범위 규칙은:  

- 자료 근거
- 연구 기준
- 명시적 설정

이 있을 때 등록한다.  

## 17. 이상치 QC

이상치 탐지와 오류 판정을 분리한다.  

향후 가능한 통계 방법:  

- IQR
- Z-score
- robust Z-score
- percentile
- 그룹별 분포 비교

V1에서 모든 방법을 구현할 필요는 없다.  

중요:  
자연재난/수문 데이터의 극단값은 중요한 실제 현상일 수 있다.  

따라서:  
OUTLIER DETECTED  
≠  
INVALID DATA  

이상치 자동 삭제/수정 금지.  

## 18. Cross-source QC

여러 파일/연구자료를 비교할 때:  

기본 JOIN KEY:  
stream_code  

비교 대상 예:  

- stream_name
- characteristic value
- unit
- reference year
- 존재 여부

파일 수정일이 최신이라는 이유만으로  
값을 정답으로 판정하지 않는다.  

자료의 연구 시점과 출처 의미를 함께 봐야 한다.  

## 19. Row Alignment QC

행 정렬 이상은 중요한 QC 유형으로 둔다.  

탐지 후보 패턴:  

- 첫 식별자 행의 특정 특성구간이 비어 있음
- 다음 행부터 특성값이 반복적으로 한 행 offset
- 마지막에 식별자 없는 특성값 행 존재
- 기준자료와 비교했을 때 특정 열 구간이 일정한 row offset으로 일치
- 식별정보와 특성정보의 행 개수가 비정상적으로 어긋남

결과 예:  
ROW_ALIGNMENT_SUSPECTED  

중요:  
프로그램은 자동으로 행을 이동시키지 않는다.  

탐지 결과에는 가능하면:  

- 대상 sheet
- 의심 시작/종료 column
- 의심 row 범위
- 예상 offset
- 비교 근거
를 보여줄 수 있도록 한다.  

다만 근거가 충분하지 않으면 offset을 확정값처럼 표시하지 않는다.  

## 20. 민감정보 QC

Import 대상 Excel에서  
분석 DB에 부적절한 운영정보 컬럼을 탐지할 수 있다.  

예:  

- API/service key
- password
- 인증정보
- IP
- CCTV 접속정보
- RTSP URL
- 개인 연락처

탐지 시:  
SECURITY 또는 SENSITIVE_DATA 계열 issue를 만들 수 있다.  

기본 동작:  
민감정보 가능성이 있는 컬럼을 일반 연구 DB Import 제외 후보로 표시한다. 분석에 불필요한 운영·민감정보로 확인된 값은 기존 보안 원칙에 따라 main research DB와 일반 Export에서 제외한다.  

민감 원본값 자체를 QC message나 로그에 노출하지 않는다. data_quality_issue의 original_value, compare_value, review_note 등에도 secret을 복사하지 않는다.  

예:  
"민감정보 가능성이 있는 컬럼이 탐지됨"  
처럼 표시하고 실제 secret 값을 출력하지 않는다.

로컬 app_user 인증 메타데이터는 연구 Excel에서 유입되는 운영 인증정보와 분리한다. 비밀번호 평문·hash를 QC issue·로그·일반 Export에 노출하지 않는다.

## 21. 위치정보 QC

소하천 시점/종점 등의 좌표가 존재하는 경우  
기술적으로 명확한 좌표 형식 검사를 할 수 있다.  

값이 있는 source/end latitude에는 -90~90, longitude에는 -180~180의 DB 기본 형식 CHECK를 적용한다. 기존 NULL 허용을 유지하며 연구 임계값으로 간주하지 않는다.

좌표계가 명확하지 않은 자료를  
자동으로 WGS84라고 가정하지 않는다.  

좌표계 변환은 명시적인 CRS 정보가 있을 때만 수행한다.  

V1에서 GIS 분석은 하지 않는다.  

## 22. Reference Year QC

reference_year가 존재할 경우:  

- 정수형 여부
- 비정상 형식
- 서로 다른 출처의 연도 차이

등을 확인할 수 있다.  

연도가 다르다는 사실 자체는 오류가 아니다.  

특성정보가 다른 이유를 설명하는 중요한 provenance가 될 수 있다.  

## 23. Representative QC

대표값 관련 검사:  

- 동일 stream_code + dictionary_id에 활성 대표값 2개 이상
- is_representative=1인 characteristic_value가 비활성 상태이거나 비활성 값을 대표값으로 사용하는 상태
- representative 변경 후 cache 불일치
- representative 없이 분석 필수항목 사용 시도

첫 번째는 DB partial unique index에서도 방지하는 방향을 사용한다.  

대표값이 없다고 항상 오류는 아니다.  
분석 목적에 따라 필요 여부가 다르다.

UI의 **현재 사용값**은 기존 is_representative로 선택한 값이다. characteristic_value는 원본값과 새로 추가한 보정값을 보존하고, record_history는 보정·선택 변경을 기록하며, stream_characteristic은 현재 사용값의 ID를 보관하고 실제 값은 characteristic_value에서 조회하는 참조 캐시다. 별도 현재값 테이블을 만들지 않는다.

동일 stream_code + dictionary_id에 활성 현재 사용값은 최대 하나다. 새 자료 Import만으로 현재 사용값을 변경하지 않으며 사용자가 명시적으로 선택한다. 선택할 characteristic_value_id에 severity='ERROR' AND is_active=1인 issue가 있으면 지정할 수 없다. 활성 WARNING/INFO는 연구자가 확인한 뒤 명시적으로 지정할 수 있다. review_status 변경만으로 ERROR 차단을 해제하지 않는다. 기존 값을 삭제·덮어쓰지 않고 characteristic_value.is_representative 변경·stream_characteristic 참조 캐시 갱신·record_history 기록을 하나의 업무 transaction으로 처리한다. 어느 단계든 실패하면 전부 rollback하며 자동 선정은 금지한다.

## 24. Cache QC

stream_characteristic은 (stream_code, dictionary_id)별 현재 characteristic_value_id와 updated_at만 보관하는 재구축 가능한 참조 캐시다. 실제 값은 characteristic_value에서 조회하며 고정 연구 특성 컬럼이나 값 복제는 두지 않는다. 활성 is_representative를 기준으로 재구축하고 사용자 직접 수정은 금지한다.  

검사 가능:  

- 활성 representative ID와 cache.characteristic_value_id 불일치
- cache의 stream_code/dictionary_id와 참조 값의 키 불일치
- cache에 존재하지만 representative 없음
- representative 존재하지만 cache 누락

문제가 있으면 원본 characteristic_value를 기준으로  
cache rebuild를 수행할 수 있다.  

cache 참조를 기준으로 원본값이나 선택 상태를 역으로 수정하지 않는다.  

## 25. Dictionary QC

검사 예:  

- duplicate internal_name
- alias collision
- 존재하지 않는 unit 참조
- 존재하지 않는 category 참조
- deprecated item 자동매핑 시도
- 동일 source_scope alias 충돌
- data_type과 저장 typed value 불일치

DB constraint + Service validation을 함께 사용한다.  

## 26. Import Mapping QC

검사:  

- 필수 컬럼 UNMAPPED
- 하나의 source column이 여러 dictionary item에 확정 매핑
- 여러 source column이 하나의 필수 item에 중복 매핑
- ambiguous mapping
- inactive/deprecated dictionary item 매핑
- unit incompatible mapping

자동 fuzzy matching은 확정 매핑으로 사용하지 않는다.  


V1에서는 UNMAPPED 컬럼의 모든 셀 값을 별도 raw/staging DB에 복제하지 않는다. source file metadata/hash, import, sheet, source column 위치, source header, normalized header와 mapping_status=UNMAPPED 등 메타데이터를 저장한다.

사용자가 컬럼 의미를 확정하면 원본 Excel을 다시 선택·참조하여 새 mapping으로 재Import한다. 원본 위치가 바뀌었으면 file hash 등으로 동일 파일 여부를 검증할 수 있도록 한다.

characteristic_value와 data_quality_issue를 범용 raw cell 저장소로 사용하지 않는다. raw_cell/staging/unmapped_value 테이블을 V1에 추가하지 않는다. 미매핑 컬럼에 민감 운영정보가 포함될 수 있으므로 원본 셀을 무조건 DB에 복제하지 않는다.

## 27. QC Issue 저장

data_quality_issue에 가능한 범위에서 저장:  

- rule
- import
- sheet
- stream
- dictionary item
- source row
- source column
- characteristic_value_id(특정 authoritative 값이면 연결)
- is_active(현재 판정/과거 보존)
- issue type
- severity
- original value
- compare value
- message
- review status

모든 issue가 모든 FK를 가져야 하는 것은 아니다.  

예:  
잘못된 stream_code는 small_stream FK를 만들 수 없으므로  
stream_code가 NULL일 수 있다.  

필요한 원본 잘못된 값은 original_value 등에 보존한다. 단, 민감정보 제외 원칙이 우선하며 secret을 오류 보존 목적으로 저장하지 않는다.  


### 규칙 snapshot과 위치

data_quality_issue의 rule_version_snapshot TEXT NULL과 rule_parameters_snapshot_json TEXT NULL에 issue 생성 당시 quality_rule.rule_version과 parameters_json을 snapshot으로 보존한다. rule_parameters_snapshot_json은 JSON 형식 TEXT다.

rule_id는 계속 quality_rule의 FK로 유지한다. snapshot은 issue 생성 당시의 재현성 정보이며 현재 quality_rule 값을 대신하는 live reference가 아니다. 규칙이 변경되어도 과거 결과의 규칙 버전과 parameter를 확인할 수 있어야 한다.

Import 출처는 source_file → import_history → import_sheet → import_column_mapping → 원본 source column으로 추적한다.

characteristic_value는 **mapping_id와 source_row**를 함께 사용하여 원본 Excel의 행·열 출처를 식별한다. mapping_id는 import_column_mapping.mapping_id를 참조한다. Import 값은 가능한 한 mapping_id를 저장한다. USER_CORRECTION / MANUAL / DERIVED 등 원본 Excel column mapping이 없는 값은 NULL을 허용한다.

characteristic_value에 source_file_id나 source_column을 중복 저장하지 않는다. Service는 mapping_id가 가리키는 import_sheet와 characteristic_value.import_sheet_id가 일치하고, mapping이 속한 import와 characteristic_value.import_id가 일치하는지 검증한다. import_id와 import_sheet_id가 함께 있으면 같은 Import 소속인지도 검증한다. 과도한 DB trigger는 사용하지 않는다.

DB provenance의 source_row, source_column_index, source_column 등 Excel 사용자 위치는 원칙적으로 **1-based**를 사용한다. Python/openpyxl/pandas 등 처리 도구의 내부 index 기준을 확인하여 저장 경계에서 명확하게 변환한다. 0-based 내부 index와 혼동하지 않는다. sheet_name을 주요 provenance로 사용하고 sheet_index는 표시·순서 보조정보로 구분한다.

시스템 생성 reviewed_at·created_at 등은 UTC ISO 8601 TEXT로 저장하며 원본 연구자료 timezone은 추정하지 않는다.

작업자 연결은 import_history.created_by_user_id, data_quality_issue.reviewed_by_user_id, record_history.actor_user_id에서만 추가하며 모두 app_user.user_id를 참조한다. 세 FK는 NULL을 허용한다(미검토 QC, 기존/작업자 미상 기록 등). 다만 새 로그인 사용자의 Import 실행·QC 검토·중요 변경은 Service가 해당 사용자 ID를 반드시 기록하며 임의 NULL로 누락하지 않는다.

세 사용자 FK의 ON DELETE는 RESTRICT로 설계한다. 계정은 물리 삭제 대신 is_active=0으로 비활성화하고 기존 사용자 행·표시정보·FK를 보존한다. CASCADE DELETE나 SET NULL로 과거 작업자를 지우지 않는다. record_history.changed_by는 기존 비구조화 작업자 텍스트로 유지하며 새 작업의 기준 식별자는 actor_user_id다.

검토자·검토시각과 자동 QC 결과를 구분한다.

## 28. QC 메시지

사용자용 QC 메시지는:  

- 무엇이 문제인지
- 어느 자료인지
- 어느 위치인지
- 무엇과 비교했는지
- 사용자가 무엇을 확인해야 하는지

를 이해할 수 있도록 작성한다.  

나쁜 예:  
"Validation failed"  

좋은 방향:  
"관리코드 구성요소를 연결한 값과 원본 관리코드가 일치하지 않습니다."  

민감정보는 메시지에 출력하지 않는다.  

## 29. 사용자 검토

QC 화면에서 향후 가능한 작업:  

- issue 상세보기
- 원본 출처 확인
- 비교값 확인
- CONFIRMED
- CORRECTED
- DEFERRED
- representative 변경
- 사용자 보정값 등록
- 재검사

QC issue를 사용자가 단순 삭제하는 기능은 기본 제공하지 않는다.

QC 화면에서 값을 덮어쓰지 않고 08 특성정보 보정 관리로 이동한다. 사용자에게 issue·작업이력 수정/삭제 기능을 제공하지 않는다. 검토 상태 변경은 허용된 Service 업무로 기록한다.

## 30. CONFIRMED 의미

CONFIRMED는 반드시  
"원본 데이터가 틀렸음"을 의미하지 않는다.  

예:  
통계적으로 이상치지만 실제값임  
→ CONFIRMED  

자료 간 이름이 다르지만 출처별 명칭 차이임  
→ CONFIRMED  

즉 QC 탐지 결과를 연구자가 확인했다는 의미다.  

## 31. CORRECTED 처리

CORRECTED 시:  

원본값 유지  
→ 보정값 별도 생성  
→ record_history 기록  
→ QC issue review_status = CORRECTED  
→ 관련 QC 재실행  
→ 보정값의 QC와 지정 가능 조건 확인  
→ 사용자가 명시적으로 선택한 경우 representative 변경  

원본 characteristic_value를 overwrite하는 방식은 기본으로 사용하지 않는다.  


V1에서는 별도 QC review history 테이블을 추가하지 않는다. data_quality_issue는 현재 review_status와 검토 정보를, record_history는 상태 변경·사용자 보정·대표값 변경 등 중요 변경 이력을 관리한다.

QC issue를 삭제하지 않는다. 재검사에서 새로운 issue가 생성될 수 있으며 과거 issue는 기존 review 상태와 record_history를 함께 보존한다. issue 간 lineage 전용 FK는 V1에 추가하지 않으며 실제 사용에서 필요성이 확인되면 향후 확장한다.

## 32. DEFERRED 처리

현재 자료만으로 판단할 수 없을 경우 사용한다.  

review_note에:  

- 추가 확인이 필요한 자료
- 판단이 어려운 이유

등을 기록할 수 있다.  

DEFERRED issue는 향후 필터링하여 다시 검토할 수 있어야 한다.  

## 33. QC 재실행

다음 경우 관련 QC 재실행을 고려한다.  

- 사용자 보정
- representative 변경
- dictionary mapping 변경
- alias 변경
- unit conversion rule 변경
- 새로운 비교자료 Import

모든 QC를 항상 전체 DB 대상으로 재실행할 필요는 없다.  

영향받은 범위만 재실행할 수 있는 구조를 고려한다.  


V1에서는 별도 QC review history 테이블을 추가하지 않는다. data_quality_issue는 현재 review_status와 검토 정보를, record_history는 상태 변경·사용자 보정·대표값 변경 등 중요 변경 이력을 관리한다.

QC issue를 삭제하지 않는다. 재검사에서 새로운 issue가 생성될 수 있으며 과거 issue는 기존 review 상태와 record_history를 함께 보존한다. issue 간 lineage 전용 FK는 V1에 추가하지 않으며 실제 사용에서 필요성이 확인되면 향후 확장한다.

### 작업이력의 책임

record_history는 중요한 연구·운영 변경을 기록한다: Import, QC 검토, 특성정보 보정, 현재 사용값 변경, 비활성화·데이터 복원, DB 백업·DB 복원 및 기타 중요한 연구 데이터 변경. 검색·정렬·페이지 이동·일반 조회·단순 필터·그래프 유형 변경은 기록하지 않는다. 사용자에게 이력 수정·삭제 기능을 제공하지 않는다.

홈·마이페이지와 작업이력은 record_history를 공유하고 actor_user_id로 현재 app_user.display_name을 조회한다. V1 사용자명 snapshot 필드는 추가하지 않는다. DB Restore 전에 자동 안전백업을 만들고, 성공 후 새 현재 DB의 record_history에 복원 작업을 기록한다. 데이터 비활성화 복원은 RESTORE, DB 전체 복원은 DB_RESTORE로 구분한다. Backup/Restore 기술과 이벤트 대상 표현·복원된 DB의 작업자 연결은 Phase 14 전에 확정한다. 원래 DB의 최신 이력이 복원 DB에 자동 합쳐진다고 가정하지 않는다.

## 34. QC Rule Version

data_quality_issue의 rule_version_snapshot TEXT NULL과 rule_parameters_snapshot_json TEXT NULL에 issue 생성 당시 quality_rule.rule_version과 parameters_json을 snapshot으로 보존한다. rule_parameters_snapshot_json은 JSON 형식 TEXT다.

rule_id는 계속 quality_rule의 FK로 유지한다. snapshot은 issue 생성 당시의 재현성 정보이며 현재 quality_rule 값을 대신하는 live reference가 아니다. 규칙이 변경되어도 과거 결과의 규칙 버전과 parameter를 확인할 수 있어야 한다.

## 35. QC Rule 활성/비활성

quality_rule.is_enabled를 사용한다.  

규칙 비활성화는 과거 issue를 삭제하거나 issue.is_active를 일괄 변경하지 않는다.  

과거 결과는 이력으로 유지한다.  

## 36. QC와 Import 관계

Preview 단계의 문제와  
DB Import 후 생성되는 issue를 구분할 수 있어야 한다.  

모든 Preview 오류를 반드시 DB issue로 영구 저장해야 하는지는  
구현 단계에서 결정할 수 있다.  

단,  
실제 Import가 수행된 자료의 중요한 QC 결과는  
추적 가능해야 한다.  


### 확정된 Import transaction 경계

### A. Import 실행 이력 생성

import_history의 status를 RUNNING으로 기록하고 **별도 transaction에서 COMMIT**한다.

### B. 실제 데이터 Import

import_sheet, import_column_mapping, small_stream 신규/관련 반영, characteristic_value 및 해당 Import와 함께 확정되어야 하는 관련 자료를 **하나의 업무 transaction**으로 처리하는 것을 기본으로 한다. 성공하면 COMMIT, 실패하면 ROLLBACK한다.

### C. 결과 이력 갱신

- 성공 후 별도 transaction에서 import_history.status를 SUCCESS로 갱신하고 finished_at을 기록한다.
- 실패 후 별도 transaction에서 import_history.status를 FAILED로 갱신하고 error_code, error_message, finished_at을 기록한다.

실제 데이터 transaction이 rollback되어도 Import 시도와 실패 이력은 보존한다. rollback된 import_sheet/import_column_mapping 등의 FK를 data_quality_issue가 강제로 참조하게 하지 않는다. Preview issue와 실패 진단정보의 영구 보존 범위는 별도 구현정책으로 정할 수 있다. V1에 import_error 테이블을 추가하지 않는다.

Import 이력은 실제 DB 반영 시작 시 생성하며 Preview 작업 재개용 저장소가 아니다. Import SUCCESS + QC 확인 필요를 허용한다. Draft/Workspace는 V1 로컬 workspace 파일로 연구 DB와 분리한다. 원본 존재·hash 확인 후 재개하며 원본 셀을 복제하지 않는다.

## 37. QC와 분석 관계

향후 분석 실행 시  
QC 상태를 참고할 수 있도록 한다.  

예:  
분석 변수에 ERROR 상태 데이터 포함  
→ 사용자 경고  

하지만:  
WARNING/INFO 데이터를 무조건 분석에서 제외하지 않는다.  

분석 제외 정책은 연구자가 확인할 수 있어야 한다.  

향후 분석 재현성 기능에서는  
어떤 QC 상태의 데이터를 사용했는지 기록하는 것을 고려한다.  

## 38. 초기 QC Rule 후보

V1 초기 구현 후보를 우선순위로 구분한다.  

### Priority A

- 관리코드 형식
- 관리코드 구성요소 일치
- 필수값
- 자료형
- 중복 관리코드
- 필수 매핑
- 민감정보 컬럼 탐지

### Priority B

- 하천명 불일치
- 특성값 불일치
- 단위 불일치
- dictionary mapping 문제
- representative 무결성

### Priority C

- 이상치
- 범위
- row alignment
- reference year 비교
- cache consistency

중요:  
Priority는 구현 순서이며  
연구적 중요도의 절대 순위가 아니다.  

## 39. 자동수정 금지 목록

QC Engine은 다음을 자동 수행하지 않는다.  

- stream_code 수정
- 하천명 수정
- 행 이동
- 특성값 교체
- 이상치 삭제
- 결측값 보간
- 단위 추정
- representative 자동 변경
- 최신자료 자동 선택
- fuzzy matching 자동 확정
- 원본값 overwrite
- QC issue 삭제

## 40. 테스트해야 할 QC 사례

향후 테스트 fixture로 최소 다음을 재현한다.  

- 정상 11자리 코드
- 선행 0 포함 코드
- 10자리/12자리 오류
- 구성요소 불일치
- 중복 코드
- 필수값 누락
- 숫자 parse 실패
- 하천명 불일치
- 동일 특성값
- 다른 특성값
- 단위 불일치
- UNMAPPED
- alias collision
- 이상치 후보
- row shift 의심 패턴
- 민감정보 header
- representative 중복 시도
- corrected issue
- deferred issue

실제 연구자료의 민감정보를 fixture에 복사하지 않는다.  

## 41. 현재 실제 자료에서 얻은 설계 교훈

특정 실제 파일명이나 민감정보를 포함하지 않고, 제공된 연구 맥락에서 얻은 일반화된 설계 교훈만 기록한다. 이 문서 작성 과정에서 실제 연구파일을 새로 검사한 것은 아니다.  

- 관리코드가 자료 연결의 핵심임
- 이름만으로 자료를 연결하면 위험함
- 다중 행/병합 header 처리가 필요함
- 서로 다른 자료에서 특성값 차이가 발생할 수 있음
- 일정한 row offset 형태의 정렬 이상 가능성이 있음
- 운영정보가 연구 데이터와 같은 Excel에 존재할 수 있음

이 항목들은 특정 파일의 오류를 모든 자료의 일반적 오류로  
확정한다는 의미가 아니다.  

## 확인 필요사항

DATA_RULES.md와의 대조를 완료했다. 원본 컬럼 추적은 mapping_id와 source_row로, UNMAPPED는 메타데이터 보존과 원본 재Import로, QC rule version은 issue snapshot으로 확정했다. QC 검토 이력은 record_history를 사용하고 lineage 전용 FK와 별도 history 테이블은 추가하지 않는다.

다음 정책은 현재 schema를 변경하지 않고 해당 기능 구현 전에 확정한다.

- source_scope 세부 명명정책과 mapping_method 세부 허용값
- INTEGER의 3.0 허용 규칙과 REAL 비교 tolerance
- Unicode/장식문자 세부 normalization과 기본 결측문자 목록
- 현재 사용값은 characteristic_value_id에 연결된 활성 ERROR로 제한한다. Q1 schema 결정은 완료했으며 재검사 범위·중복 결과 처리는 Phase 7에서 정한다.
- outlier 알고리즘과 row alignment 실제 탐지 알고리즘
- Preview issue 영구 저장 범위

대표값은 동일 stream_code + dictionary_id에 활성 값 최대 하나, 변경이력 기록, 자동 대표값 변경 금지를 유지한다. ERROR/WARNING 등의 의미를 무시하여 자동 선택하지 않는다. 연구자료 근거가 필요한 범위·threshold는 임의 생성하지 않는다.

blocking의 severity 분리 원칙은 유지하며 Import type별 최종 blocking rule은 해당 기능 구현 전에 정한다. Q1의 값 FK·활성 필드·현재값 제한은 확정되었다. 재검사 범위 등 후속 Service 상세만 non-blocking TODO로 관리한다.

## 42. 구현 전 확인사항

- [ ] QC rule_code 최종 명명규칙 확정
- [ ] Import type별 blocking rule 확정
- [ ] 필수항목 목록 확정
- [x] 전체 관리코드 숫자·11자리 형식 및 구성요소 Service 검증 확정
- [ ] 기본 range rule 근거 확인
- [ ] 초기 outlier 방법 확정
- [ ] row alignment 탐지 알고리즘 확정
- [ ] 민감정보 header 탐지 목록 확정
- [x] 현재 사용값 지정 및 Q1(characteristic_value_id FK·is_active) 확정
- [ ] QC 재실행 범위 정책 확정
- [x] rule_version_snapshot 및 rule_parameters_snapshot_json 보존 확정
- [ ] Preview issue 영구저장 범위 결정
