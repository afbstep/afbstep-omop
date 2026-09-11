--duckdb Primary Key Constraints for the AFBSTEP custom extension tables
--
-- NOT PARSED. The loader reads the custom primary keys out of
-- constraints_custom.sql, which is authoritative. This file is kept in step
-- with it by hand so the DDL can still be applied as a set of files, and the
-- constraint names are deliberately identical so that applying both fails
-- loudly rather than declaring a key twice.
--
-- episode is not repeated here: the vendored structural/primary_keys.sql
-- already declares it. episode_event is, because the vendored file gives it
-- no key and AFBSTEP needs one.

ALTER TABLE episode_event ADD CONSTRAINT xpk_episode_event PRIMARY KEY (episode_id,event_id,episode_event_field_concept_id);

ALTER TABLE source ADD CONSTRAINT xpk_source PRIMARY KEY (source_id);

ALTER TABLE device_specs ADD CONSTRAINT xpk_device_specs PRIMARY KEY (episode_id,device_exposure_id);

ALTER TABLE study ADD CONSTRAINT xpk_study PRIMARY KEY (study_id);

ALTER TABLE study_attribute ADD CONSTRAINT xpk_study_attribute PRIMARY KEY (study_id,attribute_type_concept_id,value_concept_id);

ALTER TABLE person_study ADD CONSTRAINT xpk_person_study PRIMARY KEY (person_id,study_id);
