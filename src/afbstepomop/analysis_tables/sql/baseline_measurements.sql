WITH idx AS ({index_sql}),
hits AS (
    SELECT
        i.person_id,
        c.concept_name AS variable,
        m.value_as_number,
        vc.concept_name AS value_as_concept_name,
        m.unit_concept_id,
        date_diff('day', i.anchor_date, m.measurement_date) AS day_offset
    FROM {schema}.measurement AS m
    JOIN idx AS i
      ON i.person_id = m.person_id
    JOIN {schema}.concept AS c
      ON c.concept_id = m.measurement_concept_id
    LEFT JOIN {schema}.concept AS vc
      ON vc.concept_id = m.value_as_concept_id
    WHERE 1=1
    {variable_filter}
    AND date_diff('day', i.anchor_date, m.measurement_date) BETWEEN $lo AND $hi
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY person_id, variable
            ORDER BY
                value_as_number IS NULL AND value_as_concept_name IS NULL,
                abs(day_offset),
                day_offset > 0
        ) AS rn,
        COUNT(*) OVER (PARTITION BY person_id, variable) AS n_in_window
    FROM hits
)
SELECT person_id, variable, value_as_number, value_as_concept_name,
       unit_concept_id, day_offset, n_in_window
FROM ranked
WHERE rn = 1