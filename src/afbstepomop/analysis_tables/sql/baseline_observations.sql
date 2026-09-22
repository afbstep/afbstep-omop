WITH idx AS ({index_sql}),
hits AS (
    SELECT
        i.person_id,
        c.concept_name AS variable,
        vc.concept_name AS value_as_concept_name,
        i.anchor_date,
        date_diff('day', i.anchor_date, o.observation_date) AS day_offset
    FROM {schema}.observation AS o
    JOIN idx AS i
      ON i.person_id = o.person_id
    JOIN {schema}.concept AS c
      ON c.concept_id = o.observation_concept_id
    JOIN {schema}.concept AS vc
      ON vc.concept_id = o.value_as_concept_id
    WHERE 1=1
    {variable_filter}
    AND o.observation_concept_id != $baseline_visit_concept
    AND o.value_as_concept_id != $negative_concept_id
    AND date_diff('day', i.anchor_date, o.observation_date) BETWEEN $lo AND $hi
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY person_id, variable
            ORDER BY abs(day_offset), day_offset > 0
        ) AS rn,
        COUNT(*) OVER (PARTITION BY person_id, variable) AS n_in_window
    FROM hits
)
SELECT person_id, variable, value_as_concept_name, day_offset, n_in_window
FROM ranked
WHERE rn = 1