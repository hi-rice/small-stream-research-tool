"""경로·JSON·원본 내용을 노출하지 않는 Workspace 오류."""


class WorkspaceError(Exception):
    pass


class InvalidWorkspaceError(WorkspaceError):
    pass


class UnsupportedWorkspaceVersionError(WorkspaceError):
    pass


class WorkspaceUserMismatchError(WorkspaceError):
    pass


class WorkspaceSourceMissingError(WorkspaceError):
    pass


class WorkspaceSourceChangedError(WorkspaceError):
    pass


class WorkspaceIOError(WorkspaceError):
    pass


class UnsafeWorkspaceMetadataError(WorkspaceError):
    pass
