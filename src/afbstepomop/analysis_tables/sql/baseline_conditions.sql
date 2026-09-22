-- One row per (person, comorbidity) actually present in the data, with
-- Case 1/2/3 classification and the concept's own name as the column label.

WITH idx AS ({index_sql}),
hits AS (
    SELECT
        i.person_id,
        c.concept_name AS variable,
        co.condition_start_date AS event_date,
        i.anchor_date
    FROM {schema}.condition_occurrence AS co
    JOIN idx AS i
      ON i.person_id = co.person_id
    JOIN {schema}.concept AS c
      ON c.concept_id = co.condition_concept_id
    WHERE 1=1
    {variable_filter}
)
SELECT
    person_id,
    variable,
    CASE
        WHEN event_date = CAST($unknown_date AS DATE) THEN 'historical_undated'
        WHEN event_date < anchor_date                  THEN 'historical_dated'
        WHEN event_date = anchor_date                   THEN 'current'
    END AS timing,
    CASE
        WHEN event_date = CAST($unknown_date AS DATE) THEN NULL
        ELSE date_diff('day', anchor_date, event_date)
    END AS onset_days
FROM hits
WHERE timing IS NOT NULL

UNION ALL

SELECT
    i.person_id,
    c.concept_name AS variable,
    'negative' AS timing,
    NULL AS onset_days
FROM {schema}.observation AS o
JOIN idx AS i
  ON i.person_id = o.person_id
JOIN {schema}.concept AS c
  ON c.concept_id = o.observation_concept_id
WHERE o.value_as_concept_id = $negative_concept_id