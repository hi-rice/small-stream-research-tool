"""원본 SQL·값·경로를 포함하지 않는 Import 저장소 오류."""


class PersistenceError(Exception):
    """SQLite 읽기 또는 쓰기 실패."""


class TransactionRequiredError(PersistenceError):
    """호출자가 쓰기 transaction을 열지 않음."""


class InvalidPersistenceArgumentError(PersistenceError):
    """저장소 API의 컬럼 또는 인자 계약 위반."""


class RecordNotFoundError(PersistenceError):
    """변경할 레코드 또는 INSERT 결과를 찾을 수 없음."""


class ConstraintViolationError(PersistenceError):
    """DB CHECK/NOT NULL 등 제약 위반."""


class DuplicateRecordError(ConstraintViolationError):
    """PK/UNIQUE 제약 위반."""


class ForeignKeyReferenceError(ConstraintViolationError):
    """존재하지 않는 FK 참조."""
