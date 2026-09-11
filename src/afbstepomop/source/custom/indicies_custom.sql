-- speed up lookups by person across the custom tables
CREATE INDEX idx_source_person_id ON source (person_id);
CREATE INDEX idx_device_specs_person_id ON device_specs (person_id);
CREATE INDEX idx_person_study_person_id ON person_study (person_id);

-- speed up joins back to episode (the most common lookup pattern)
CREATE INDEX idx_source_episode_id ON source (episode_id);
CREATE INDEX idx_device_specs_episode_id ON device_specs (episode_id);
CREATE INDEX idx_episode_event_episode_id ON episode_event (episode_id);

-- speed up study lookups
CREATE INDEX idx_person_study_study_id ON person_study (study_id);