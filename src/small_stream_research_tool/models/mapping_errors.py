"""입력 원문을 메시지에 복제하지 않는 매핑 오류."""


class MappingError(Exception):
    pass


class InvalidMappingError(MappingError):
    pass


class MappingTargetUnavailableError(MappingError):
    pass
