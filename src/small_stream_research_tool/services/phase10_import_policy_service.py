"""현재 사전의 승인 항목만 Preview와 Import에 통과시킨다."""

from small_stream_research_tool.database.connection import read_transaction
from small_stream_research_tool.models.import_preparation import (
    CORE_COORDINATE_LIMITS,
    CORE_TEXT_FIELDS,
    ImportFieldPolicy,
)
from small_stream_research_tool.models.import_preview import PreviewFieldPolicy
from small_stream_research_tool.models.phase10_import_policy import (
    UNIT_CONFIRMED,
    UNIT_NEEDS_REVIEW,
    UNIT_NOT_APPLICABLE,
    Phase10ImportPolicies,
    UnitConfirmation,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
    ResearchDictionaryError,
)

CORE_ALLOWED = frozenset(
    (
        "stream_code",
        "province_code",
        "city_county_code",
        "town_code",
        "stream_serial_no",
        "stream_name",
        *CORE_TEXT_FIELDS,
        *CORE_COORDINATE_LIMITS,
    )
)


class Phase10ImportPolicyService:
    def __init__(self, connection):
        self._connection = connection

    def policies(self):
        try:
            with read_transaction(self._connection):
                repo = DictionaryRepository(self._connection)
                approved_ids = (
                    ResearchDictionaryBootstrapService(self._connection)
                    .approved_display_policy()
                    .allowed_dictionary_ids
                )
                items = repo.list_items(active_only=False)
                approved = CORE_ALLOWED | frozenset(
                    item.internal_name for item in items if item.dictionary_id in approved_ids
                )
                excluded = frozenset(
                    item.internal_name for item in items if item.internal_name not in approved
                )
            return Phase10ImportPolicies(
                PreviewFieldPolicy(excluded_internal_names=excluded),
                ImportFieldPolicy(excluded_internal_names=excluded),
                approved,
            )
        except ResearchDictionaryError:
            raise
        except Exception:
            raise ResearchDictionaryError() from None

    def unit_confirmation(self, dictionary_id, source_unit=None):
        """정확히 일치하는 단위만 확인한다. 변환·별칭 추정은 하지 않는다."""
        if type(dictionary_id) is not int or dictionary_id <= 0:
            raise ResearchDictionaryError()
        if source_unit is not None and (type(source_unit) is not str or not source_unit):
            raise ResearchDictionaryError()
        try:
            with read_transaction(self._connection):
                repo = DictionaryRepository(self._connection)
                item = repo.get_item(dictionary_id)
                if item is None or not item.is_active:
                    raise ResearchDictionaryError()
                if item.unit_id is None:
                    status = UNIT_NOT_APPLICABLE if source_unit is None else UNIT_NEEDS_REVIEW
                else:
                    unit = repo.get_unit(item.unit_id)
                    status = (
                        UNIT_CONFIRMED
                        if unit is not None and unit.is_active and source_unit == unit.unit_symbol
                        else UNIT_NEEDS_REVIEW
                    )
            return UnitConfirmation(dictionary_id, status, source_unit)
        except ResearchDictionaryError:
            raise
        except Exception:
            raise ResearchDictionaryError() from None
