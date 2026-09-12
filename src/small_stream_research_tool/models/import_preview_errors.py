"""입력 원문이나 DB 상세를 노출하지 않는 Preview application 오류."""


class ImportPreviewError(Exception):
    pass


class InvalidPreviewArgumentError(ImportPreviewError):
    pass


class StreamLookupError(ImportPreviewError):
    pass


class PreviewSourceChangedError(ImportPreviewError):
    pass
