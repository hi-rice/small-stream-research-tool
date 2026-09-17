"""Phase 9A 읽기 전용 조회. DB 레코드를 안전한 표시 projection으로 제한한다."""

import json

from small_stream_research_tool.database.connection import read_transaction
from small_stream_research_tool.models.stream_read import (
    CharacteristicDetailRow,
    CharacteristicDisplayPolicy,
    CharacteristicSummary,
    ProvenanceSummary,
    QCDisplayItem,
    RegionOption,
    StreamBasicDetail,
    StreamListPage,
    StreamListRequest,
    StreamListRow,
    StreamReadDetail,
    StreamResearchDetail,
    ValueHistoryDisplayRow,
)
from small_stream_research_tool.models.stream_read_errors import (
    InvalidStreamReadRequest,
    StreamReadError,
    StreamReadFailure,
)
from small_stream_research_tool.repositories.stream_query_repository import (
    SORT_COLUMNS,
    StreamQueryRepository,
)

MAX_PAGE_SIZE = 100  # QTableView 한 번의 적재와 IN-list QC batch를 제한한다.
MAX_DISPLAY_ITEMS = 200  # SQLite bind 수와 상세 화면 전송량의 기술적 상한이다.


def _integer(value):
    return type(value) is int and 0 < value < 2**63


def _code(value, length):
    return type(value) is str and len(value) == length and value.isascii() and value.isdigit()


def _qc_state(counts):
    if counts and counts[0]:
        return "ERROR"
    if counts and (counts[1] or counts[2]):
        return "NEEDS_REVIEW"
    return "ACTIVE_ISSUES_NONE"  # 검사 실행 완료를 증명하지 않는다.


def _typed_value(row, start=2):
    values = tuple(value for value in row[start : start + 4] if value is not None)
    if len(values) != 1:
        raise StreamReadFailure()
    return values[0]


def _source_classification(source_type):
    if source_type == "USER_CORRECTION":
        return "RESEARCHER_CORRECTION"
    if source_type == "IMPORT":
        return "IMPORT"
    return "OTHER_SOURCE"


class StreamReadService:
    def __init__(self, connection):
        self._connection = connection
        self._repository = StreamQueryRepository(connection)

    def _request(self, request):
        if type(request) is not StreamListRequest:
            raise InvalidStreamReadRequest()
        if not (
            _integer(request.page)
            and type(request.page_size) is int
            and 1 <= request.page_size <= MAX_PAGE_SIZE
        ):
            raise InvalidStreamReadRequest()
        if (request.page - 1) * request.page_size >= 2**63:
            raise InvalidStreamReadRequest()
        if (
            type(request.search) is not str
            or len(request.search) > 200
            or "\x00" in request.search
            or request.search != request.search.strip()
        ):
            raise InvalidStreamReadRequest()
        if request.search.isascii() and request.search.isdigit() and len(request.search) > 11:
            raise InvalidStreamReadRequest()
        for value, length in (
            (request.province_code, 2),
            (request.city_county_code, 3),
            (request.town_code, 3),
        ):
            if value is not None and not _code(value, length):
                raise InvalidStreamReadRequest()
        if (
            type(request.sort_field) is not str
            or request.sort_field not in SORT_COLUMNS
            or type(request.sort_direction) is not str
            or request.sort_direction not in ("ASC", "DESC")
            or type(request.active_only) is not bool
        ):
            raise InvalidStreamReadRequest()

    def _policy(self, policy):
        if type(policy) is not CharacteristicDisplayPolicy:
            raise InvalidStreamReadRequest()
        ids = policy.allowed_dictionary_ids
        if (
            type(ids) is not frozenset
            or len(ids) > MAX_DISPLAY_ITEMS
            or any(not _integer(i) for i in ids)
            or type(policy.show_source_file_name) is not bool
            or type(policy.show_sheet_name) is not bool
        ):
            raise InvalidStreamReadRequest()
        return tuple(sorted(ids))

    def list_streams(self, request=None):
        try:
            if request is None:
                request = StreamListRequest()
            self._request(request)
            with read_transaction(self._connection):
                count = self._repository.count_streams(request)
                raw = self._repository.page_streams(request)
                codes = tuple(row[0] for row in raw)
                issues = {
                    row[0]: row[1:] for row in self._repository.issue_counts_for_streams(codes)
                }
                rows = tuple(
                    StreamListRow(
                        code,
                        name,
                        province,
                        city,
                        town,
                        bool(active),
                        _qc_state(issues.get(code)),
                    )
                    for code, name, province, city, town, active in raw
                )
                result = StreamListPage(
                    count,
                    request.page,
                    request.page_size,
                    (count + request.page_size - 1) // request.page_size,
                    rows,
                )
            return result
        except StreamReadError:
            raise
        except Exception:
            raise StreamReadFailure() from None

    def region_options(self, level, *, province_code=None, city_county_code=None):
        try:
            if level not in ("province", "city_county", "town"):
                raise InvalidStreamReadRequest()
            if province_code is not None and not _code(province_code, 2):
                raise InvalidStreamReadRequest()
            if city_county_code is not None and not _code(city_county_code, 3):
                raise InvalidStreamReadRequest()
            if level == "city_county" and province_code is None:
                raise InvalidStreamReadRequest()
            if level == "town" and (province_code is None or city_county_code is None):
                raise InvalidStreamReadRequest()
            with read_transaction(self._connection):
                rows = self._repository.region_options(level, province_code, city_county_code)
            return tuple(RegionOption(code, name) for code, name in rows)
        except StreamReadError:
            raise
        except Exception:
            raise StreamReadFailure() from None

    def get_stream_detail(self, stream_code, *, display_policy=None):
        try:
            if not _code(stream_code, 11):
                raise InvalidStreamReadRequest()
            if display_policy is None:
                display_policy = CharacteristicDisplayPolicy()
            dictionary_ids = self._policy(display_policy)
            with read_transaction(self._connection):
                basic_row = self._repository.basic_stream(stream_code)
                if basic_row is None:
                    return None
                counts = self._repository.issue_counts_for_streams((stream_code,))
                basic = StreamBasicDetail(
                    *basic_row[:-1],
                    bool(basic_row[-1]),
                    _qc_state(counts[0][1:] if counts else None),
                )
                characteristics = self._characteristics(stream_code, dictionary_ids, display_policy)
                result = StreamReadDetail(basic, characteristics)
            return result
        except StreamReadError:
            raise
        except Exception:
            raise StreamReadFailure() from None

    def get_research_stream_detail(self, stream_code):
        """Phase 9C 상세를 고정 query 수로 조회한다. 연구 사전은 조회 중 생성하지 않는다."""
        try:
            from small_stream_research_tool.services.research_dictionary_bootstrap import (
                load_research_manifest,
                validate_research_manifest,
            )

            if not _code(stream_code, 11):
                raise InvalidStreamReadRequest()
            manifest = load_research_manifest()
            with read_transaction(self._connection):
                basic_row = self._repository.basic_stream(stream_code)
                if basic_row is None:
                    return None
                counts = self._repository.issue_counts_for_streams((stream_code,))
                basic = StreamBasicDetail(
                    *basic_row[:-1],
                    bool(basic_row[-1]),
                    _qc_state(counts[0][1:] if counts else None),
                )
                policy = self._research_policy(manifest, validate_research_manifest(manifest))
                dictionary_ids = self._policy(policy)
                if not dictionary_ids:
                    return StreamResearchDetail(basic, "UNINITIALIZED", ())
                rows = self._research_characteristics(stream_code, dictionary_ids, policy, manifest)
                return StreamResearchDetail(basic, "READY", rows)
        except StreamReadError:
            raise
        except Exception as error:
            # ResearchDictionaryError and SQLite failures remain safe at the GUI boundary.
            if error.__class__.__name__ == "ResearchDictionaryError":
                raise StreamReadFailure() from None
            raise StreamReadFailure() from None

    def _research_policy(self, manifest, digest):
        description = self._repository.research_version_description(manifest["manifest_version"])
        if description is None:
            return CharacteristicDisplayPolicy()
        if description != "research-manifest-sha256:" + digest:
            raise StreamReadFailure()
        specs = {row["internal_name"]: row for row in manifest["items"] if row["display_approved"]}
        rows = self._repository.dictionary_items_by_internal_names(tuple(specs))
        if len(rows) != len(specs):
            raise StreamReadFailure()
        ids = set()
        for row in rows:
            (
                dictionary_id,
                internal_name,
                standard_name,
                data_type,
                analyzable,
                active,
                deprecated,
                category_key,
                category_active,
                unit_symbol,
                unit_active,
            ) = row
            spec = specs.get(internal_name)
            if (
                spec is None
                or not active
                or deprecated is not None
                or not category_active
                or standard_name != spec["standard_name"]
                or data_type != spec["data_type"]
                or bool(analyzable) != spec["analyzable"]
                or category_key != spec["category_key"]
                or unit_symbol != spec["unit_symbol"]
                or (unit_symbol is not None and not unit_active)
            ):
                raise StreamReadFailure()
            ids.add(dictionary_id)
        return CharacteristicDisplayPolicy(frozenset(ids))

    def _research_characteristics(self, stream_code, dictionary_ids, policy, manifest):
        items = self._repository.dictionary_items_detail(dictionary_ids)
        metadata = {row["internal_name"]: row for row in manifest["items"]}
        reps = self._repository.active_representatives(stream_code, dictionary_ids)
        caches = dict(self._repository.caches(stream_code, dictionary_ids))
        representatives = {}
        for row in reps:
            representatives.setdefault(row[1], []).append(row)
        valid = {
            item_id: values[0]
            for item_id, values in representatives.items()
            if len(values) == 1 and caches.get(item_id) == values[0][0]
        }
        value_ids = tuple(row[0] for row in valid.values())
        issue_counts = {row[0]: row[1:] for row in self._repository.value_issues(value_ids)}
        issue_rows = self._repository.active_value_issue_details(value_ids)
        issues = {}
        for value_id, issue_type, severity, review_status, active in issue_rows:
            issues.setdefault(value_id, []).append(
                QCDisplayItem(
                    issue_type,
                    severity,
                    review_status,
                    f"{issue_type} 품질검사 항목",
                    bool(active),
                )
            )
        provenance_rows = {row[0]: row for row in self._repository.provenance(value_ids)}
        all_values = self._repository.values_for_items(stream_code, dictionary_ids)
        correction_children = set()
        if any(row[7] == "USER_CORRECTION" for row in all_values):
            for old_text, new_text in self._repository.correction_history(
                stream_code, dictionary_ids
            ):
                try:
                    old, new = json.loads(old_text), json.loads(new_text)
                    if _integer(old.get("source_value_id")) and _integer(
                        new.get("correction_value_id")
                    ):
                        correction_children.add(new["correction_value_id"])
                except (TypeError, ValueError, AttributeError):
                    continue
        history = {}
        for row in all_values:
            typed = _typed_value(row)
            classification = _source_classification(row[7])
            if classification == "IMPORT":
                summary = "Import 자료"
                if row[11]:
                    summary += f" · 배치 {row[11]}"
                if row[12] is not None:
                    summary += f" · 원본 행 {row[12]}"
            elif classification == "RESEARCHER_CORRECTION":
                summary = (
                    "연구자 보정값 · 이전 값에서 생성"
                    if row[0] in correction_children
                    else "연구자 보정값"
                )
            else:
                summary = "기타 등록 자료"
            history.setdefault(row[1], []).append(
                ValueHistoryDisplayRow(
                    typed,
                    row[6],
                    classification,
                    bool(row[8]),
                    row[1] in valid and valid[row[1]][0] == row[0],
                    row[10],
                    summary,
                )
            )
        result = []
        for item_id, internal_name, name, _data_type, category_key, category_name, _unit in items:
            item_reps = representatives.get(item_id, ())
            cache_id = caches.get(item_id)
            if not item_reps and cache_id is None:
                status = "UNASSIGNED"
            elif item_id in valid:
                status = "VALID_CURRENT"
            else:
                status = "INCONSISTENT"
            current = valid.get(item_id)
            provenance = None
            current_value = unit = qc_state = None
            qc_items = ()
            if current is not None:
                current_value = _typed_value(current)
                unit = current[15]
                qc_state = _qc_state(issue_counts.get(current[0]))
                source = provenance_rows.get(current[0])
                if source:
                    provenance = ProvenanceSummary(
                        _source_classification(source[5]),
                        source[1] if policy.show_source_file_name else None,
                        source[2] if policy.show_sheet_name else None,
                        source[3],
                        source[4],
                        None,
                    )
                qc_items = tuple(issues.get(current[0], ()))
            spec = metadata[internal_name]
            result.append(
                CharacteristicDetailRow(
                    item_id,
                    internal_name,
                    name,
                    category_key,
                    category_name,
                    status,
                    current_value,
                    unit,
                    qc_state,
                    provenance,
                    spec["representative_six"],
                    spec["focus_nine"],
                    qc_items,
                    tuple(history.get(item_id, ())),
                )
            )
        return tuple(result)

    def _characteristics(self, stream_code, dictionary_ids, policy):
        if not dictionary_ids:
            return ()
        items = self._repository.dictionary_items(dictionary_ids)
        reps = self._repository.active_representatives(stream_code, dictionary_ids)
        caches = dict(self._repository.caches(stream_code, dictionary_ids))
        by_item = {}
        for row in reps:
            by_item.setdefault(row[1], []).append(row)
        valid_ids = tuple(
            rows[0][0]
            for item_id, rows in by_item.items()
            if len(rows) == 1 and caches.get(item_id) == rows[0][0]
        )
        issues = {row[0]: row[1:] for row in self._repository.value_issues(valid_ids)}
        provenance = {row[0]: row for row in self._repository.provenance(valid_ids)}
        correction_parents = {}
        if any(row[5] == "USER_CORRECTION" for row in provenance.values()):
            for old_text, new_text in self._repository.correction_history(
                stream_code, dictionary_ids
            ):
                try:
                    old, new = json.loads(old_text), json.loads(new_text)
                    parent, child = old.get("source_value_id"), new.get("correction_value_id")
                    if _integer(parent) and _integer(child):
                        correction_parents[child] = parent
                except (TypeError, ValueError, AttributeError):
                    continue
        result = []
        for item_id, name, data_type, _dictionary_unit in items:
            representatives = by_item.get(item_id, ())
            cache_id = caches.get(item_id)
            if not representatives and cache_id is None:
                status = "UNASSIGNED"
            elif (
                len(representatives) == 1
                and cache_id == representatives[0][0]
                and representatives[0][12] == stream_code
                and representatives[0][13] == 1
                and representatives[0][14] == 1
            ):
                status = "VALID_CURRENT"
            else:
                status = "INCONSISTENT"
            if status != "VALID_CURRENT":
                result.append(CharacteristicSummary(item_id, name, data_type, status, None))
                continue
            value = representatives[0]
            typed = _typed_value(value)
            source = provenance.get(value[0])
            summary = None
            if source is not None:
                classification = _source_classification(source[5])
                summary = ProvenanceSummary(
                    classification,
                    source[1] if policy.show_source_file_name else None,
                    source[2] if policy.show_sheet_name else None,
                    source[3],
                    source[4],
                    correction_parents.get(value[0]),
                )
            result.append(
                CharacteristicSummary(
                    item_id,
                    name,
                    data_type,
                    status,
                    typed,
                    value[15],
                    _qc_state(issues.get(value[0])),
                    summary,
                )
            )
        return tuple(result)
