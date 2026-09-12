"""사전 관리에서 필요한 오류. 원본 입력을 오류 메시지에 복제하지 않는다."""


class DictionaryError(Exception):
    pass


class InvalidDictionaryDefinitionError(DictionaryError):
    pass


class DuplicateDefinitionError(DictionaryError):
    pass


class DuplicateAliasError(DuplicateDefinitionError):
    pass


class DictionaryEntryNotFoundError(DictionaryError):
    pass


class DictionaryItemInUseError(DictionaryError):
    pass


class UnitConversionError(DictionaryError):
    pass
