"""AFBSTEP storage conventions"""

SENTINEL_UNKNOWN_DATE = "1900-01-01"   # comorbidity Case 3: date unknown
SENTINEL_ONGOING_DATE = "2099-12-31"   # drug_exposure_end_date: still ongoing

NEGATIVE_CONCEPT_ID = 4189457          # explicit negative finding (missingness Case 2)

MISSINGNESS_REASON_CONCEPTS = {
    45884199: "not_performed",         # missingness Case 3
    45880382: "not_interpretable",     # missingness Case 4
    2000013000: "unknown",             # missingness Case 5
}

BASELINE_VISIT_CONCEPT_ID = 2000013017        # marks a visit_occurrence row as baseline
BASELINE_VISIT_FIELD_CONCEPT_ID = 1147869     # visit_occurrence.visit_occurrence_id