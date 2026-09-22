SELECT
    o.person_id,
    v.visit_end_date AS discharge_date
FROM {schema}.observation AS o
JOIN {schema}.visit_occurrence AS v
  ON v.visit_occurrence_id = o.observation_event_id
WHERE o.observation_concept_id = {baseline_visit_concept}
  AND v.visit_end_date IS NOT NULL