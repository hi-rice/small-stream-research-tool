"""외부 오류 원문을 노출하지 않는 복구 domain 오류."""


class ImportRecoveryError(Exception):
    def __init__(self):
        super().__init__("Import 복구 상태를 확인하거나 기록할 수 없습니다.")


class ImportRecoveryStateError(ImportRecoveryError):
    def __init__(self):
        Exception.__init__(self, "복구 대상 또는 현재 상태를 확인해야 합니다.")


class ImportRecoveryConsistencyError(ImportRecoveryError):
    def __init__(self):
        Exception.__init__(self, "성공 복구에 필요한 일관성 근거가 충족되지 않았습니다.")
