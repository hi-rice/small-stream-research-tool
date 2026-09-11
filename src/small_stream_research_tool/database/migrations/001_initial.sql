-- V1 initial schema: DATABASE_DESIGN.md. Runner owns transactions and version records.
-- Dates/JSON, provenance and business decisions remain Service responsibilities.

CREATE TABLE schema_version (
    schema_version_id INTEGER PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    description TEXT NULL,
    migration_name TEXT NULL,
    app_version TEXT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE app_user (
    user_id INTEGER PRIMARY KEY,
    login_id TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    department TEXT NULL,
    role TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT NULL,
    CHECK (typeof(login_id) = 'text' AND length(login_id) BETWEEN 4 AND 50
        AND login_id NOT GLOB '*[^a-z0-9._-]*' AND instr(login_id, char(0)) = 0)
);

CREATE TABLE data_category (
    category_id INTEGER PRIMARY KEY,
    category_key TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    parent_category_id INTEGER NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_category_id) REFERENCES data_category(category_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION
);

CREATE TABLE dictionary_version (
    version_id INTEGER PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    description TEXT NULL,
    is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0,1)),
    created_at TEXT NOT NULL
);

CREATE TABLE unit_dictionary (
    unit_id INTEGER PRIMARY KEY,
    unit_name TEXT NOT NULL,
    unit_symbol TEXT NOT NULL UNIQUE,
    dimension TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE unit_conversion (
    conversion_id INTEGER PRIMARY KEY,
    from_unit_id INTEGER NOT NULL,
    to_unit_id INTEGER NOT NULL,
    factor REAL NOT NULL,
    offset REAL NOT NULL DEFAULT 0,
    formula_type TEXT NOT NULL DEFAULT 'LINEAR',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (from_unit_id) REFERENCES unit_dictionary(unit_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (to_unit_id) REFERENCES unit_dictionary(unit_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    UNIQUE (from_unit_id, to_unit_id, formula_type)
);

CREATE TABLE data_dictionary (
    dictionary_id INTEGER PRIMARY KEY,
    standard_name TEXT NOT NULL,
    internal_name TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL,
    data_type TEXT NOT NULL,
    unit_id INTEGER NULL,
    description TEXT NULL,
    storage_type TEXT NOT NULL DEFAULT 'FLEX',
    analyzable INTEGER NOT NULL DEFAULT 1 CHECK (analyzable IN (0,1)),
    required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0,1)),
    nullable INTEGER NOT NULL DEFAULT 1 CHECK (nullable IN (0,1)),
    created_version_id INTEGER NOT NULL,
    deprecated_version_id INTEGER NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES data_category(category_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (unit_id) REFERENCES unit_dictionary(unit_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (created_version_id) REFERENCES dictionary_version(version_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (deprecated_version_id) REFERENCES dictionary_version(version_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    CHECK (data_type IN ('REAL','INTEGER','TEXT','DATE','DATETIME')),
    CHECK (storage_type IN ('CORE','FLEX'))
);

CREATE TABLE column_alias (
    alias_id INTEGER PRIMARY KEY,
    dictionary_id INTEGER NOT NULL,
    alias_name TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source_scope TEXT NOT NULL DEFAULT 'GLOBAL',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (dictionary_id) REFERENCES data_dictionary(dictionary_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    UNIQUE (normalized_alias, source_scope)
);

CREATE TABLE source_file (
    source_file_id INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    original_path TEXT NOT NULL,
    file_extension TEXT NULL,
    file_size INTEGER NULL,
    file_hash TEXT NULL,
    file_modified_at TEXT NULL,
    source_description TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    registered_at TEXT NOT NULL
);

CREATE TABLE import_history (
    import_id INTEGER PRIMARY KEY,
    source_file_id INTEGER NOT NULL,
    created_by_user_id INTEGER NULL,
    batch_code TEXT NOT NULL UNIQUE,
    import_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NULL,
    total_rows INTEGER NULL,
    accepted_rows INTEGER NULL,
    warning_rows INTEGER NULL,
    rejected_rows INTEGER NULL,
    dictionary_version_id INTEGER NULL,
    schema_version_id INTEGER NULL,
    settings_json TEXT NULL,
    error_code TEXT NULL,
    error_message TEXT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_file_id) REFERENCES source_file(source_file_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (created_by_user_id) REFERENCES app_user(user_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (dictionary_version_id) REFERENCES dictionary_version(version_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (schema_version_id) REFERENCES schema_version(schema_version_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    CHECK (status IN ('PENDING','RUNNING','SUCCESS','FAILED','ROLLED_BACK','CANCELLED'))
);

CREATE TABLE import_sheet (
    import_sheet_id INTEGER PRIMARY KEY,
    import_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL,
    sheet_index INTEGER NULL,
    header_start_row INTEGER NULL,
    header_end_row INTEGER NULL,
    data_start_row INTEGER NULL,
    total_rows INTEGER NULL,
    accepted_rows INTEGER NULL,
    warning_rows INTEGER NULL,
    rejected_rows INTEGER NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (import_id) REFERENCES import_history(import_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    UNIQUE (import_id, sheet_name),
    CHECK (status IN ('RUNNING','SUCCESS','FAILED'))
);

CREATE TABLE import_column_mapping (
    mapping_id INTEGER PRIMARY KEY,
    import_sheet_id INTEGER NOT NULL,
    source_column_index INTEGER NOT NULL,
    source_header TEXT NULL,
    normalized_header TEXT NULL,
    dictionary_id INTEGER NULL,
    mapping_status TEXT NOT NULL,
    mapping_method TEXT NOT NULL,
    source_unit TEXT NULL,
    target_unit_id INTEGER NULL,
    transform_rule TEXT NULL,
    user_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (user_confirmed IN (0,1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (import_sheet_id) REFERENCES import_sheet(import_sheet_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (dictionary_id) REFERENCES data_dictionary(dictionary_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (target_unit_id) REFERENCES unit_dictionary(unit_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    UNIQUE (import_sheet_id, source_column_index)
);

CREATE TABLE small_stream (
    stream_code TEXT PRIMARY KEY NOT NULL,
    province_code TEXT NOT NULL,
    city_county_code TEXT NOT NULL,
    town_code TEXT NOT NULL,
    stream_serial_no TEXT NOT NULL,
    stream_name TEXT NOT NULL,
    province_name TEXT NULL,
    city_county_name TEXT NULL,
    town_name TEXT NULL,
    river_system TEXT NULL,
    source_address TEXT NULL,
    source_latitude REAL NULL,
    source_longitude REAL NULL,
    end_address TEXT NULL,
    end_latitude REAL NULL,
    end_longitude REAL NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (typeof(stream_code) = 'text' AND length(stream_code) = 11
        AND stream_code NOT GLOB '*[^0-9]*' AND instr(stream_code, char(0)) = 0),
    CHECK (length(province_code) = 2),
    CHECK (length(city_county_code) = 3),
    CHECK (length(town_code) = 3),
    CHECK (length(stream_serial_no) = 3),
    CHECK (source_latitude IS NULL OR source_latitude BETWEEN -90 AND 90),
    CHECK (source_longitude IS NULL OR source_longitude BETWEEN -180 AND 180),
    CHECK (end_latitude IS NULL OR end_latitude BETWEEN -90 AND 90),
    CHECK (end_longitude IS NULL OR end_longitude BETWEEN -180 AND 180)
);

CREATE TABLE stream_relation (
    relation_id INTEGER PRIMARY KEY,
    stream_code TEXT NOT NULL,
    related_stream_code TEXT NULL,
    relation_type TEXT NOT NULL,
    relation_order INTEGER NULL,
    related_stream_name_raw TEXT NULL,
    source_import_id INTEGER NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (stream_code) REFERENCES small_stream(stream_code)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (related_stream_code) REFERENCES small_stream(stream_code)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (source_import_id) REFERENCES import_history(import_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION
);

CREATE TABLE characteristic_value (
    characteristic_value_id INTEGER PRIMARY KEY,
    stream_code TEXT NOT NULL,
    dictionary_id INTEGER NOT NULL,
    value_number REAL NULL,
    value_integer INTEGER NULL,
    value_text TEXT NULL,
    value_date TEXT NULL,
    unit_id INTEGER NULL,
    original_value TEXT NULL,
    original_unit TEXT NULL,
    import_id INTEGER NULL,
    import_sheet_id INTEGER NULL,
    source_row INTEGER NULL,
    mapping_id INTEGER NULL,
    source_type TEXT NOT NULL DEFAULT 'IMPORT',
    source_reference TEXT NULL,
    reference_year INTEGER NULL,
    is_representative INTEGER NOT NULL DEFAULT 0 CHECK (is_representative IN (0,1)),
    quality_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (stream_code) REFERENCES small_stream(stream_code)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (dictionary_id) REFERENCES data_dictionary(dictionary_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (unit_id) REFERENCES unit_dictionary(unit_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (import_id) REFERENCES import_history(import_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (import_sheet_id) REFERENCES import_sheet(import_sheet_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (mapping_id) REFERENCES import_column_mapping(mapping_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    CHECK ((value_number IS NOT NULL) + (value_integer IS NOT NULL)
        + (value_text IS NOT NULL) + (value_date IS NOT NULL) = 1)
);

CREATE TABLE stream_characteristic (
    stream_code TEXT NOT NULL,
    dictionary_id INTEGER NOT NULL,
    characteristic_value_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (stream_code) REFERENCES small_stream(stream_code)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (dictionary_id) REFERENCES data_dictionary(dictionary_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (characteristic_value_id) REFERENCES characteristic_value(characteristic_value_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    PRIMARY KEY (stream_code, dictionary_id)
);

CREATE TABLE quality_rule (
    rule_id INTEGER PRIMARY KEY,
    rule_code TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL,
    target_type TEXT NOT NULL,
    dictionary_id INTEGER NULL,
    rule_type TEXT NOT NULL,
    default_severity TEXT NOT NULL,
    parameters_json TEXT NULL,
    description TEXT NULL,
    rule_version TEXT NOT NULL DEFAULT '1.0',
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (dictionary_id) REFERENCES data_dictionary(dictionary_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    CHECK (default_severity IN ('ERROR','WARNING','INFO'))
);

CREATE TABLE data_quality_issue (
    issue_id INTEGER PRIMARY KEY,
    characteristic_value_id INTEGER NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    rule_id INTEGER NULL,
    rule_version_snapshot TEXT NULL,
    rule_parameters_snapshot_json TEXT NULL,
    import_id INTEGER NULL,
    import_sheet_id INTEGER NULL,
    stream_code TEXT NULL,
    dictionary_id INTEGER NULL,
    source_row INTEGER NULL,
    source_column INTEGER NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    original_value TEXT NULL,
    compare_value TEXT NULL,
    message TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
    review_result TEXT NULL,
    review_note TEXT NULL,
    reviewed_at TEXT NULL,
    reviewed_by_user_id INTEGER NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (characteristic_value_id) REFERENCES characteristic_value(characteristic_value_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (rule_id) REFERENCES quality_rule(rule_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (import_id) REFERENCES import_history(import_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (import_sheet_id) REFERENCES import_sheet(import_sheet_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (stream_code) REFERENCES small_stream(stream_code)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (dictionary_id) REFERENCES data_dictionary(dictionary_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (reviewed_by_user_id) REFERENCES app_user(user_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    CHECK (severity IN ('ERROR','WARNING','INFO')),
    CHECK (review_status IN ('UNREVIEWED','IN_REVIEW','CONFIRMED','CORRECTED','DEFERRED'))
);

CREATE TABLE record_history (
    history_id INTEGER PRIMARY KEY,
    issue_id INTEGER NULL,
    import_id INTEGER NULL,
    table_name TEXT NOT NULL,
    record_key TEXT NOT NULL,
    column_name TEXT NULL,
    old_value TEXT NULL,
    new_value TEXT NULL,
    change_type TEXT NOT NULL,
    reason TEXT NULL,
    changed_by TEXT NULL,
    actor_user_id INTEGER NULL,
    changed_at TEXT NOT NULL,
    FOREIGN KEY (issue_id) REFERENCES data_quality_issue(issue_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (import_id) REFERENCES import_history(import_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION,
    FOREIGN KEY (actor_user_id) REFERENCES app_user(user_id)
        ON DELETE RESTRICT ON UPDATE NO ACTION
);

-- Inactive selected values remain historical rows.
CREATE UNIQUE INDEX ux_characteristic_value_active_representative
ON characteristic_value(stream_code, dictionary_id)
WHERE is_representative = 1 AND is_active = 1;

CREATE UNIQUE INDEX ux_dictionary_version_current
ON dictionary_version(is_current) WHERE is_current = 1;

-- Child FK indexes support RESTRICT checks without full child-table scans.
CREATE INDEX ix_data_category_parent_category_id ON data_category(parent_category_id);
CREATE INDEX ix_unit_conversion_to_unit_id ON unit_conversion(to_unit_id);
CREATE INDEX ix_data_dictionary_category_id ON data_dictionary(category_id);
CREATE INDEX ix_data_dictionary_unit_id ON data_dictionary(unit_id);
CREATE INDEX ix_data_dictionary_created_version_id ON data_dictionary(created_version_id);
CREATE INDEX ix_data_dictionary_deprecated_version_id ON data_dictionary(deprecated_version_id);
CREATE INDEX ix_column_alias_dictionary_id ON column_alias(dictionary_id);
CREATE INDEX ix_import_history_source_file_id ON import_history(source_file_id);
CREATE INDEX ix_import_history_created_by_user_id ON import_history(created_by_user_id);
CREATE INDEX ix_import_history_dictionary_version_id ON import_history(dictionary_version_id);
CREATE INDEX ix_import_history_schema_version_id ON import_history(schema_version_id);
CREATE INDEX ix_import_column_mapping_dictionary_id ON import_column_mapping(dictionary_id);
CREATE INDEX ix_import_column_mapping_target_unit_id ON import_column_mapping(target_unit_id);
CREATE INDEX ix_stream_relation_stream_code ON stream_relation(stream_code);
CREATE INDEX ix_stream_relation_related_stream_code ON stream_relation(related_stream_code);
CREATE INDEX ix_stream_relation_source_import_id ON stream_relation(source_import_id);
CREATE INDEX ix_characteristic_value_stream_code ON characteristic_value(stream_code, dictionary_id);
CREATE INDEX ix_characteristic_value_dictionary_id ON characteristic_value(dictionary_id);
CREATE INDEX ix_characteristic_value_unit_id ON characteristic_value(unit_id);
CREATE INDEX ix_characteristic_value_import_id ON characteristic_value(import_id);
CREATE INDEX ix_characteristic_value_import_sheet_id ON characteristic_value(import_sheet_id);
CREATE INDEX ix_characteristic_value_mapping_id ON characteristic_value(mapping_id);
CREATE INDEX ix_stream_characteristic_dictionary_id ON stream_characteristic(dictionary_id);
CREATE INDEX ix_stream_characteristic_characteristic_value_id ON stream_characteristic(characteristic_value_id);
CREATE INDEX ix_quality_rule_dictionary_id ON quality_rule(dictionary_id);
CREATE INDEX ix_data_quality_issue_characteristic_value_id ON data_quality_issue(characteristic_value_id, is_active, severity);
CREATE INDEX ix_data_quality_issue_rule_id ON data_quality_issue(rule_id);
CREATE INDEX ix_data_quality_issue_import_id ON data_quality_issue(import_id);
CREATE INDEX ix_data_quality_issue_import_sheet_id ON data_quality_issue(import_sheet_id);
CREATE INDEX ix_data_quality_issue_stream_code ON data_quality_issue(stream_code, dictionary_id);
CREATE INDEX ix_data_quality_issue_dictionary_id ON data_quality_issue(dictionary_id);
CREATE INDEX ix_data_quality_issue_reviewed_by_user_id ON data_quality_issue(reviewed_by_user_id);
CREATE INDEX ix_record_history_issue_id ON record_history(issue_id);
CREATE INDEX ix_record_history_import_id ON record_history(import_id);
CREATE INDEX ix_record_history_actor_user_id ON record_history(actor_user_id);
