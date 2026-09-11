-- =====================================================
-- CUSTOM EXTENSION TABLES (NOT part of official OMOP CDM v5.4)
-- Purpose: model continuous/intermittent AF-burden monitoring using
-- the official OMOP EPISODE table as the anchor, with custom
-- companion tables (source, device_specs) linking external raw data
-- files and device metadata to a person's episodes without storing
-- large binary content in OMOP itself. Study, study_attribute, and
-- person_study additionally record which source study each person's
-- data originates from, including study-level attributes that allow
-- more than one value per study (e.g. country of data collection,
-- data provision level) and each person's study arm assignment.
-- =====================================================
CREATE TABLE source (
    source_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    link_to_file UUID NULL,
    file_concept_id INTEGER NULL,
    source_event_id INTEGER NULL,
    source_event_field_concept_id INTEGER NULL
);
CREATE TABLE device_specs (
    episode_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    device_exposure_id INTEGER NOT NULL,
    device_algorithm VARCHAR NULL,
    device_algorithm_v VARCHAR NULL,
    device_sn VARCHAR NULL,
    device_v VARCHAR NULL
);

CREATE TABLE study (
    study_id INTEGER NOT NULL,
    study_name VARCHAR NOT NULL,
    nct_number VARCHAR(11) NULL,
    contributor VARCHAR NULL,
    extended_affiliate BOOLEAN NULL,
    extended_affiliate_detail VARCHAR NULL,
    study_type_concept_id INTEGER NULL,
    n_data_subjects INTEGER NULL,
    study_start_date DATE NULL,
    study_end_date DATE NULL,
    median_follow_up_months NUMERIC NULL,
    dataset_status_concept_id INTEGER NULL,
    transfer_frequency_concept_id INTEGER NULL
);

CREATE TABLE study_attribute (
    study_id INTEGER NOT NULL,
    attribute_type_concept_id INTEGER NOT NULL,
    value_concept_id INTEGER NOT NULL
);

CREATE TABLE person_study (
    person_id INTEGER NOT NULL,
    study_id INTEGER NOT NULL,
    observation_period_id INTEGER NULL,
    enrollment_date DATE NULL,
    arm_source_value VARCHAR(50) NULL,
    arm_type_concept_id INTEGER NULL
);
