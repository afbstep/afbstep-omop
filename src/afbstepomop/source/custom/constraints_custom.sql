
-- =====================================================
-- CONSTRAINTS FOR THE AFBSTEP CUSTOM EXTENSION TABLES
-- (NOT part of official OMOP CDM v5.4)
--
-- Kept separate from the vendored constraints.sql so the stock CDM files
-- stay diffable against future OHDSI releases.
--
-- This file is authoritative for the custom primary keys: the loader reads
-- them from here, not from primary_keys_custom.sql, which nothing parses.
--
-- The foreign keys to CONCEPT are what make file_concept_id,
-- source_event_field_concept_id and the study, study_attribute and
-- person_study concept columns count as concept-valued: concept columns are
-- derived from foreign keys, never from column names.
--
-- source_event_id carries no foreign key on purpose. It points into whichever
-- table source_event_field_concept_id names, so no single parent can be
-- declared. The stock CDM leaves measurement_event_id unconstrained for the
-- same reason.
-- =====================================================

--PRIMARY KEYS

ALTER TABLE source ADD CONSTRAINT xpk_source PRIMARY KEY (source_id);

ALTER TABLE device_specs ADD CONSTRAINT xpk_device_specs PRIMARY KEY (episode_id,device_exposure_id);

ALTER TABLE study ADD CONSTRAINT xpk_study PRIMARY KEY (study_id);

ALTER TABLE study_attribute ADD CONSTRAINT xpk_study_attribute PRIMARY KEY (study_id,attribute_type_concept_id,value_concept_id);

ALTER TABLE person_study ADD CONSTRAINT xpk_person_study PRIMARY KEY (person_id,study_id);

--FOREIGN KEYS

ALTER TABLE source ADD CONSTRAINT fpk_source_person_id FOREIGN KEY (person_id) REFERENCES person (person_id);

ALTER TABLE source ADD CONSTRAINT fpk_source_file_concept_id FOREIGN KEY (file_concept_id) REFERENCES concept (concept_id);

ALTER TABLE source ADD CONSTRAINT fpk_source_source_event_field_concept_id FOREIGN KEY (source_event_field_concept_id) REFERENCES concept (concept_id);

ALTER TABLE device_specs ADD CONSTRAINT fpk_device_specs_person_id FOREIGN KEY (person_id) REFERENCES person (person_id);

ALTER TABLE device_specs ADD CONSTRAINT fpk_device_specs_episode_id FOREIGN KEY (episode_id) REFERENCES episode (episode_id);


ALTER TABLE study ADD CONSTRAINT fpk_study_study_type_concept_id FOREIGN KEY (study_type_concept_id) REFERENCES concept (concept_id);

ALTER TABLE study ADD CONSTRAINT fpk_study_dataset_status_concept_id FOREIGN KEY (dataset_status_concept_id) REFERENCES concept (concept_id);

ALTER TABLE study ADD CONSTRAINT fpk_study_transfer_frequency_concept_id FOREIGN KEY (transfer_frequency_concept_id) REFERENCES concept (concept_id);

ALTER TABLE study_attribute ADD CONSTRAINT fpk_study_attribute_study_id FOREIGN KEY (study_id) REFERENCES study (study_id);

ALTER TABLE study_attribute ADD CONSTRAINT fpk_study_attribute_attribute_type_concept_id FOREIGN KEY (attribute_type_concept_id) REFERENCES concept (concept_id);

ALTER TABLE study_attribute ADD CONSTRAINT fpk_study_attribute_value_concept_id FOREIGN KEY (value_concept_id) REFERENCES concept (concept_id);

ALTER TABLE person_study ADD CONSTRAINT fpk_person_study_person_id FOREIGN KEY (person_id) REFERENCES person (person_id);

ALTER TABLE person_study ADD CONSTRAINT fpk_person_study_study_id FOREIGN KEY (study_id) REFERENCES study (study_id);

ALTER TABLE person_study ADD CONSTRAINT fpk_person_study_observation_period_id FOREIGN KEY (observation_period_id) REFERENCES observation_period (observation_period_id);

ALTER TABLE person_study ADD CONSTRAINT fpk_person_study_arm_type_concept_id FOREIGN KEY (arm_type_concept_id) REFERENCES concept (concept_id);
ALTER TABLE device_specs ADD CONSTRAINT fpk_device_specs_device_exposure_id FOREIGN KEY (device_exposure_id) REFERENCES device_exposure (device_exposure_id);
