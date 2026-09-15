"""Phase 9A 읽기 전용 조회. DB 레코드를 안전한 표시 projection으로 제한한다."""

import json

from small_stream_research_tool.database.connection import read_transaction
from small_stream_research_tool.models.stream_read import (
    CharacteristicDisplayPolicy,
    CharacteristicSummary,
    ProvenanceSummary,
    RegionOption,
    StreamBasicDetail,
    StreamListPage,
    StreamListRequest,
    StreamListRow,
    StreamReadDetail,
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
            typed = tuple(v for v in value[2:6] if v is not None)
            if len(typed) != 1:
                raise StreamReadFailure()
            source = provenance.get(value[0])
            summary = None
            if source is not None:
                classification = (
                    "RESEARCHER_CORRECTION"
                    if source[5] == "USER_CORRECTION"
                    else "IMPORT"
                    if source[5] == "IMPORT"
                    else "OTHER_SOURCE"
                )
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
                    typed[0],
                    value[15],
                    _qc_state(issues.get(value[0])),
                    summary,
                )
            )
        return tuple(result)
