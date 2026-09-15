"""GUI에 SQL·경로·원본 연구값을 전달하지 않는 조회 오류."""


class StreamReadError(Exception):
    def __init__(self):
        super().__init__("소하천 조회를 완료할 수 없습니다.")


class InvalidStreamReadRequest(StreamReadError):
    def __init__(self):
        Exception.__init__(self, "조회 조건을 확인해야 합니다.")


class StreamReadFailure(StreamReadError):
    def __init__(self):
        Exception.__init__(self, "소하천 자료를 조회할 수 없습니다.")
