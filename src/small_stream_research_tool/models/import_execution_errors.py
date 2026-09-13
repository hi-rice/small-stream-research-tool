"""원문 DB 오류와 입력값을 노출하지 않는 실행 오류."""


class ImportExecutionError(Exception):
    pass


class ImportPreflightError(ImportExecutionError):
    def __init__(self):
        super().__init__("Import 실행 전 입력 또는 참조 확인이 필요합니다.")


class DuplicateImportError(ImportPreflightError):
    def __init__(self):
        ImportExecutionError.__init__(self, "이미 사용된 Import batch입니다. 재실행할 수 없습니다.")


class ImportTransactionError(ImportExecutionError):
    def __init__(self, phase, result):
        super().__init__("Import transaction이 실패했습니다.")
        self.phase = phase
        self.result = result


class ImportFinalizeError(ImportExecutionError):
    def __init__(self, result):
        super().__init__("Import 종료 기록에 실패했습니다. 별도 복구 확인이 필요합니다.")
        self.phase = "C"
        self.result = result
        self.recovery_required = True
