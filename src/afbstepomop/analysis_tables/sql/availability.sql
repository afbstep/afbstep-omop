WITH idx AS ({index_sql}),
observed AS (
    SELECT DISTINCT i.study_id, c.concept_name AS variable
    FROM {schema}.condition_occurrence AS co
    JOIN idx AS i ON i.person_id = co.person_id
    JOIN {schema}.concept AS c ON c.concept_id = co.condition_concept_id

    UNION

    SELECT DISTINCT i.study_id, c.concept_name AS variable
    FROM {schema}.observation AS o
    JOIN idx AS i ON i.person_id = o.person_id
    JOIN {schema}.concept AS c ON c.concept_id = o.observation_concept_id
    WHERE o.value_as_concept_id = $negative_concept_id

    UNION

    SELECT DISTINCT i.study_id, c.concept_name AS variable
    FROM {schema}.measurement AS m
    JOIN idx AS i ON i.person_id = m.person_id
    JOIN {schema}.concept AS c ON c.concept_id = m.measurement_concept_id

    UNION

    SELECT DISTINCT i.study_id, c.concept_name AS variable
    FROM {schema}.drug_exposure AS d
    JOIN idx AS i ON i.person_id = d.person_id
    JOIN {schema}.concept AS c ON c.concept_id = d.drug_concept_id

    UNION

    SELECT DISTINCT i.study_id, c.concept_name AS variable
    FROM {schema}.device_exposure AS de
    JOIN idx AS i ON i.person_id = de.person_id
    JOIN {schema}.concept AS c ON c.concept_id = de.device_concept_id
)
SELECT study_id, variable, 1 AS collected
FROM observed