"""Home·작업이력·마이페이지가 공유하는 read-only application boundary."""

import json

from small_stream_research_tool.database.connection import read_transaction
from small_stream_research_tool.models.app_read import (
    HomeSummary,
    UserPublicProfile,
    WorkHistoryActorOption,
    WorkHistoryItem,
    WorkHistoryPage,
    WorkHistoryRequest,
)
from small_stream_research_tool.models.app_read_errors import (
    AppReadError,
    AppReadFailure,
    InactiveUserProfile,
    InvalidAppReadRequest,
    UserProfileNotFound,
)
from small_stream_research_tool.repositories.app_query_repository import (
    PAIR_EVENTS,
    VALUE_EVENTS,
    AppQueryRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryError,
    load_research_manifest,
    validate_research_manifest,
)

HISTORY_EVENTS = PAIR_EVENTS | VALUE_EVENTS
SAFE_REASON_CODES = frozenset(("RESEARCHER_SELECTION", "SOURCE_REVIEW", "QC_REVIEW_CONFIRMED"))
MAX_PAGE_SIZE = 100
HOME_HISTORY_LIMIT = 5


def _id(value):
    return type(value) is int and 0 < value < 2**63


def _stream_code(value):
    return type(value) is str and len(value) == 11 and value.isascii() and value.isdigit()


class AppReadService:
    """호출자가 소유한 한 connection에서 SELECT snapshot만 사용한다."""

    def __init__(self, connection):
        self._connection = connection
        self._repository = AppQueryRepository(connection)

    @staticmethod
    def _request(request):
        if type(request) is not WorkHistoryRequest:
            raise InvalidAppReadRequest()
        if not (
            _id(request.page)
            and type(request.page_size) is int
            and 1 <= request.page_size <= MAX_PAGE_SIZE
            and (request.change_type is None or request.change_type in HISTORY_EVENTS)
            and (request.actor_user_id is None or _id(request.actor_user_id))
            and (request.stream_code is None or _stream_code(request.stream_code))
        ):
            raise InvalidAppReadRequest()
        return request

    def get_home_summary(self):
        try:
            manifest = load_research_manifest()
            digest = validate_research_manifest(manifest)
            with read_transaction(self._connection):
                streams = self._repository.active_stream_count()
                errors, review = self._repository.qc_stream_counts()
                dictionary_state = self._dictionary_state(manifest, digest)
                recent = self._history_items(WorkHistoryRequest(page_size=HOME_HISTORY_LIMIT))
            return HomeSummary(streams, errors, review, dictionary_state, recent)
        except AppReadError:
            raise
        except ResearchDictionaryError:
            raise AppReadFailure() from None
        except Exception:
            raise AppReadFailure() from None

    def list_work_history(self, request=None):
        request = WorkHistoryRequest() if request is None else request
        request = self._request(request)
        try:
            with read_transaction(self._connection):
                total = self._repository.count_history(request)
                items = self._history_items(request)
            pages = (total + request.page_size - 1) // request.page_size
            return WorkHistoryPage(total, request.page, request.page_size, pages, items)
        except AppReadError:
            raise
        except Exception:
            raise AppReadFailure() from None

    def list_history_actor_options(self):
        try:
            with read_transaction(self._connection):
                rows = self._repository.history_actor_options()
            return tuple(WorkHistoryActorOption(row[0], row[1]) for row in rows)
        except Exception:
            raise AppReadFailure() from None

    def get_user_profile(self, user_id):
        if not _id(user_id):
            raise InvalidAppReadRequest()
        try:
            with read_transaction(self._connection):
                row = self._repository.public_user_profile(user_id)
            if row is None:
                raise UserProfileNotFound()
            profile = UserPublicProfile(*row[:4], bool(row[4]), row[5], row[6])
            if not profile.is_active:
                raise InactiveUserProfile()
            return profile
        except AppReadError:
            raise
        except Exception:
            raise AppReadFailure() from None

    def recent_user_work(self, user_id, limit=HOME_HISTORY_LIMIT):
        if not _id(user_id) or type(limit) is not int or not 1 <= limit <= 10:
            raise InvalidAppReadRequest()
        request = WorkHistoryRequest(page_size=limit, actor_user_id=user_id)
        try:
            with read_transaction(self._connection):
                return self._history_items(request)
        except AppReadError:
            raise
        except Exception:
            raise AppReadFailure() from None

    def _dictionary_state(self, manifest, digest):
        version = self._repository.research_version(manifest["manifest_version"])
        if version is None:
            return "NOT_INITIALIZED"
        if version != ("research-manifest-sha256:" + digest, 1):
            return "INCONSISTENT"
        specs = {row["internal_name"]: row for row in manifest["items"] if row["display_approved"]}
        rows = self._repository.dictionary_definitions(tuple(specs))
        if len(rows) != len(specs):
            return "INCONSISTENT"
        for row in rows:
            (
                _dictionary_id,
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
                return "INCONSISTENT"
        return "READY"

    @staticmethod
    def _key(raw):
        try:
            value = json.loads(raw)
            return value if type(value) is dict else None
        except (TypeError, ValueError, UnicodeError):
            return None

    def _history_items(self, request):
        rows = self._repository.page_history(request)
        parsed = []
        value_ids = set()
        for event, raw_key, reason, changed_at, actor_name in rows:
            key = self._key(raw_key)
            target = None
            if key is not None and event in PAIR_EVENTS:
                code, item = key.get("stream_code"), key.get("dictionary_id")
                if _stream_code(code) and _id(item):
                    target = (code, item)
            elif key is not None and event in VALUE_EVENTS:
                value_id = key.get("characteristic_value_id")
                if _id(value_id):
                    value_ids.add(value_id)
                    target = value_id
            parsed.append((event, target, reason, changed_at, actor_name))

        values = {
            row[0]: (row[1], row[2]) for row in self._repository.value_targets(tuple(value_ids))
        }
        targets = []
        stream_codes, dictionary_ids = set(), set()
        for event, target, reason, changed_at, actor_name in parsed:
            if event in VALUE_EVENTS and type(target) is int:
                target = values.get(target)
            if type(target) is tuple:
                stream_codes.add(target[0])
                dictionary_ids.add(target[1])
            targets.append((event, target, reason, changed_at, actor_name))
        stream_names = dict(self._repository.stream_names(tuple(stream_codes)))
        dictionary_names = dict(self._repository.dictionary_names(tuple(dictionary_ids)))

        result = []
        for event, target, reason, changed_at, actor_name in targets:
            resolved = (
                type(target) is tuple
                and target[0] in stream_names
                and target[1] in dictionary_names
            )
            safe_reason = reason if reason in SAFE_REASON_CODES else None
            reason_state = "NONE" if reason is None else "KNOWN" if safe_reason else "UNRECOGNIZED"
            result.append(
                WorkHistoryItem(
                    event,
                    actor_name,
                    "KNOWN" if actor_name is not None else "UNKNOWN",
                    target[0] if resolved else None,
                    stream_names.get(target[0]) if resolved else None,
                    dictionary_names.get(target[1]) if resolved else None,
                    "RESOLVED" if resolved else "UNRESOLVED",
                    safe_reason,
                    reason_state,
                    changed_at,
                )
            )
        return tuple(result)
