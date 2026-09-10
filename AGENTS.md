# small-stream-research-tool 마스터 개발지침

이 문서는 소하천 연구지원 프로그램의 개발 범위, 데이터 처리 원칙, 아키텍처 방향과 작업 규칙을 정의한다. 빠른 구현보다 데이터 정확성, 추적성, 재현성, 유지보수성을 우선한다.

## 적용 범위
- 이 파일은 프로젝트 루트와 모든 하위 디렉터리에 적용한다.
- 하위 디렉터리에 별도의 `AGENTS.md`가 있으면 해당 범위의 구체적인 지침을 함께 따른다.
- 사용자의 명시적인 요청을 우선한다.

## 프로젝트 현황과 지침의 사용

- 현재는 소스 코드, 빌드 설정, 테스트 설정이 없는 초기 저장소이며, Phase 0 구현 전이다.
- 아래 기술 스택은 예정 사항이다. 실제 설치 여부와 실행 명령은 프로젝트 설정을 확인하며 추측하지 않는다.
- Phase 목록은 개발 순서이며 전체 구현을 자동으로 허가하는 지시가 아니다. 매 작업은 사용자가 요청한 범위에서 수행한다.
- 현재 6개 설계문서가 있으며 작업 시 실제 경로와 내용을 확인한다.
- 소스 코드와 세부 문서 생성은 각각 요청된 작업에서 수행한다.

## 프로젝트 목적
프로젝트명: small-stream-research-tool
사용자 표시명: 소하천 데이터 관리(NDMI)
Python 패키지명: small_stream_research_tool

로컬 계정 app_user와 작업자 추적을 V1에 포함한다. 기존 18개 연구·기반 테이블에 app_user를 더한 확정 V1 테이블 수는 19개다. Import Draft/Workspace는 V1 작업 이어하기 기능으로 연구 DB 밖의 로컬 workspace 파일에 저장한다. 원본 전체 셀을 복제하지 않고 재개 시 파일 존재·hash를 검증하며, 이동·불일치 시 원본 재지정을 요구한다. Preview·매핑에서는 import_history를 생성하지 않는다.

국립재난안전연구원의 소하천 관련 연구업무를 지원하기 위한 Windows용 로컬·오프라인 연구지원 프로그램이다.

최종 목표 흐름:

원본 Excel
→ 자료 구조 인식
→ 컬럼 표준화 및 매핑
→ 소하천 관리코드 검증
→ 데이터 품질검사(QC)
→ 소하천 DB 구축
→ 데이터 조회·추출
→ 통계분석·시각화
→ 향후 연구모형 분석
→ 결과 및 분석이력 관리

모든 기능을 한 번에 구현하지 않는다.

V1의 핵심 범위:
- 소하천 기본정보 및 특성정보 DB
- Excel 파일 등록/Import
- 다중 시트 및 다중 행 헤더 대응
- 데이터 사전
- 컬럼 자동 매핑
- 미등록 컬럼 관리
- 소하천 관리코드 생성·검증
- QC
- 출처 및 Import 이력
- 대표 특성값
- 수정 이력
- DB 조회
- 기본 통계
- 기본 그래프
- Excel/PNG 결과 출력

강우·수위·유량 시계열, 홍수사상, 노모그래프, 비선형 최적화, GIS, ML은 향후 확장 영역이며 명시적인 요청 없이 V1에 구현하지 않는다.

## 핵심 데이터 원칙
1. 정확성과 추적성을 기능 수보다 우선한다.

2. 원본 Excel을 수정하거나 덮어쓰지 않는다.

3. 연구자료의 값이나 컬럼 의미를 임의로 추정하지 않는다.

4. 의미가 확인되지 않은 Excel 컬럼은 표준항목으로 임의 등록하지 않고 UNMAPPED 상태로 처리한다.

5. 자동 검출과 자동 수정을 구분한다.

허용 가능한 자동 처리:
- 헤더 공백 등 형식 정규화
- 사전에 등록된 컬럼 별칭 적용
- 사전에 정의되고 확인된 단위변환
- 날짜 형식 표준화
- 결측 표현 표준화
- 규칙에 따른 관리코드 구성

자동 수행 금지:
- 하천명 불일치 수정
- 이상치 삭제
- 결측값 임의 보간
- 서로 다른 자료의 값 자동 교체
- 행 밀림 자료 자동 이동/수정
- 불명확한 컬럼 의미 추정

## 소하천 관리코드
소하천의 기본 식별자는 소하천 관리코드(11자리)다.

내부명: stream_code

반드시 TEXT로 저장한다.
숫자형으로 변환하지 않으며 선행 0을 보존한다.

구성:
- province_code: 2자리 TEXT
- city_county_code: 3자리 TEXT
- town_code: 3자리 TEXT
- stream_serial_no: 3자리 TEXT

DB는 stream_code의 TEXT·11자리·숫자 형식과 구성요소 길이를 검사한다. 네 구성요소의 연결 결과가 stream_code와 일치하는지는 Service validation에서 검사하며 자동 보정하지 않는다.

소하천명은 기본 JOIN KEY로 사용하지 않는다.
자료 간 연결은 원칙적으로 stream_code를 사용한다.

## 데이터 사전
프로그램을 특정 Excel 컬럼 구조에 하드코딩하지 않는다.

표준 데이터항목은 데이터 사전을 통해 관리한다.

데이터 사전은 최소한 다음 개념을 지원하도록 설계한다:
- 표준항목명
- 내부명
- 카테고리
- 데이터형
- 단위
- 설명
- 분석 가능 여부
- 필수 여부
- NULL 허용 여부
- 버전
- 활성 상태

Excel 컬럼 별칭은 column_alias를 통해 표준항목과 연결한다.

새 컬럼의 의미를 확실히 판단할 수 없으면 UNMAPPED로 처리하고 사용자 확인 전 자동 등록하지 않는다.

## Excel Import
다음을 고려한다:
- 여러 시트
- 여러 행 헤더
- 병합 셀
- 컬럼명 차이
- 컬럼 순서 변경
- 추가/누락 컬럼
- 단위 차이
- 빈 행
- 불완전한 행

특정 행 번호 또는 특정 Excel 컬럼 번호에 전체 Import 구조를 하드코딩하지 않는다.

Import 출처는 다음 구조로 추적 가능하게 설계한다:

source_file
→ import_history
→ import_sheet
→ import_column_mapping

원본 파일의 어느 시트/행/컬럼에서 값이 들어왔는지 추적 가능해야 한다.

## 특성정보
특성정보의 authoritative source of truth는 characteristic_value다.

stream_characteristic은 (stream_code, dictionary_id)별 현재 characteristic_value_id와 updated_at만 보관하는 재구축 가능한 참조 캐시다. 실제 값은 characteristic_value에서 조회하며 고정 연구 특성 컬럼이나 값 복제는 두지 않는다. 활성 is_representative를 기준으로 재구축하고 사용자 직접 수정은 금지한다.

stream_characteristic은 직접 수정하지 않는다.

대표값 변경:
characteristic_value
→ 대표값 변경
→ 변경이력 기록
→ stream_characteristic 재구축

## QC
QC는 자동 데이터 삭제 기능이 아니다.

severity와 review_status를 별개로 관리한다.

severity 예:
ERROR / WARNING / INFO

review_status 예:
UNREVIEWED / IN_REVIEW / CONFIRMED / CORRECTED / DEFERRED

이상치는 실제 자연현상일 수 있으므로 자동 오류나 삭제 대상으로 취급하지 않는다.

QC 문제를 발견해도 원본값을 자동 수정하거나 삭제하지 않는다.

자동 QC 화면 상태는 data_quality_issue.is_active=1인 issue만 집계한다. 활성 issue가 없으면 ‘정상’, 활성 ERROR는 없고 INFO/WARNING만 있으면 ‘확인 필요’, 활성 ERROR가 하나 이상이면 ‘오류’다. INFO는 정상 severity가 아니다. review_status는 사람의 검토 상태로 별도 유지하며 활성 여부와 혼합하지 않는다. 활성 issue가 없다는 집계는 검사 실행 완료를 증명하지 않으므로 실행 여부 안내와 구분한다.

특정 값의 issue는 characteristic_value_id FK로 연결하고 값이 없는 issue는 NULL을 허용한다. 재검사에서 현재 문제가 아닌 issue는 is_active=0으로 보존하고 새 문제는 새 행으로 기록한다. review_status와 활성 여부는 별개다.

## 변경이력
중요 데이터 변경은 추적 가능해야 한다.

값 수정, 대표값 변경, 비활성화, 복원, 사용자 보정, QC에 따른 변경 등을 기록한다.

원본 Import 값을 가능한 한 직접 덮어쓰지 않는다.

## 로컬 계정과 사용자 표시

V1 login_id는 Service에서 앞뒤 공백 제거 → 소문자 정규화 → 허용 문자·길이 검증 후 저장한다. 영문자·숫자·점(.)·밑줄(_)·하이픈(-)만 허용하고 내부 공백은 거부한다. 정규화된 길이는 4~50자이며 대소문자만 다른 ID는 동일 계정이다. login_id는 NOT NULL UNIQUE이고 별도 정규화 컬럼은 없다. 이 제한은 display_name·department에 적용하지 않는다.

V1은 개인 PC의 로컬 계정으로 현재 작업자를 식별한다. 서버·팀 협업·동시편집·온라인 회원가입·이메일/휴대폰 복구·복잡한 권한 관리는 포함하지 않는다. 사용자가 없으면 최초 사용자 등록 화면으로 연결한다. app_user의 비밀번호는 평문으로 저장하지 않으며 자체 암호화·비밀번호 알고리즘을 만들지 않는다. 검증된 password hashing library를 사용하며 세부 library·알고리즘은 Phase 1A 인증 구현 직전에 확정한다. 이 선택은 Phase 0 또는 DB 컬럼 정의 자체의 차단 사유가 아니다.

로컬 앱 계정은 연구자료에서 가져온 운영 인증정보와 구분한다. app_user는 애플리케이션 인증·작업자 메타데이터이며 연구항목·일반 Export·QC 원본값·로그 대상이 아니다. 연구 Excel의 서비스 Key·비밀번호·IP·CCTV·RTSP·개인 연락처는 기존대로 연구 DB Import에서 제외한다. 계정 비활성화는 과거 이력을 지우지 않는다.

UI의 **현재 사용값**은 기존 is_representative로 선택한 값이다. characteristic_value는 원본값과 새로 추가한 보정값을 보존하고, record_history는 보정·선택 변경을 기록하며, stream_characteristic은 현재 사용값의 ID를 보관하고 실제 값은 characteristic_value에서 조회하는 참조 캐시다. 별도 현재값 테이블을 만들지 않는다.

동일 stream_code + dictionary_id에 활성 현재 사용값은 최대 하나다. 새 자료 Import만으로 현재 사용값을 변경하지 않으며 사용자가 명시적으로 선택한다. 선택할 characteristic_value_id에 severity='ERROR' AND is_active=1인 issue가 있으면 지정할 수 없다. 활성 WARNING/INFO는 연구자가 확인한 뒤 명시적으로 지정할 수 있다. review_status 변경만으로 ERROR 차단을 해제하지 않는다. 기존 값을 삭제·덮어쓰지 않고 characteristic_value.is_representative 변경·stream_characteristic 참조 캐시 갱신·record_history 기록을 하나의 업무 transaction으로 처리한다. 어느 단계든 실패하면 전부 rollback하며 자동 선정은 금지한다.

과거 작업자 표시명은 사용자 FK로 현재 app_user.display_name을 조회한다. V1 사용자명 snapshot 필드는 추가하지 않는다. DB Restore 전 자동 안전백업을 만들고 성공 후 새 현재 DB의 record_history에 복원 이력을 기록한다. 상세 복구 기술은 Phase 14에서 결정한다.

## 보안
다음과 같은 분석에 불필요한 운영·민감정보는 main research DB에 저장하지 않는다:
- 서비스 Key
- 인증정보
- 계정정보
- 공인/사설 IP
- CCTV 접속정보
- RTSP URL
- 비밀번호
- 담당자 개인 연락처

이러한 컬럼은 기본적으로 분석 DB Import 및 일반 Export에서 제외한다.

명시적인 요청 없이 네트워크 전송, 외부 API, 클라우드 업로드 기능을 구현하지 않는다.

## 기술 방향
예정 기술 스택:
- Python 3.12
- PySide6
- SQLite
- pandas
- openpyxl
- matplotlib
- pytest

아직 실제 설정 파일이 생성되기 전에는 설치되어 있다고 가정하지 않는다.

기본 책임 분리:
UI → Service → Repository → Database

Excel:
Reader → Header Detection → Mapper → Normalizer → Validator → Importer

QC는 독립적인 rule/module 형태로 확장 가능하게 설계한다.

## 오프라인
V1은 인터넷 없이 동작하는 Windows 로컬 프로그램을 목표로 한다.

외부 API, 클라우드 DB, 웹 서버, SaaS, 인터넷 연결에 기본 기능이 의존하지 않도록 한다.

SQLite는 개인 PC 로컬 실행과 로컬 계정별 작업자 식별을 기본 전제로 한다. 동시편집·서버 공유는 V1에서 제공하지 않는다.

## 향후 분석 확장
분석 기능은 모듈식으로 확장 가능해야 한다.

향후:
- 기술통계
- 그룹통계
- 상관분석
- 회귀분석
- 비선형 회귀
- 이상치 분석
- 민감도 분석
- 강우-유량 노모그래프
- 수위-유량 관계
- 매개변수 최적화
- 모형 검증

새 분석 방법 추가 때문에 프로그램 핵심 구조 전체를 다시 작성해야 하는 설계를 피한다.

사용자 정의 수식 기능을 만들 경우 arbitrary Python eval을 사용하지 않는다.

## 연구모형 제한
노모그래프, 수위-유량 관계식, 홍수사상 분리, 최적화 등의 정확한 수식·초기값·제약조건·목적함수·사상분리 기준은 연구자료 확인 후 구현한다.

개발자가 임의로 추정하지 않는다.

근거가 없으면 TODO 또는 미구현으로 남기고 필요한 결정을 보고한다.

## 삭제 및 DB
연구 원자료는 원칙적으로 물리 삭제하지 않는다.

is_active, deprecated, status, history 등의 방법을 우선한다.

Import 실패 트랜잭션 등은 rollback할 수 있다.

SQLite 사용 시:
- foreign_keys 활성화
- 명확한 PK/FK
- 필요한 CHECK constraint
- 필요한 INDEX
- 초기 DB부터 schema_version 부여 및 순차 migration(구현 방식은 Phase 1에서 결정)

불필요한 AUTOINCREMENT를 사용하지 않는다.

## 테스트
다음을 중요 회귀 테스트 대상으로 본다:
- 11자리 관리코드 생성/검증
- 선행 0 보존
- 중복 관리코드
- 필수값 누락
- 데이터형 오류
- 컬럼 별칭
- UNMAPPED
- 다중 시트
- 다중 행 헤더
- Import rollback
- 대표값 변경
- 변경이력
- QC 상태
- 원본값 보존

실제 연구자료의 오류 유형은 민감정보를 제거한 fixture로 재현할 수 있다.

## 개발 Phase

DEVELOPMENT_ROADMAP.md의 번호와 단계명을 기준으로 한다. Phase 0 기반 → Phase 1 DB/schema → Phase 1A 사용자/인증 기반 → Phase 2 사전 → Phase 3 Excel 탐색 → Phase 4 관리코드 → Phase 5 매핑/Preview → Phase 6 Import → Phase 7 QC → Phase 8 보정/현재 사용값/이력 → Phase 9 조회·홈·로그인 UI → Phase 10 Import/사전/QC·설정 UI → Phase 11 통계 → Phase 12 그래프 → Phase 13 Export → Phase 14 백업/복구 → Phase 15 패키징 → Phase 16 최종 검증.

UI보다 데이터·업무 기반을 먼저 구축하며 각 Phase 테스트·Gate 통과 후 진행한다.

## V1 UI 범위

V1은 팀 초대·실시간 협업·서버 동기화·클라우드·복잡한 권한·GIS 지도·하천 사진·시계열 분석·자동 위험도 판정·과거 분석 결과 공유·PDF Export를 제외한다. 여러 연구자, 중앙 서버/API, PostgreSQL, 팀 데이터·분석 결과 공유, 사용자/권한 확대는 향후 확장 영역이다.

V1 결과 내보내기는 Excel(소하천 조회 결과·QC 결과·보정/변경 이력·기초통계)과 PNG(그래프)다. PDF는 제외한다. 내부 PK·로그·민감정보·app_user 인증정보는 일반 Export에서 제외한다. 원본 Excel을 덮어쓰지 않으며 내보낸 사용자 파일을 프로그램이 자동 삭제하지 않는다.

## 향후 세부 설계 문서
세부 구현 기준은 다음 설계 문서에 둔다:

docs/PROJECT_OVERVIEW.md
docs/ARCHITECTURE.md
docs/DATABASE_DESIGN.md
docs/DATA_RULES.md
docs/QC_RULES.md
docs/DEVELOPMENT_ROADMAP.md

세부 문서가 생성된 이후에는 관련 작업 전에 해당 문서를 확인한다.

문서와 구현 사이에 충돌이 있으면 임의 변경하지 말고:
1. 충돌 내용
2. 변경 필요 이유
3. 영향 범위
4. 제안 수정안
을 먼저 보고한다.

## Codex 작업 규칙
작업 전:
- AGENTS.md 확인
- 관련 docs 확인
- 현재 Phase 확인
- 기존 코드 및 Git 상태 확인
- 요청 범위 확인

작업 중:
- 현재 요청 범위를 넘어서는 기능을 임의 구현하지 않는다.
- 무관한 리팩터링을 하지 않는다.
- 설계 문서를 임의 변경하지 않는다.
- 연구 데이터 의미를 추측하지 않는다.
- 테스트를 약화하여 통과시키지 않는다.
- 임시 하드코딩으로 테스트만 통과시키지 않는다.

작업 완료 후:
- 구현 내용
- 생성/수정 파일
- DB 변경
- 실행 테스트
- 테스트 결과
- 남은 문제/TODO
- 다음 단계 전에 확인할 사항
을 보고한다.

## 절대 금지
- 연구자료에 없는 의미 생성
- 미확정 컬럼 자동 해석
- 원본 Excel 수정
- QC 오류 자동 삭제
- 행 밀림 자동 수정
- 하천명 불일치 자동 수정
- 결측값 임의 보간
- stream_code 숫자 저장
- 민감 운영정보 main DB 저장
- 임의 외부 API/네트워크 기능 추가
- 전체 프로그램을 한 번에 구현
- 보고 없이 핵심 설계 변경

빠른 구현보다 데이터 정확성, 추적성, 재현성, 유지보수성을 우선한다.

## 공통 작업 방식
- 사용자에게 한국어로 간결하게 설명한다.
- 변경 전에 관련 파일과 Git 상태를 확인하고, 사용자가 작성한 변경을 보존한다.
- 요청한 목적에 필요한 범위만 수정하고, 무관한 리팩터링이나 의존성 추가를 피한다.
- 기존 코드가 있으면 그 구조와 스타일을 따른다.
- 새로운 의존성이 필요하면 목적을 확인하고 프로젝트의 의존성 관리 파일에 기록한다.
- 비밀 키, 인증 정보, 개인정보를 코드나 로그에 기록하거나 커밋하지 않는다. 설정 예시에는 자리표시자를 사용한다.

## 공통 검증 원칙
- 실행 및 테스트 명령은 프로젝트 설정과 문서에서 확인한 뒤 사용한다.
- 동작 변경에는 관련 검증을 수행하고, 필요한 경우 회귀 테스트를 추가한다.
- 문서만 변경했다면 내용, 경로, 형식을 확인한다.
- 완료 시 변경 사항과 검증 결과를 요약한다. 실행하지 못한 검증은 이유와 함께 명시한다.

## 지침 및 문서 유지
- 실행 방법, 설정, 디렉터리 구조가 정해지면 README에 기록한다.
- 이 파일에는 지속적으로 유효한 작업 지침을 유지하고, 일회성 진행 기록은 넣지 않는다.
