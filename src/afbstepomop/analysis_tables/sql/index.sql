-- One row per person with a study enrolment: study_id and the anchor
-- date used by every downstream analysis table.
--
-- Anchor = the baseline visit (marked by concept {baseline_visit_concept}),
-- if one exists, otherwise the enrolment date.

WITH baseline_visit AS (
    SELECT o.person_id, v.visit_start_date AS baseline_date
    FROM {schema}.observation AS o
    JOIN {schema}.visit_occurrence AS v
      ON v.visit_occurrence_id = o.observation_event_id
    WHERE o.observation_concept_id = {baseline_visit_concept}
)
SELECT
    ps.person_id,
    ps.study_id,
    ps.enrollment_date,
    COALESCE(bv.baseline_date, ps.enrollment_date) AS anchor_date
FROM {schema}.person_study AS ps
LEFT JOIN baseline_visit AS bv
       ON bv.person_id = ps.person_id
{study_filter}