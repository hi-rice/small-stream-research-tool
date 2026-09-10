# 소프트웨어 아키텍처

이 문서는 `small-stream-research-tool`의 목표 아키텍처와 계층·모듈별 책임을 정의한다. 프로젝트 목적과 제품 범위는 `PROJECT_OVERVIEW.md`, 공통 개발 원칙은 루트의 `AGENTS.md`를 기준으로 한다.

현재는 Phase 0 구현 전 설계 단계다. 아래 디렉터리, Service·Repository 명칭과 인터페이스는 설계 방향 또는 예시이며 실제 파일이나 클래스가 이미 존재한다는 의미가 아니다. 세부 SQL 테이블·컬럼은 `DATABASE_DESIGN.md`에서 다루며 이 문서에서 확정하지 않는다.

## 1. 기본 아키텍처 원칙

Windows에서 로컬·오프라인으로 동작하는 Python 데스크톱 연구지원 프로그램을 설계한다. V1은 개인 PC 로컬 SQLite 기반으로 소하천 특성정보 등록·검수·조회·기본 분석·출력을 지원한다는 목표를 갖는다.

```text
UI → Service → Repository → Database
```

| 계층 | 책임 | 담당하지 않는 작업 |
| --- | --- | --- |
| UI | 사용자 입력, 화면 표시, 작업 요청 전달, 결과 표시 | 비즈니스 규칙, SQL, 직접적인 데이터 가공 |
| Service | Import·표준화·QC·대표값·분석의 업무 흐름, 트랜잭션 단위 작업 조정 | 위젯 구현, SQL 구현 세부사항 |
| Repository | CRUD, 조회·저장, SQL과 DB 접근 캡슐화 | 대표값 선택 등 비즈니스 판단 |
| Database | SQLite 연결, schema, transaction, migration/schema version, 백업 기반 기능 | 사용자 화면, 연구자료 의미 판단 |

Service는 `importers`, `qc`, `analysis`, `exporters`의 전문 처리 모듈도 호출한다. 저장소 접근과 계산·검증의 책임을 구분하며, 모든 계산이 Repository를 거쳐야 한다는 의미는 아니다.

## 2. 권장 목표 프로젝트 구조

다음은 권장 목표 구조다. Phase별로 필요한 디렉터리와 파일만 생성하며 빈 디렉터리를 미리 모두 만들지 않는다. AGENTS.md와 6개 설계문서는 작성되어 있다. 소스·설정·테스트 디렉터리는 구현 예정이며 아래 트리는 목표 구조다.

```text
small-stream-research-tool/
├─ AGENTS.md
├─ README.md
├─ pyproject.toml
├─ docs/
│  ├─ PROJECT_OVERVIEW.md
│  ├─ ARCHITECTURE.md
│  ├─ DATABASE_DESIGN.md
│  ├─ DATA_RULES.md
│  ├─ QC_RULES.md
│  └─ DEVELOPMENT_ROADMAP.md
├─ src/
│  └─ small_stream_research_tool/
│     ├─ app/
│     ├─ ui/
│     ├─ services/
│     ├─ repositories/
│     ├─ database/
│     ├─ importers/
│     ├─ qc/
│     ├─ analysis/
│     ├─ exporters/
│     ├─ models/
│     ├─ config/
│     └─ utils/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ fixtures/
└─ data/
   ├─ db/
   ├─ backups/
   ├─ exports/
   └─ temp/
```

`models`는 화면이나 SQLite 구현에 의존하지 않는 데이터 표현, `config`는 설정과 로컬 경로의 관리, `utils`는 특정 업무에 속하지 않는 작은 공통 처리를 담당하는 방향으로 설계한다. 업무 로직을 범용 유틸리티로 모으지 않는다.

`data` 하위 구조는 로컬 데이터의 용도별 배치 예시다. 배포 시 소스 디렉터리에 저장해야 한다는 의미는 아니다. 실제 DB·백업·출력·임시 파일은 프로그램 소스와 분리한 로컬 데이터 경로에 두며, 구체적인 저장 위치는 후속 설계에서 정한다.

## 3. app: 시작과 애플리케이션 조립

`app`은 시작 처리(application bootstrap), 의존성 연결(dependency wiring), 메인 윈도우 시작, 프로그램 종료 처리를 담당한다. UI와 Service, Repository 등을 연결하여 사용할 수 있도록 조립하며 업무 로직이나 DB SQL은 넣지 않는다.

## 4. UI: 사용자 조작과 표시

사용자 표시명은 **소하천 데이터 관리**, 기관 표기는 NDMI다. 아래는 제공된 텍스트 UI 명세의 화면 구조이며 Figma를 직접 관찰한 결과가 아니다.

| 화면 | 책임 |
| --- | --- |
| 00 로그인 | AuthService / 최초 사용자 등록 |
| 01 홈 | 조회 Service / 최근 record_history |
| 02 Excel 가져오기 | ImportService / workbook·sheet·header 탐색 |
| 03 컬럼 매핑 | DictionaryService·ImportService / 매핑 선택 |
| 04 관리코드 검증 | 관리코드 검증 Service / TEXT 식별자 |
| 05 Import Preview | ImportService / 요약·sample·문제 확인 |
| 06 Import 이력 | ImportRepository를 통한 Service 조회 |
| 07 품질검사(QC) | QCService / 검토자·검토시각 |
| 08 특성정보 보정 관리 | StreamService / 새 보정값·현재 사용값·이력 |
| 09 소하천 조회 | StreamService / 검색·상세·출처 |
| 10 DB 관리 | DB·BackupService / 상태·비활성·복원·백업 |
| 11 기초통계 | AnalysisService / 동적 수치항목 선택 |
| 12 그래프 분석 | 분석 모듈 / Histogram·Boxplot·Scatter plot |
| 13 결과 내보내기 | ExportService / Excel·PNG |
| 14 작업이력 | HistoryRepository를 통한 Service 조회 |
| 15 마이페이지 | 현재 사용자·최근 record_history |
| 16 설정 | 환경 설정 Service / QSettings 또는 local config |

UI는 Service만 호출한다. pandas·SQL·QC·현재 사용값 선정 규칙을 직접 구현하지 않는다. DB 관리의 데이터 복원과 DB 백업 복원은 구분하며 특성값 변경은 08 보정 관리로만 연결한다.

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

## 5. Service: 업무 흐름 조정

다음 명칭은 책임을 설명하기 위한 후보이며, 실제 클래스 구성은 각 Phase에서 필요한 범위로 구체화한다.

| Service 후보 | 예상 책임 |
| --- | --- |
| `ImportService` | 파일 등록, Excel 탐색, Preview 생성, 매핑 결과 확인, 표준화, 검증, Import transaction 실행 조정 |
| `DictionaryService` | 데이터 사전, 컬럼 별칭, 단위 관리, 신규 컬럼 처리 |
| `StreamService` | 소하천 기본정보, 관리코드 검증, 소하천 조회, 특성정보 대표값 처리 |
| `QCService` | QC rule 실행, 결과 저장, 검토상태 변경, 수정 후 재검사 |
| `AnalysisService` | V1 기본 통계, 분석 데이터 준비, 분석 모듈 호출 |
| `ExportService` | Excel/PNG 결과, Export 대상 필드 검증, 민감 운영정보 제외 |
| `BackupService` | 중요 작업 전 백업과 복구 업무 흐름 조정 |

Service 간 과도한 직접 의존을 피한다. 업무 단위의 트랜잭션 경계는 Service가 조정하고, 시작·commit·rollback의 기반 기능은 Database가 제공한다. Repository가 중간에 독립적으로 저장을 확정하여 같은 업무의 데이터와 이력이 분리되지 않도록 한다.

### 로컬 인증·이력·환경 설정

V1 login_id는 Service에서 앞뒤 공백 제거 → 소문자 정규화 → 허용 문자·길이 검증 후 저장한다. 영문자·숫자·점(.)·밑줄(_)·하이픈(-)만 허용하고 내부 공백은 거부한다. 정규화된 길이는 4~50자이며 대소문자만 다른 ID는 동일 계정이다. login_id는 NOT NULL UNIQUE이고 별도 정규화 컬럼은 없다. 이 제한은 display_name·department에 적용하지 않는다.

AuthService/UserRepository는 후보 책임명으로, 최초 사용자 등록·로그인·현재 작업자·비활성화를 다룬다. 인증 기반을 데이터 사전·Import보다 먼저 구현하고 화면은 이후 연결한다.

V1은 개인 PC의 로컬 계정으로 현재 작업자를 식별한다. 서버·팀 협업·동시편집·온라인 회원가입·이메일/휴대폰 복구·복잡한 권한 관리는 포함하지 않는다. 사용자가 없으면 최초 사용자 등록 화면으로 연결한다. app_user의 비밀번호는 평문으로 저장하지 않으며 자체 암호화·비밀번호 알고리즘을 만들지 않는다. 검증된 password hashing library를 사용하며 세부 library·알고리즘은 Phase 1A 인증 구현 직전에 확정한다. 이 선택은 Phase 0 또는 DB 컬럼 정의 자체의 차단 사유가 아니다.

로컬 앱 계정은 연구자료에서 가져온 운영 인증정보와 구분한다. app_user는 애플리케이션 인증·작업자 메타데이터이며 연구항목·일반 Export·QC 원본값·로그 대상이 아니다. 연구 Excel의 서비스 Key·비밀번호·IP·CCTV·RTSP·개인 연락처는 기존대로 연구 DB Import에서 제외한다. 계정 비활성화는 과거 이력을 지우지 않는다.

### 작업이력의 책임

record_history는 중요한 연구·운영 변경을 기록한다: Import, QC 검토, 특성정보 보정, 현재 사용값 변경, 비활성화·데이터 복원, DB 백업·DB 복원 및 기타 중요한 연구 데이터 변경. 검색·정렬·페이지 이동·일반 조회·단순 필터·그래프 유형 변경은 기록하지 않는다. 사용자에게 이력 수정·삭제 기능을 제공하지 않는다.

홈·마이페이지와 작업이력은 record_history를 공유하고 actor_user_id로 현재 app_user.display_name을 조회한다. V1 사용자명 snapshot 필드는 추가하지 않는다. DB Restore 전에 자동 안전백업을 만들고, 성공 후 새 현재 DB의 record_history에 복원 작업을 기록한다. 데이터 비활성화 복원은 RESTORE, DB 전체 복원은 DB_RESTORE로 구분한다. Backup/Restore 기술과 이벤트 대상 표현·복원된 DB의 작업자 연결은 Phase 14 전에 확정한다. 원래 DB의 최신 이력이 복원 DB에 자동 합쳐진다고 가정하지 않는다.

설정은 일반, 데이터/저장공간, 백업, Excel/Import, 내보내기, 화면 표시로 구분한다. 글자 크기·행 높이·최근 폴더·window size·기본 출력 경로는 QSettings 또는 별도 local config를 우선 검토한다. 연구 DB 설정과 UI 환경 설정을 혼합하지 않는다.

## 6. Repository: 저장소 접근

Repository는 조회·저장과 SQL 캡슐화를 담당하며 SQLite 연결이나 SQL 구현 세부사항을 Service에 노출하지 않는다. 대표값 선택이나 QC 결과에 대한 업무 판단은 수행하지 않는다. CRUD 중 연구 원자료 삭제는 `AGENTS.md`의 원본 보존·비활성화 우선 원칙을 따른다.

V1 책임 분리 후보는 `StreamRepository`, `CharacteristicRepository`, `DictionaryRepository`, `ImportRepository`, `QualityRepository`, `HistoryRepository`다. 향후 계측·분석이력·연구모형에는 `MeasurementRepository`, `AnalysisRepository`, `ModelRepository` 등의 확장 위치를 고려하되 V1에서 선행 구현하지 않는다.

향후 PostgreSQL 등으로 변경할 가능성을 고려하지만 V1에서 범용 DB 추상화를 과도하게 만들지 않는다.

## 7. Database: SQLite 기반 기능

초기 DB부터 schema_version을 기록하고 이후 순차 migration을 적용한다. migrations/001_initial.sql 등의 구조는 예정이며 runner는 Phase 1에서 정한다.

Database 계층은 connection 관리, PRAGMA 설정, transaction, schema 생성, schema version, migration, index와 backup을 담당한다. 연결 시 `PRAGMA foreign_keys = ON`을 적용하는 설계로 한다.

연구 데이터의 주요 변경은 트랜잭션 단위로 처리한다. 아직 확정하지 않은 변경을 취소하는 rollback과 완료된 중요 작업을 백업에서 복구하는 restore는 별도 작업이다. BackupService는 실행할 업무 흐름을 조정하고 Database 계층은 DB 백업·복구 기반 기능을 제공한다.

DB 파일은 프로그램 소스와 분리한 로컬 데이터 경로에 둔다. 19개 V1 테이블의 PK/FK·제약은 DATABASE_DESIGN.md를 따른다. C1/U1/Q1과 기본 제약·migration 방향은 확정되었으며, Import 중단 복구 T1과 DB 복원 사용자 연결 B1은 해당 Phase 전에 결정한다.

## 8. Excel Import 아키텍처

Excel 처리를 하나의 거대한 함수로 만들지 않고 다음 단계로 나눈다.

```text
Excel Reader → Sheet Inspector → Header Detector → Column Mapper
→ Normalizer → Validator → Import Preview → Importer
```

| 단계 | 책임 |
| --- | --- |
| Reader | 원본을 수정하지 않고 파일을 읽음 |
| Sheet Inspector | 시트 목록과 기본 구조 탐색 |
| Header Detector | 헤더 시작·종료 행과 병합 구조 분석 |
| Column Mapper | 원본 컬럼을 `data_dictionary` / `column_alias`와 연결 |
| Normalizer | 값 형식, 결측 표현, 등록·확인된 단위 변환 표준화 |
| Validator | 관리코드, 자료형, 필수값 등 기본 검증 |
| Preview | DB 저장 전에 매핑과 문제를 확인할 수 있는 결과 생성 |
| Importer | 확인된 결과를 Service가 조정하는 트랜잭션으로 저장 |

Importer의 DB 저장도 Repository/Database를 거치며 별도의 SQL 접근 경로를 만들지 않는다. 미확정 컬럼은 `UNMAPPED`로 유지하고 원본 행·열 번호를 전체 시스템의 고정 전제로 삼지 않는다. 단계 사이에서 원본값과 파일·시트·행·컬럼 출처를 전달하며 표준화값과 구분한다.

관리코드 `stream_code`는 11자리 TEXT로 선행 0을 보존하고 구성요소와의 일치를 검증한다. 소하천명을 JOIN KEY로 사용하지 않는다.

실제 Import 실행 시작 때에만 import_history를 생성한다. 같은 stream_code가 기존 DB에 있다고 자동 오류로 판정하지 않으며 여러 출처·시점의 characteristic_value를 보존한다.

### 진행 중 Import 작업 저장: V1 로컬 workspace

V1은 Excel 가져오기 → Sheet/Header 선택 → 컬럼 매핑 후 프로그램을 종료해도 재실행·로그인 후 이어서 작업할 수 있도록 한다. 임시 선택 상태는 연구 DB 밖의 application data/workspace 아래 로컬 파일(JSON 등)에 저장한다. 경로 예시는 `workspace/import_draft_xxx.json`이며 실제 파일명 계약은 구현 단계에서 정한다. 연구 DB는 19개 테이블을 유지하며 Draft 테이블을 추가하지 않는다.

저장 후보는 사용자 ID, 원본 Excel 경로·hash, 선택 Sheet, Header 시작/종료 행, Data 시작 행, 컬럼 매핑 상태, 현재 작업 단계, 마지막 저장 시각이다. 행·컬럼은 1-based, 시스템 저장 시각은 UTC를 따른다. 원본 전체 셀·민감값·비밀번호·인증정보는 복제하지 않는다.

재개 시 원본 파일 존재와 hash 일치를 확인한다. 파일 이동·부재 또는 hash 불일치 시 자동 대체하지 않고 사용자에게 원본 파일 재지정을 요구한다. 재지정 파일도 검증하며 내용이 바뀐 파일에 이전 매핑을 자동 확정하지 않는다. 사전·매핑 유효성은 재개 시 다시 검증한다.

source_file은 원본 메타데이터, workspace는 미완료 작업, import_history는 실제 DB Import 실행 이력이다. Preview/매핑/Draft 저장은 import_history를 생성하지 않는다. workspace의 사용자 ID는 DB FK가 아니므로 Service가 현재 DB·로그인 사용자와의 소유 관계를 확인한다. DB 복원 후 같은 숫자 사용자 ID를 동일인으로 단정하지 않는다.

파일 형식 버전·원자적 저장·손상 대응·사용자별 접근·보존 기간·Import 성공 후 정리·비활성 계정 및 DB 복원 시 재연결 계약은 Phase 5 전 TODO다. 정리는 원본 Excel이나 Export 파일 자동 삭제를 뜻하지 않는다.

## 9. 데이터 처리의 개념적 단계

```text
RAW → DISCOVERED → MAPPED → NORMALIZED → VALIDATED → IMPORTED → REVIEWED
```

원본 읽기, 구조 탐색, 매핑, 표준화, 검증, 저장, 연구자 검토를 설명하는 개념이다. 하나의 status 컬럼이나 고정된 상태 전이 구현을 지정하지 않는다. `MAPPED` 단계에서도 미확정 컬럼은 `UNMAPPED`로 명시하며 의미를 추정하지 않는다.

원본 Excel을 수정하지 않고 원본값을 가능한 한 보존한다. 원본값·표준화값·QC 결과·대표값·사용자 보정값의 의미를 혼합하지 않는다.

## 10. QC 아키텍처

```text
QC Engine → QC Rules → QC Result → Review
→ Correction/Representative Change → Recheck
```

QC는 독립적인 rule/module로 확장한다. 예상 규칙 그룹은 `management_code`, `required_value`, `data_type`, `duplicate`, `missing`, `range`, `cross_source`, `unit`, `outlier`, `row_alignment`다. 모든 규칙을 V1 초기에 한 번에 구현하지 않는다.

공유할 인터페이스 개념은 rule identifier, target, severity, parameters, `evaluate()`, result/message다. 이는 계약의 검토 항목이며 실제 Python 인터페이스 코드나 자료형을 확정하는 것이 아니다.

Engine은 규칙을 실행해 결과를 반환하고 QCService는 결과 저장과 검토상태 변경을 조정한다. severity와 review_status는 별도로 관리한다. QC Engine은 데이터를 직접 삭제하거나 자동 보정하지 않는다. 보정·대표값 변경은 연구자 검토 후 이력을 동반하는 업무 처리로 수행한다.

Import 전 Validator의 기본 검증·QC와 Import 후 출처 간 비교 및 재검사를 구분한다. 저장 전 확인과 저장 후 지속적인 연구자 검토를 모두 지원하는 방향으로 설계한다.

QCService는 characteristic_value_id와 is_active로 현재 issue를 판정한다. 특정 값이 없는 issue는 nullable FK를 사용하며, 성공한 재검사 범위에서 과거 issue 비활성화와 새 issue 저장을 한 transaction으로 조정한다. 검토 상태와 활성 상태를 혼합하지 않는다.

## 11. 특성정보와 대표값

stream_characteristic은 (stream_code, dictionary_id)별 현재 characteristic_value_id와 updated_at만 보관하는 재구축 가능한 참조 캐시다. 실제 값은 characteristic_value에서 조회하며 고정 연구 특성 컬럼이나 값 복제는 두지 않는다. 활성 is_representative를 기준으로 재구축하고 사용자 직접 수정은 금지한다.

```text
Import → characteristic_value 저장 → QC → 사용자 검토
→ 대표값 지정·변경이력 기록 → stream_characteristic 재구축
```

대표값 변경과 이력·캐시 갱신은 일관성이 유지되는 업무 단위로 조정한다. `stream_characteristic`을 직접 편집하는 경로는 만들지 않는다. 서로 다른 출처의 값을 자동 교체하지 않고 출처와 판단을 추적 가능하게 한다.

UI의 **현재 사용값**은 기존 is_representative로 선택한 값이다. characteristic_value는 원본값과 새로 추가한 보정값을 보존하고, record_history는 보정·선택 변경을 기록하며, stream_characteristic은 현재 사용값의 ID를 보관하고 실제 값은 characteristic_value에서 조회하는 참조 캐시다. 별도 현재값 테이블을 만들지 않는다.

동일 stream_code + dictionary_id에 활성 현재 사용값은 최대 하나다. 새 자료 Import만으로 현재 사용값을 변경하지 않으며 사용자가 명시적으로 선택한다. 선택할 characteristic_value_id에 severity='ERROR' AND is_active=1인 issue가 있으면 지정할 수 없다. 활성 WARNING/INFO는 연구자가 확인한 뒤 명시적으로 지정할 수 있다. review_status 변경만으로 ERROR 차단을 해제하지 않는다. 기존 값을 삭제·덮어쓰지 않고 characteristic_value.is_representative 변경·stream_characteristic 참조 캐시 갱신·record_history 기록을 하나의 업무 transaction으로 처리한다. 어느 단계든 실패하면 전부 rollback하며 자동 선정은 금지한다.

## 12. 분석 아키텍처

V1 통계는 유효 N, 결측, 평균, 중앙값, 표준편차, 최소, Q1, Q3, 최대와 지역별 비교다. 그래프는 Histogram, Boxplot, Scatter plot이다. 수치형 항목 선택은 data_dictionary.data_type과 analyzable을 기준으로 동적으로 구성하며 Figma 예시 컬럼을 하드코딩하지 않는다. 결측 집계 대상·통계 정의·QC 포함 정책은 구현 전에 확인하며 연구 threshold는 만들지 않는다.

AnalysisService가 데이터를 준비하고 UI와 분리된 분석 모듈을 호출한다. 기존의 상관·회귀·최적화·민감도·노모그래프·모형 검증은 향후 확장 영역이다.

## 13. Export 아키텍처

V1 결과 내보내기는 Excel(소하천 조회 결과·QC 결과·보정/변경 이력·기초통계)과 PNG(그래프)다. PDF는 제외한다. 내부 PK·로그·민감정보·app_user 인증정보는 일반 Export에서 제외한다. 원본 Excel을 덮어쓰지 않으며 내보낸 사용자 파일을 프로그램이 자동 삭제하지 않는다.

UI → ExportService → exporters 책임을 유지한다.

## 14. 보안 경계

연구분석에 불필요한 서비스 Key, 인증·계정정보, IP, CCTV 접속정보, RTSP URL, 비밀번호, 담당자 개인 연락처는 main research DB와 일반 Export에 포함하지 않는다. Import 단계에서 해당 컬럼을 분석 대상에서 제외할 수 있어야 하며 Export 전에도 확인한다.

외부 네트워크 연결은 기본 아키텍처에 포함하지 않는다. 향후 운영정보 저장이 명시적으로 필요해지면 main DB와 별도의 보호된 저장소를 설계한다. V1에서 해당 저장소를 선행 구현하는 지시는 아니다.

V1은 개인 PC의 로컬 계정으로 현재 작업자를 식별한다. 서버·팀 협업·동시편집·온라인 회원가입·이메일/휴대폰 복구·복잡한 권한 관리는 포함하지 않는다. 사용자가 없으면 최초 사용자 등록 화면으로 연결한다. app_user의 비밀번호는 평문으로 저장하지 않으며 자체 암호화·비밀번호 알고리즘을 만들지 않는다. 검증된 password hashing library를 사용하며 세부 library·알고리즘은 Phase 1A 인증 구현 직전에 확정한다. 이 선택은 Phase 0 또는 DB 컬럼 정의 자체의 차단 사유가 아니다.

로컬 앱 계정은 연구자료에서 가져온 운영 인증정보와 구분한다. app_user는 애플리케이션 인증·작업자 메타데이터이며 연구항목·일반 Export·QC 원본값·로그 대상이 아니다. 연구 Excel의 서비스 Key·비밀번호·IP·CCTV·RTSP·개인 연락처는 기존대로 연구 DB Import에서 제외한다. 계정 비활성화는 과거 이력을 지우지 않는다.

V1은 팀 초대·실시간 협업·서버 동기화·클라우드·복잡한 권한·GIS 지도·하천 사진·시계열 분석·자동 위험도 판정·과거 분석 결과 공유·PDF Export를 제외한다. 여러 연구자, 중앙 서버/API, PostgreSQL, 팀 데이터·분석 결과 공유, 사용자/권한 확대는 향후 확장 영역이다.

## 15. 향후 시계열 확장

V1에서는 구현하지 않는다. V3 이후 계측자료를 위해 계측용 Repository와 처리 모듈을 추가할 위치를 고려한다. 다음은 개념적 관계이며 확정된 schema가 아니다.

```text
small_stream → measurement_station → stage/discharge observations
small_stream → AWS link → AWS station → rainfall observations
```

RAW 관측값과 계산·보정·모형 결과를 혼합하지 않는다. 계산된 누적강우, 보정유량, 모의유량 등은 향후 derived timeseries 개념으로 분리할 수 있도록 한다.

## 16. 향후 연구모형 확장

V2 분석 재현성 관리와 V4 이후 연구모형을 고려하여 다음 개념적 흐름을 확장 방향으로 둔다.

```text
analysis run → input dataset/event → equation/model → parameters
→ validation → result/figure
```

V1에서 분석이력 기반과 모형 기능을 모두 구현하는 지시는 아니다. 노모그래프의 정확한 수식, 초기값, 제약조건, 목적함수, 홍수사상 분리 알고리즘은 연구자료 확인 전에 확정하지 않는다.

## 17. 의존성 방향

의존성은 기본적으로 상위에서 하위로 흐른다. `UI → Service → Repository → Database`를 따르고 `Database → UI`, `Repository → UI`, `QC Rule → UI`의 역방향 결합을 피한다.

도메인·업무 로직, Import 처리, QC 규칙과 분석 계산을 PySide6 widget에 종속시키지 않는다. app이 의존성을 연결하고 UI는 처리 결과를 표시한다. 화면을 시작하지 않고도 핵심 로직을 테스트할 수 있는 구조를 목표로 한다.

## 18. 테스트 구조

pytest를 예정하며 다음과 같이 테스트 책임을 구분한다. 현재 테스트 파일이 구현되었다는 의미는 아니다.

| 구분 | 대상 |
| --- | --- |
| `tests/unit` | 관리코드와 선행 0 보존, 데이터 정규화, 매핑, QC rule, Service 단위 로직 |
| `tests/integration` | SQLite, Repository, Import transaction과 rollback, Excel Import pipeline 연계 부분 |
| `tests/fixtures` | 민감정보를 제거한 작은 Excel, 다중 시트, 다중 헤더, 컬럼 별칭, UNMAPPED, 중복 관리코드, 행 정렬 이상 패턴 |

fixture에 실제 운영 인증정보·IP·연락처를 포함하지 않는다. 원본값 보존, 대표값 변경과 이력, QC 상태 처리도 중요 검증 대상으로 삼는다.

## 19. 오류 처리

사용자가 이해할 수 있는 오류 표시와 개발자 진단용 상세정보를 구분한다. Service는 실패한 업무와 단계를 식별할 수 있는 결과를 UI에 전달하며, DB transaction 실패 시 중간 저장 상태가 남지 않도록 한다.

오류를 무시하고 저장을 계속하기보다 안전한 실패를 우선한다. 연구자료 의미가 불명확하면 추정해서 진행하지 않고 `UNMAPPED`, QC 결과, 설계상 TODO 등 적절한 명시 상태로 남긴다. 이를 반드시 하나의 DB 상태 컬럼에 통합한다는 의미는 아니다.

## 20. 로깅

향후 로깅을 도입하면 작업 종류, 처리 건수, 오류 코드, 처리 단계, 실행시간을 진단 정보로 기록할 수 있다. 서비스 Key, 비밀번호, 인증정보, RTSP credential, 담당자 개인정보는 기록하지 않는다.

원본 데이터 전체를 무분별하게 로그로 출력하지 않는다. 진단 로그와 연구 데이터 출처·변경이력은 목적을 구분하며, 로그만으로 연구 이력을 대체하지 않는다.

## 21. 아키텍처의 핵심 목표

- 특정 Excel 양식에 종속되지 않는다.
- 연구 원본을 보존하고 데이터 출처를 추적할 수 있다.
- QC와 수정, 대표값과 원본값을 분리한다.
- UI와 업무 로직, DB와 업무 로직의 책임을 분리한다.
- 새로운 분석 방법을 추가할 수 있다.
- 향후 계측자료와 연구모형을 단계적으로 확장할 수 있다.
- 기본 기능을 오프라인으로 실행할 수 있다.
- 각 책임을 테스트할 수 있다.
- 연구자가 SQL을 몰라도 사용할 수 있다.

예정 기술은 Python 3.12, PySide6, SQLite, pandas, openpyxl, matplotlib, pytest다. 실제 도입은 Phase별로 진행하며 위 구조·기술이 이미 구현되거나 설치되었다고 가정하지 않는다.
