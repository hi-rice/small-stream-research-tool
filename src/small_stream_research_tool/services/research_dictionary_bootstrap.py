"""연구 사전 manifest를 schema migration과 분리해 원자적으로 등록한다."""

import hashlib
import json
import re
from dataclasses import dataclass
from importlib.resources import files

from small_stream_research_tool.models.stream_read import CharacteristicDisplayPolicy
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.services.dictionary_service import normalize_alias
from small_stream_research_tool.utils.timestamps import utc_now_text

_KEY = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
_TYPES = frozenset(("REAL", "INTEGER", "TEXT", "DATE", "DATETIME"))
_SENSITIVE = ("service_key", "cctv", "rtsp", "password", "contact", "phone", "_ip")
_AMBIGUOUS = frozenset(
    ("A", "B", "C", "D", "전체", "정비", "미정비", "빈도", "홍수량", "하폭", "전", "답")
)
_ITEM_FIELDS = frozenset(
    (
        "research_concept",
        "standard_name",
        "internal_name",
        "category_key",
        "data_type",
        "unit_symbol",
        "analyzable",
        "aliases",
        "representative_six",
        "focus_nine",
        "display_approved",
    )
)


class ResearchDictionaryError(Exception):
    def __init__(self):
        super().__init__("연구 사전 정의를 적용할 수 없습니다.")


@dataclass(frozen=True)
class BootstrapResult:
    manifest_version: str
    fingerprint: str
    category_count: int
    unit_count: int
    item_count: int
    alias_count: int


def load_research_manifest(version="research-dictionary-v1"):
    names = {
        "research-dictionary-v1": "research_dictionary_v1.json",
        "research-dictionary-v2": "research_dictionary_v2.json",
    }
    if version not in names:
        raise ResearchDictionaryError()
    path = files("small_stream_research_tool").joinpath("resources", names[version])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ResearchDictionaryError() from None


def manifest_fingerprint(manifest):
    try:
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise ResearchDictionaryError() from None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_research_manifest(manifest):
    try:
        if type(manifest) is not dict or set(manifest) != {
            "manifest_version",
            "source_scope",
            "categories",
            "units",
            "items",
        }:
            raise ValueError
        if not _KEY.fullmatch(manifest["manifest_version"].replace("-", "_")):
            raise ValueError
        if manifest["source_scope"] != "NATIONAL_2024":
            raise ValueError
        categories, units, items = (manifest["categories"], manifest["units"], manifest["items"])
        if not all(type(v) is list and v for v in (categories, units, items)):
            raise ValueError
        category_keys, unit_symbols, internal_names, aliases = set(), set(), set(), set()
        for row in categories:
            if type(row) is not dict or set(row) != {"key", "name", "sort_order"}:
                raise ValueError
            if (
                not _KEY.fullmatch(row["key"])
                or not row["name"]
                or type(row["sort_order"]) is not int
            ):
                raise ValueError
            if row["key"] in category_keys:
                raise ValueError
            category_keys.add(row["key"])
        for row in units:
            if type(row) is not dict or set(row) != {"symbol", "name"}:
                raise ValueError
            if type(row["symbol"]) is not str or not row["symbol"] or not row["name"]:
                raise ValueError
            if row["symbol"] in unit_symbols:
                raise ValueError
            unit_symbols.add(row["symbol"])
        for row in items:
            if type(row) is not dict or set(row) != _ITEM_FIELDS:
                raise ValueError
            key = row["internal_name"]
            if type(key) is not str or not _KEY.fullmatch(key) or key in internal_names:
                raise ValueError
            if any(word in key for word in _SENSITIVE) or "연락처" in row["standard_name"]:
                raise ValueError
            internal_names.add(key)
            if row["category_key"] not in category_keys or row["data_type"] not in _TYPES:
                raise ValueError
            if row["unit_symbol"] is not None and row["unit_symbol"] not in unit_symbols:
                raise ValueError
            if not all(
                type(row[name]) is bool
                for name in ("analyzable", "representative_six", "focus_nine", "display_approved")
            ):
                raise ValueError
            if row["analyzable"] and row["data_type"] not in ("REAL", "INTEGER"):
                raise ValueError
            if not all(
                type(row[name]) is str and row[name].strip()
                for name in ("research_concept", "standard_name")
            ):
                raise ValueError
            if type(row["aliases"]) is not list or not row["aliases"]:
                raise ValueError
            for alias in row["aliases"]:
                if type(alias) is not dict or set(alias) != {"name", "source_scope"}:
                    raise ValueError
                if alias["source_scope"] != manifest["source_scope"]:
                    raise ValueError
                name = alias["name"]
                if type(name) is not str or not name.strip() or name.strip() in _AMBIGUOUS:
                    raise ValueError
                if "|" in name and " | " not in name:
                    raise ValueError
                normalized = normalize_alias(name)
                identity = (normalized, alias["source_scope"])
                if identity in aliases:
                    raise ValueError
                aliases.add(identity)
        for side in ("source", "end"):
            suffixes = {
                name.removeprefix(side + "_")
                for name in internal_names
                if name.startswith(side + "_")
            }
            other = "end" if side == "source" else "source"
            if any(other + "_" + suffix not in internal_names for suffix in suffixes):
                raise ValueError
        if len(items) != 70 or len([r for r in items if r["category_key"] == "land_use"]) != 32:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ResearchDictionaryError() from None
    return manifest_fingerprint(manifest)


class ResearchDictionaryBootstrapService:
    def __init__(self, connection):
        self._connection = connection
        self._repo = DictionaryRepository(connection)

    def bootstrap(self, manifest=None):
        manifest = load_research_manifest() if manifest is None else manifest
        digest = validate_research_manifest(manifest)
        stamp = utc_now_text()
        try:
            with self._repo.transaction():
                version = next(
                    (
                        v
                        for v in self._repo.list_versions()
                        if v.version == manifest["manifest_version"]
                    ),
                    None,
                )
                description = "research-manifest-sha256:" + digest
                if version is None:
                    version = self._repo.create_version(
                        version=manifest["manifest_version"],
                        description=description,
                        created_at=stamp,
                    )
                elif version.description != description:
                    raise ResearchDictionaryError()
                categories = self._categories(manifest["categories"], stamp)
                units = self._units(manifest["units"], stamp)
                items, alias_count = self._items(
                    manifest["items"], version.version_id, categories, units, stamp
                )
                # 하나의 명시적 사전 bootstrap 동작으로 Import prerequisite도 준비하되,
                # 연구 manifest의 버전·fingerprint·표시 정책과는 분리한다.
                from small_stream_research_tool.services.import_core_dictionary_bootstrap import (
                    ImportCoreDictionaryBootstrapService,
                )

                ImportCoreDictionaryBootstrapService(self._connection).bootstrap()
                current = self._repo.get_current_version()
                is_v1_request_on_v2 = (
                    current is not None
                    and current.version == "research-dictionary-v2"
                    and manifest["manifest_version"] == "research-dictionary-v1"
                )
                if not is_v1_request_on_v2 and (
                    current is None or current.version_id != version.version_id
                ):
                    self._repo.set_current_version(version.version_id)
            return BootstrapResult(
                manifest["manifest_version"],
                digest,
                len(categories),
                len(units),
                len(items),
                alias_count,
            )
        except ResearchDictionaryError:
            raise
        except Exception:
            raise ResearchDictionaryError() from None

    def bootstrap_v2(self):
        """Bootstrap V2 on a fresh database or upgrade an existing V1 database."""
        current = self._repo.get_current_version()
        if current is None:
            return self.bootstrap(load_research_manifest("research-dictionary-v2"))
        return self.upgrade_to_v2()

    def upgrade_to_v2(self):
        """Upgrade an unused V1 definition set to V2 in one transaction."""
        v1 = load_research_manifest("research-dictionary-v1")
        v2 = load_research_manifest("research-dictionary-v2")
        validate_research_manifest(v1)
        digest = validate_research_manifest(v2)
        expected = {
            "arrival_time": "hr",
            "storage_constant": "hr",
            "initial_loss": "mm",
            "source_plan_frequency": "year",
            "end_plan_frequency": "year",
        }
        left = {row["internal_name"]: row for row in v1["items"]}
        right = {row["internal_name"]: row for row in v2["items"]}
        if set(left) != set(right) or len(right) != 70:
            raise ResearchDictionaryError()
        for name, old in left.items():
            changed = {**old, "unit_symbol": expected.get(name, old["unit_symbol"])}
            if right[name] != changed:
                raise ResearchDictionaryError()
        stamp = utc_now_text()
        try:
            with self._repo.transaction():
                current = self._repo.get_current_version()
                if current is None or current.version != "research-dictionary-v1":
                    if current is not None and current.version == "research-dictionary-v2":
                        version = next(
                            (
                                version
                                for version in self._repo.list_versions()
                                if version.version == v2["manifest_version"]
                            ),
                            None,
                        )
                        if (
                            version is None
                            or version.description != "research-manifest-sha256:" + digest
                        ):
                            raise ResearchDictionaryError()
                        self._verify_manifest(v2)
                        return self._v2_result(v2, digest)
                    raise ResearchDictionaryError()
                units = self._units(v2["units"], stamp)
                rows = {}
                for name in expected:
                    row = self._repo.get_item_by_internal_name(name)
                    if row is None or self._repo.item_in_use(row.dictionary_id):
                        raise ResearchDictionaryError()
                    rows[name] = row
                version = next(
                    (v for v in self._repo.list_versions() if v.version == v2["manifest_version"]),
                    None,
                )
                description = "research-manifest-sha256:" + digest
                if version is None:
                    version = self._repo.create_version(
                        version=v2["manifest_version"], description=description, created_at=stamp
                    )
                elif version.description != description:
                    raise ResearchDictionaryError()
                for name, symbol in expected.items():
                    self._repo.update_item_definition(
                        rows[name].dictionary_id, {"unit_id": units[symbol].unit_id}, stamp
                    )
                self._verify_manifest(v2)
                self._repo.set_current_version(version.version_id)
            return self._v2_result(v2, digest)
        except ResearchDictionaryError:
            raise
        except Exception:
            raise ResearchDictionaryError() from None

    @staticmethod
    def _v2_result(manifest, digest):
        return BootstrapResult(
            manifest["manifest_version"],
            digest,
            len(manifest["categories"]),
            len(manifest["units"]),
            len(manifest["items"]),
            sum(len(row["aliases"]) for row in manifest["items"]),
        )

    def _verify_manifest(self, manifest):
        categories = {r.category_key: r for r in self._repo.list_categories(active_only=False)}
        units = {r.unit_symbol: r for r in self._repo.list_units(active_only=False)}
        for spec in manifest["items"]:
            row = self._repo.get_item_by_internal_name(spec["internal_name"])
            unit = units.get(spec["unit_symbol"]) if spec["unit_symbol"] else None
            category = categories.get(spec["category_key"])
            if (
                row is None
                or category is None
                or not row.is_active
                or row.deprecated_version_id is not None
                or row.standard_name != spec["standard_name"]
                or row.category_id != category.category_id
                or row.data_type != spec["data_type"]
                or row.unit_id != (unit.unit_id if unit else None)
                or row.analyzable != spec["analyzable"]
            ):
                raise ResearchDictionaryError()

    def _categories(self, definitions, stamp):
        existing = {r.category_key: r for r in self._repo.list_categories(active_only=False)}
        result = {}
        for spec in definitions:
            row = existing.get(spec["key"])
            if row is None:
                row = self._repo.create_category(
                    category_key=spec["key"],
                    category_name=spec["name"],
                    parent_category_id=None,
                    sort_order=spec["sort_order"],
                    created_at=stamp,
                    updated_at=stamp,
                )
            elif not (
                row.is_active
                and row.category_name == spec["name"]
                and row.parent_category_id is None
                and row.sort_order == spec["sort_order"]
            ):
                raise ResearchDictionaryError()
            result[spec["key"]] = row
        return result

    def _units(self, definitions, stamp):
        existing = {r.unit_symbol: r for r in self._repo.list_units(active_only=False)}
        result = {}
        for spec in definitions:
            row = existing.get(spec["symbol"])
            if row is None:
                row = self._repo.create_unit(
                    unit_name=spec["name"],
                    unit_symbol=spec["symbol"],
                    dimension=None,
                    created_at=stamp,
                    updated_at=stamp,
                )
            elif not (row.is_active and row.unit_name == spec["name"] and row.dimension is None):
                raise ResearchDictionaryError()
            result[spec["symbol"]] = row
        return result

    def _items(self, definitions, version_id, categories, units, stamp):
        result, alias_count = {}, 0
        for spec in definitions:
            cat_id = categories[spec["category_key"]].category_id
            unit_id = units[spec["unit_symbol"]].unit_id if spec["unit_symbol"] else None
            row = self._repo.get_item_by_internal_name(spec["internal_name"])
            if row is None:
                row = self._repo.create_item(
                    standard_name=spec["standard_name"],
                    internal_name=spec["internal_name"],
                    category_id=cat_id,
                    data_type=spec["data_type"],
                    unit_id=unit_id,
                    description=None,
                    storage_type="FLEX",
                    analyzable=spec["analyzable"],
                    required=False,
                    nullable=True,
                    created_version_id=version_id,
                    deprecated_version_id=None,
                    is_active=True,
                    created_at=stamp,
                    updated_at=stamp,
                )
            elif not (
                row.is_active
                and row.deprecated_version_id is None
                and row.standard_name == spec["standard_name"]
                and row.category_id == cat_id
                and row.data_type == spec["data_type"]
                and row.unit_id == unit_id
                and row.description is None
                and row.storage_type == "FLEX"
                and row.analyzable == spec["analyzable"]
                and not row.required
                and row.nullable
            ):
                raise ResearchDictionaryError()
            result[spec["internal_name"]] = row
            for alias in spec["aliases"]:
                normalized = normalize_alias(alias["name"])
                prior = self._repo.find_alias(normalized, alias["source_scope"])
                if prior is None:
                    self._repo.create_alias(
                        dictionary_id=row.dictionary_id,
                        alias_name=alias["name"],
                        normalized_alias=normalized,
                        source_scope=alias["source_scope"],
                        created_at=stamp,
                        updated_at=stamp,
                    )
                elif not (
                    prior.is_active
                    and prior.dictionary_id == row.dictionary_id
                    and prior.alias_name == alias["name"]
                ):
                    raise ResearchDictionaryError()
                alias_count += 1
        return result, alias_count

    def approved_display_policy(self, manifest=None):
        if manifest is None:
            current = self._repo.get_current_version()
            version = (
                current.version
                if current and current.version.startswith("research-dictionary-v")
                else "research-dictionary-v1"
            )
            manifest = load_research_manifest(version)
        digest = validate_research_manifest(manifest)
        version = next(
            (v for v in self._repo.list_versions() if v.version == manifest["manifest_version"]),
            None,
        )
        if version is None:
            return CharacteristicDisplayPolicy()
        if version.description != "research-manifest-sha256:" + digest:
            raise ResearchDictionaryError()
        categories = {r.category_key: r for r in self._repo.list_categories(active_only=False)}
        units = {r.unit_symbol: r for r in self._repo.list_units(active_only=False)}
        ids = set()
        for spec in manifest["items"]:
            if not spec["display_approved"]:
                continue
            item = self._repo.get_item_by_internal_name(spec["internal_name"])
            category = categories.get(spec["category_key"])
            unit = units.get(spec["unit_symbol"]) if spec["unit_symbol"] else None
            if (
                item is None
                or category is None
                or not category.is_active
                or not item.is_active
                or item.deprecated_version_id is not None
                or item.category_id != category.category_id
                or item.data_type != spec["data_type"]
                or item.standard_name != spec["standard_name"]
                or item.unit_id != (unit.unit_id if unit else None)
                or (unit is not None and not unit.is_active)
            ):
                raise ResearchDictionaryError()
            ids.add(item.dictionary_id)
        return CharacteristicDisplayPolicy(frozenset(ids))
