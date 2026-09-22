WITH idx AS ({index_sql}),
hits AS (
    SELECT
        i.person_id,
        c.concept_name AS variable,
        de.device_exposure_start_date AS start_date,
        de.device_exposure_end_date AS end_date,
        i.anchor_date
    FROM {schema}.device_exposure AS de
    JOIN idx AS i
      ON i.person_id = de.person_id
    JOIN {schema}.concept AS c
      ON c.concept_id = de.device_concept_id
    WHERE 1=1
    {variable_filter}
    AND de.device_exposure_start_date <= i.anchor_date
    AND (
          de.device_exposure_end_date IS NULL
          OR de.device_exposure_end_date >= i.anchor_date
        )
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY person_id, variable
            ORDER BY start_date DESC
        ) AS rn
    FROM hits
)
SELECT
    person_id,
    variable,
    1 AS value,
    'observed' AS reason,
    (end_date IS NULL OR end_date = CAST($sentinel_ongoing AS DATE)) AS ongoing,
    date_diff('day', anchor_date, start_date) AS start_day
FROM ranked
WHERE rn = 1