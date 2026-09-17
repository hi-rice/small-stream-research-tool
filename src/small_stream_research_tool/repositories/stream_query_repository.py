"""Phase 9A의 bounded SELECT만 담당한다. 임의 SQL/정렬 입력을 받지 않는다."""

import sqlite3

from small_stream_research_tool.models.stream_read_errors import StreamReadFailure

SORT_COLUMNS = {
    "stream_code": "s.stream_code",
    "stream_name": "s.stream_name",
    "province": "s.province_name",
    "city_county": "s.city_county_name",
    "town": "s.town_name",
}


def _marks(values):
    return ",".join("?" for _ in values)


class StreamQueryRepository:
    def __init__(self, connection):
        self._connection = connection

    def _rows(self, sql, params=()):
        try:
            cursor = self._connection.execute(sql, params)
            try:
                return tuple(cursor.fetchall())
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise StreamReadFailure() from None

    def _where(self, request):
        clauses, params = [], []
        if request.active_only:
            clauses.append("s.is_active=1")
        for column, value in (
            ("province_code", request.province_code),
            ("city_county_code", request.city_county_code),
            ("town_code", request.town_code),
        ):
            if value is not None:
                clauses.append(f"s.{column}=?")
                params.append(value)
        if request.search:
            if request.search.isascii() and request.search.isdigit():
                if len(request.search) == 11:
                    clauses.append("s.stream_code=?")
                    params.append(request.search)
                else:
                    clauses.append("s.stream_code LIKE ?")
                    params.append(request.search + "%")
            else:
                escaped = (
                    request.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                clauses.append("s.stream_name LIKE ? ESCAPE '\\'")
                params.append("%" + escaped + "%")
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), tuple(params)

    def count_streams(self, request):
        where, params = self._where(request)
        return self._rows("SELECT count(*) FROM small_stream s" + where, params)[0][0]

    def region_options(self, level, province_code=None, city_county_code=None):
        columns = {
            "province": ("province_code", "province_name"),
            "city_county": ("city_county_code", "city_county_name"),
            "town": ("town_code", "town_name"),
        }
        code, name = columns[level]
        clauses = ["is_active=1"]
        params = []
        if province_code is not None:
            clauses.append("province_code=?")
            params.append(province_code)
        if city_county_code is not None:
            clauses.append("city_county_code=?")
            params.append(city_county_code)
        return self._rows(
            f"SELECT {code},MIN(COALESCE(NULLIF({name},''),{code})) "
            "FROM small_stream WHERE "
            + " AND ".join(clauses)
            + f" GROUP BY {code} ORDER BY {code}",
            tuple(params),
        )

    def page_streams(self, request):
        where, params = self._where(request)
        order = SORT_COLUMNS[request.sort_field] + " " + request.sort_direction
        if request.sort_field != "stream_code":
            order += ",s.stream_code ASC"
        return self._rows(
            "SELECT s.stream_code,s.stream_name,"
            "COALESCE(s.province_name,s.province_code),"
            "COALESCE(s.city_county_name,s.city_county_code),"
            "COALESCE(s.town_name,s.town_code),s.is_active "
            "FROM small_stream s" + where + " ORDER BY " + order + " LIMIT ? OFFSET ?",
            (*params, request.page_size, (request.page - 1) * request.page_size),
        )

    def issue_counts_for_streams(self, stream_codes):
        if not stream_codes:
            return ()
        return self._rows(
            "SELECT stream_code,"
            "sum(CASE WHEN severity='ERROR' THEN 1 ELSE 0 END),"
            "sum(CASE WHEN severity='WARNING' THEN 1 ELSE 0 END),"
            "sum(CASE WHEN severity='INFO' THEN 1 ELSE 0 END) "
            "FROM data_quality_issue WHERE is_active=1 AND stream_code IN ("
            + _marks(stream_codes)
            + ") GROUP BY stream_code",
            stream_codes,
        )

    def basic_stream(self, stream_code):
        rows = self._rows(
            "SELECT stream_code,stream_name,COALESCE(province_name,province_code),"
            "COALESCE(city_county_name,city_county_code),COALESCE(town_name,town_code),"
            "river_system,source_address,end_address,source_latitude,source_longitude,"
            "end_latitude,end_longitude,is_active "
            "FROM small_stream WHERE stream_code=?",
            (stream_code,),
        )
        return rows[0] if rows else None

    def dictionary_items(self, dictionary_ids):
        if not dictionary_ids:
            return ()
        return self._rows(
            "SELECT d.dictionary_id,d.standard_name,d.data_type,u.unit_symbol "
            "FROM data_dictionary d LEFT JOIN unit_dictionary u ON u.unit_id=d.unit_id "
            "WHERE d.dictionary_id IN (" + _marks(dictionary_ids) + ") "
            "ORDER BY d.dictionary_id",
            dictionary_ids,
        )

    def dictionary_items_detail(self, dictionary_ids):
        if not dictionary_ids:
            return ()
        return self._rows(
            "SELECT d.dictionary_id,d.internal_name,d.standard_name,d.data_type,"
            "c.category_key,c.category_name,u.unit_symbol "
            "FROM data_dictionary d JOIN data_category c ON c.category_id=d.category_id "
            "LEFT JOIN unit_dictionary u ON u.unit_id=d.unit_id "
            "WHERE d.is_active=1 AND d.deprecated_version_id IS NULL "
            "AND c.is_active=1 AND d.dictionary_id IN (" + _marks(dictionary_ids) + ") "
            "ORDER BY c.sort_order,d.dictionary_id",
            dictionary_ids,
        )

    def research_version_description(self, version):
        rows = self._rows("SELECT description FROM dictionary_version WHERE version=?", (version,))
        return rows[0][0] if rows else None

    def dictionary_items_by_internal_names(self, internal_names):
        if not internal_names:
            return ()
        return self._rows(
            "SELECT d.dictionary_id,d.internal_name,d.standard_name,d.data_type,"
            "d.analyzable,d.is_active,d.deprecated_version_id,c.category_key,c.is_active,"
            "u.unit_symbol,u.is_active "
            "FROM data_dictionary d JOIN data_category c ON c.category_id=d.category_id "
            "LEFT JOIN unit_dictionary u ON u.unit_id=d.unit_id "
            "WHERE d.internal_name IN (" + _marks(internal_names) + ")",
            internal_names,
        )

    def active_representatives(self, stream_code, dictionary_ids):
        if not dictionary_ids:
            return ()
        return self._rows(
            "SELECT v.characteristic_value_id,v.dictionary_id,v.value_number,v.value_integer,"
            "v.value_text,v.value_date,v.unit_id,v.source_type,v.import_id,v.import_sheet_id,"
            "v.mapping_id,v.source_row,v.stream_code,v.is_active,v.is_representative,"
            "u.unit_symbol "
            "FROM characteristic_value v LEFT JOIN unit_dictionary u ON u.unit_id=v.unit_id "
            "WHERE v.stream_code=? AND v.is_active=1 "
            "AND v.is_representative=1 AND v.dictionary_id IN ("
            + _marks(dictionary_ids)
            + ") ORDER BY dictionary_id,characteristic_value_id",
            (stream_code, *dictionary_ids),
        )

    def caches(self, stream_code, dictionary_ids):
        if not dictionary_ids:
            return ()
        return self._rows(
            "SELECT dictionary_id,characteristic_value_id FROM stream_characteristic "
            "WHERE stream_code=? AND dictionary_id IN (" + _marks(dictionary_ids) + ")",
            (stream_code, *dictionary_ids),
        )

    def value_issues(self, value_ids):
        if not value_ids:
            return ()
        return self._rows(
            "SELECT characteristic_value_id,"
            "sum(CASE WHEN severity='ERROR' THEN 1 ELSE 0 END),"
            "sum(CASE WHEN severity='WARNING' THEN 1 ELSE 0 END),"
            "sum(CASE WHEN severity='INFO' THEN 1 ELSE 0 END) "
            "FROM data_quality_issue WHERE is_active=1 AND characteristic_value_id IN ("
            + _marks(value_ids)
            + ") GROUP BY characteristic_value_id",
            value_ids,
        )

    def active_value_issue_details(self, value_ids):
        if not value_ids:
            return ()
        return self._rows(
            "SELECT characteristic_value_id,issue_type,severity,review_status,is_active "
            "FROM data_quality_issue WHERE is_active=1 AND characteristic_value_id IN ("
            + _marks(value_ids)
            + ") ORDER BY characteristic_value_id,issue_id",
            value_ids,
        )

    def values_for_items(self, stream_code, dictionary_ids):
        if not dictionary_ids:
            return ()
        return self._rows(
            "SELECT v.characteristic_value_id,v.dictionary_id,v.value_number,v.value_integer,"
            "v.value_text,v.value_date,u.unit_symbol,v.source_type,v.is_active,"
            "v.is_representative,v.created_at,h.batch_code,v.source_row "
            "FROM characteristic_value v LEFT JOIN unit_dictionary u ON u.unit_id=v.unit_id "
            "LEFT JOIN import_history h ON h.import_id=v.import_id "
            "WHERE v.stream_code=? AND v.dictionary_id IN (" + _marks(dictionary_ids) + ") "
            "ORDER BY v.dictionary_id,v.created_at DESC,v.characteristic_value_id DESC",
            (stream_code, *dictionary_ids),
        )

    def provenance(self, value_ids):
        if not value_ids:
            return ()
        return self._rows(
            "SELECT v.characteristic_value_id,f.file_name,s.sheet_name,v.source_row,"
            "m.source_column_index,v.source_type "
            "FROM characteristic_value v "
            "LEFT JOIN import_history h ON h.import_id=v.import_id "
            "LEFT JOIN source_file f ON f.source_file_id=h.source_file_id "
            "LEFT JOIN import_sheet s ON s.import_sheet_id=v.import_sheet_id "
            "AND s.import_id=v.import_id "
            "LEFT JOIN import_column_mapping m ON m.mapping_id=v.mapping_id "
            "AND m.import_sheet_id=v.import_sheet_id "
            "WHERE v.characteristic_value_id IN (" + _marks(value_ids) + ")",
            value_ids,
        )

    def correction_history(self, stream_code, dictionary_ids):
        # parent 관계는 기존 generic history JSON 계약이다. 원시 연구값은 조회하지 않는다.
        import json

        keys = tuple(
            json.dumps(
                {"stream_code": stream_code, "dictionary_id": dictionary_id},
                sort_keys=True,
                separators=(",", ":"),
            )
            for dictionary_id in dictionary_ids
        )
        if not keys:
            return ()
        return self._rows(
            "SELECT old_value,new_value FROM record_history "
            "WHERE change_type='CORRECTION' AND record_key IN ("
            + _marks(keys)
            + ") ORDER BY history_id",
            keys,
        )
