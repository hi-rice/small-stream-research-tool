"""연구 사전과 분리된 Import 식별·기본정보 사전을 원자적으로 등록한다."""

import hashlib
import json
import re
from contextlib import nullcontext
from dataclasses import dataclass
from importlib.resources import files

from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.services.dictionary_service import normalize_alias
from small_stream_research_tool.utils.timestamps import utc_now_text

_KEY = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
_EXPECTED = {
    "stream_code": "IDENTITY",
    "province_code": "IDENTITY",
    "city_county_code": "IDENTITY",
    "town_code": "IDENTITY",
    "stream_serial_no": "IDENTITY",
    "stream_name": "STREAM_MASTER",
}


class ImportCoreDictionaryError(Exception):
    def __init__(self):
        super().__init__("Import 기본정보 사전 정의를 적용할 수 없습니다.")


@dataclass(frozen=True)
class ImportCoreBootstrapResult:
    manifest_version: str
    fingerprint: str
    item_count: int
    alias_count: int


def load_import_core_manifest():
    path = files("small_stream_research_tool").joinpath("resources/import_core_dictionary_v1.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ImportCoreDictionaryError() from None


def import_core_fingerprint(manifest):
    try:
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise ImportCoreDictionaryError() from None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_import_core_manifest(manifest):
    try:
        if type(manifest) is not dict or set(manifest) != {
            "manifest_version",
            "category",
            "items",
        }:
            raise ValueError
        if manifest["manifest_version"] != "import-core-dictionary-v1":
            raise ValueError
        category = manifest["category"]
        if type(category) is not dict or set(category) != {"key", "name", "sort_order"}:
            raise ValueError
        if (
            category["key"] != "import_core"
            or not category["name"]
            or type(category["sort_order"]) is not int
        ):
            raise ValueError
        items = manifest["items"]
        if type(items) is not list or len(items) != len(_EXPECTED):
            raise ValueError
        names, aliases = set(), set()
        for item in items:
            if type(item) is not dict or set(item) != {
                "standard_name",
                "internal_name",
                "data_type",
                "role",
                "aliases",
            }:
                raise ValueError
            name = item["internal_name"]
            if (
                not _KEY.fullmatch(name)
                or name in names
                or _EXPECTED.get(name) != item["role"]
                or item["data_type"] != "TEXT"
                or not item["standard_name"].strip()
            ):
                raise ValueError
            names.add(name)
            if type(item["aliases"]) is not list or not item["aliases"]:
                raise ValueError
            for alias in item["aliases"]:
                if type(alias) is not dict or set(alias) != {"name", "source_scope"}:
                    raise ValueError
                if alias["source_scope"] != "NATIONAL_2024" or not alias["name"].strip():
                    raise ValueError
                identity = (normalize_alias(alias["name"]), alias["source_scope"])
                if identity in aliases:
                    raise ValueError
                aliases.add(identity)
        if names != set(_EXPECTED):
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ImportCoreDictionaryError() from None
    return import_core_fingerprint(manifest)


class ImportCoreDictionaryBootstrapService:
    def __init__(self, connection):
        self._connection = connection
        self._repo = DictionaryRepository(connection)

    def bootstrap(self, manifest=None):
        manifest = load_import_core_manifest() if manifest is None else manifest
        digest = validate_import_core_manifest(manifest)
        stamp = utc_now_text()
        try:
            boundary = (
                nullcontext() if self._connection.in_transaction else self._repo.transaction()
            )
            with boundary:
                description = "import-core-manifest-sha256:" + digest
                version = next(
                    (
                        row
                        for row in self._repo.list_versions()
                        if row.version == manifest["manifest_version"]
                    ),
                    None,
                )
                if version is None:
                    version = self._repo.create_version(
                        version=manifest["manifest_version"],
                        description=description,
                        created_at=stamp,
                    )
                elif version.description != description:
                    raise ImportCoreDictionaryError()
                category_spec = manifest["category"]
                category = next(
                    (
                        row
                        for row in self._repo.list_categories(active_only=False)
                        if row.category_key == category_spec["key"]
                    ),
                    None,
                )
                if category is None:
                    category = self._repo.create_category(
                        category_key=category_spec["key"],
                        category_name=category_spec["name"],
                        parent_category_id=None,
                        sort_order=category_spec["sort_order"],
                        is_active=True,
                        created_at=stamp,
                        updated_at=stamp,
                    )
                elif not (
                    category.is_active
                    and category.category_name == category_spec["name"]
                    and category.parent_category_id is None
                    and category.sort_order == category_spec["sort_order"]
                ):
                    raise ImportCoreDictionaryError()
                alias_count = 0
                for spec in manifest["items"]:
                    item = self._repo.get_item_by_internal_name(spec["internal_name"])
                    if item is None:
                        item = self._repo.create_item(
                            standard_name=spec["standard_name"],
                            internal_name=spec["internal_name"],
                            category_id=category.category_id,
                            data_type="TEXT",
                            unit_id=None,
                            description="Import " + spec["role"],
                            storage_type="CORE",
                            analyzable=False,
                            required=False,
                            nullable=True,
                            created_version_id=version.version_id,
                            deprecated_version_id=None,
                            is_active=True,
                            created_at=stamp,
                            updated_at=stamp,
                        )
                    elif not (
                        item.is_active
                        and item.deprecated_version_id is None
                        and item.standard_name == spec["standard_name"]
                        and item.category_id == category.category_id
                        and item.data_type == "TEXT"
                        and item.unit_id is None
                        and item.description == "Import " + spec["role"]
                        and item.storage_type == "CORE"
                        and not item.analyzable
                        and not item.required
                        and item.nullable
                        and item.created_version_id == version.version_id
                    ):
                        raise ImportCoreDictionaryError()
                    for alias in spec["aliases"]:
                        normalized = normalize_alias(alias["name"])
                        prior = self._repo.find_alias(normalized, alias["source_scope"])
                        if prior is None:
                            self._repo.create_alias(
                                dictionary_id=item.dictionary_id,
                                alias_name=alias["name"],
                                normalized_alias=normalized,
                                source_scope=alias["source_scope"],
                                is_active=True,
                                created_at=stamp,
                                updated_at=stamp,
                            )
                        elif not (
                            prior.is_active
                            and prior.dictionary_id == item.dictionary_id
                            and prior.alias_name == alias["name"]
                        ):
                            raise ImportCoreDictionaryError()
                        alias_count += 1
            return ImportCoreBootstrapResult(
                manifest["manifest_version"], digest, len(manifest["items"]), alias_count
            )
        except ImportCoreDictionaryError:
            raise
        except Exception:
            raise ImportCoreDictionaryError() from None
