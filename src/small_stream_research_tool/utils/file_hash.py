"""파일을 메모리에 복제하지 않는 SHA-256 계산."""

import hashlib
from pathlib import Path

HASH_CHUNK_SIZE = 1024 * 1024


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
