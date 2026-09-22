WITH idx AS ({index_sql}),
hits AS (
    SELECT
        i.person_id,
        c.concept_name AS variable,
        po.procedure_date AS event_date,
        i.anchor_date
    FROM {schema}.procedure_occurrence AS po
    JOIN idx AS i
      ON i.person_id = po.person_id
    JOIN {schema}.concept AS c
      ON c.concept_id = po.procedure_concept_id
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