# Reference source dataset (`reference_*.csv`)

A worked **raw provider export** for 26 reference persons (`P-001`–`P-026`),
built so that every example in `mapping_codebook.md` and
`afbstepomop_schema_description.md` is contained in it as a subset.

**This is not OMOP.** It is the "typical starting point" a partner site
actually holds, before any mapping. No column holds a concept id; labels are
in-house shorthand, deliberately not the CDM's wording, so that mapping them
is a real exercise rather than a rename.

`../reference_mapping_pipeline.ipynb` maps these four files into
`../reference_mapped_dataset/`, and asserts 26 checks against the codebook's
published expected values for `P-001`–`P-004` before running the validator.

The older `patients.csv` / `episodes_events.csv` / `monitoring_data.csv`
(persons `PT001`–`PT020`) are a separate, unchanged example and are still what
`example_mapping_pipeline.ipynb` reads. Nothing here feeds `mapped_dataset/`.

## The four files

| File | Grain | Holds |
|---|---|---|
| `reference_baseline.csv` | one row per person, wide | everything known at or before enrolment |
| `reference_followup.csv` | one row per dated record, long | everything after enrolment |
| `reference_device_registry.csv` | one row per device | device identity: model, serial number, firmware, algorithm |
| `reference_study_information.csv` | one row per fact, long | study metadata, multi-select attributes, and who was enrolled in which arm |

The baseline/follow-up split follows the codebook's own two source tables. The
boundary is the person's `incl_date`: a record dated at or before it is
baseline, after it is follow-up. Persons with no enrolment date (the standing
wearable feed: `P-004`, `P-023`, `P-024`) have no boundary — their devices sit
in baseline, everything dated goes to follow-up.

Joins: `pat_id` throughout; `dev_ref` / `dev1_ref`… → `reference_device_registry.dev_id`;
`parent_rec_id` → a `window` row's `rec_id` in the same follow-up file;
`reference_study_information.pat_id` on `enrollment` rows → `pat_id`.

### `reference_baseline.csv` (120 columns)

Column groups, in order:

1. **Person** — `pat_id, site, sex, yob, race, ethnicity, incl_date,
   visit_setting, last_contact_date, vital_status, height_cm, weight_kg,
   smoking, af_type, cha2ds2vasc`
2. **Comorbidities** — `<c>_yn`, `<c>_onset`, `<c>_datecert` for `htn`, `dm`,
   `hf`, `stroke`, `ckd`, plus `other_dx_icd10`
3. **Baseline labs** — `krea_mgdl`, `hb_gl`, `lvef_pct`, `ehra_class`, each
   with `_date` and `_flag`, plus `lab_doc`, `ehra_doc`
4. **Vitals, extra labs and scores** (added so the minimal data set is fully
   covered) — `sbp_mmhg`, `dbp_mmhg`, `hr_bpm` sharing one `vitals_date` /
   `vitals_flag`, because they are one measurement act at the baseline visit;
   `egfr_ml_min`, `ntprobnp_pg_ml`, `ldl_mmol_l` each with `_date` and
   `_flag`; `cha2ds2va` (the sex-agnostic variant, 0–8, **distinct from**
   `cha2ds2vasc`, 0–9); `ecg_rhythm` with `ecg_date` / `ecg_flag`;
   `af_first_dx_date`; `af_device_detected`
5. **Devices in use at baseline** — `dev1_ref` … `dev3_ref`
6. **Medication at baseline** — `med1_*`, `med2_*` (`name`, `class`, `start`,
   `stop`, `ongoing`, `doc`)
7. **Pre-enrolment / baseline-visit history** — `hist1_*` … `hist4_*`
   (`case_no`, `kind`, `start`, `end`, `code_sys`, `code`, `code_txt`, `dept`,
   `energy_src`, `dev_ref`). `kind` is `admission`, `procedure` or
   `complication`.

Repeated groups fill from slot 1 upward with no holes. Study and arm are
deliberately **not** here — a site's baseline CRF does not carry them; they
live in `reference_study_information.csv`.

### `reference_followup.csv` (26 columns)

`rec_kind` says what the row is; the columns that do not apply are empty.

| `rec_kind` | Populated columns |
|---|---|
| `lab` | `event_name`, `instance`, `ts_start`, `variable`, `value`, `unit`, `flag`, `file_path`. `variable` covers `krea`, `hb`, `lvef`, `ehra`, `afeqt` and the repeat vitals/labs `sbp`, `dbp`, `hr`, `egfr`, `ntprobnp`, `ldl` |
| `med` | `instance`, `ts_start`, `ts_end`, `variable` (name), `value` (class), `ongoing` |
| `admission` | `rec_id`, `ts_start`, `ts_end`, `code_sys`, `code`, `code_txt`, `dept`, `discharge_to`, `ascertain_src` |
| `procedure` | `rec_id`, `ts_start`, `code_sys`, `code`, `code_txt`, `dept`, `energy_src`, `dev_ref` |
| `device` | `ts_start`, `ts_end`, `dev_ref`, `variable` (kind), `value` (model), `algo_version` |
| `window` | `rec_id`, `ts_start`, `ts_end`, `dev_ref`, `variable`, `value`, `unit`, `flag`, `algo_version`. `variable` covers `af_burden`, `n_ecg_total`, `n_ecg_af`, `adherence_pct`, `pct_ap`, `pct_vp`, `pvc_burden` |
| `episode` | `rec_id`, `ts_start`, `ts_end`, `parent_rec_id`, `dev_ref`, `rhythm`, `hr_max`, `algo_version` |
| `daily` | `rec_id`, `ts_start`, `ts_end`, `dev_ref`, `variable`, `value`, `unit` |
| `file` | `rec_id`, `ts_start`, `ts_end`, `dev_ref`, `file_path`, `file_kind` |
| `death` | `event_name` = `eos`, `ts_start`, `variable` = `death_cause`, `value`, `ascertain_src` |

### `reference_study_information.csv` (6 columns)

`study_id, entry_kind, pat_id, entry_key, entry_value, entry_note`

| `entry_kind` | Meaning |
|---|---|
| `meta` | one study attribute per row; `entry_key` names it (`study_name`, `nct`, `contributor`, `ext_affiliate`, `ext_affiliate_name`, `study_kind`, `n_subjects`, `data_from`, `data_to`, `median_fu_months`, `ds_status`, `transfer_mode`) |
| `country` | `entry_value` = ISO-2 country of data collection |
| `provision` | `entry_value` = data provision level |
| `arm` | `entry_value` = the arm's in-house name, `entry_note` = its role |
| `enrollment` | `pat_id` = the person, `entry_value` = their arm, `entry_note` = enrolment date |

## Coding conventions

| Field | Values |
|---|---|
| `sex` | `M`, `F`, `D` |
| `visit_setting` | `amb` (outpatient), `stat` (inpatient) |
| `code_sys` | `ICD10` (diagnoses), `OPS` (German procedure codes) |
| `energy_src` | `RF`, `Cryo`, `PFA`, `Laser`, `n.s.`, `PVI-other` |
| `dev_kind` | `PM`, `CRT-P`, `CRT-D`, `S-ICD`, `ILR`, `HOLTER`, `PATCH`, `PPG-WATCH`, `TELE-ECG`, `REST-ECG`, `CIED-unspec`, `CIED-monitor`, `ABL-GEN` |
| `ecg_rhythm` | `SR`, `AF`, `AFL`, `paced` — the 12-lead ECG rhythm at baseline. Only `AF` and `AFL` have a concept this project can vouch for; `SR` and `paced` map to `0` with the source value preserved, pending an Athena lookup |
| `ascertain_src` | `EHR`, `registry`, `patient-report`, `device-tx` |
| `rhythm` | `AF`, `AFL`, `AT` — what the recording shows. The AF *pattern* (paroxysmal … permanent) is a patient-level state and lives in `af_type` on the baseline row, never on an episode |
| `file_kind` | `report-pdf`, `raw-cied`, `waveform`, `interrog-pdf`, `audio`, `scan-pdf` |
| `med` class | `VKA`, `DOAC`, `betablocker`, `antiarrhythmic`, `diuretic`, `RAS-I`, `SGLT2-I`, `plt-inhibitor`, `digitalis`, `CCB`, `MRA`, `statin`, `ARNI` |
| provision level | `META`, `TAB`, `TAB+SIG`, `TAB+IMG` |
| arm role | `treatment`, `control`, `placebo`, `sham`, `no intervention` |

### Missingness

Flag columns (`krea_flag`, `hb_flag`, `lvef_flag`, `ehra_flag` in baseline;
`flag` in follow-up) carry the source's own reason. Empty flag = the value is
present; a value and a flag are never both populated.

| Source state | Codebook case |
|---|---|
| no row / blank `*_yn` / column absent for the whole site | Case 1 — never assessed |
| `*_yn = 0` | Case 2 — explicitly negative |
| flag `not done` | Case 3 — attempted, not performed |
| flag `uninterpretable` | Case 4 — attempted, not interpretable |
| flag `NA` | Case 5 — missing, cause unknown |

### Comorbidity dating

| `<c>_datecert` | `<c>_onset` | Codebook case |
|---|---|---|
| `baseline` | empty | Case 1 — established at the baseline visit |
| `exact` | the true date | Case 2 — historical, date known |
| `unknown` | empty | Case 3 — historical, date unknown |

The `1900-01-01` sentinel is a **mapping** decision and deliberately does not
appear in this raw data — the source states "date unknown", and the sentinel
is introduced when building `condition_occurrence`.

### Devices and firmware

`algo_version` appears in the registry **and** on follow-up rows, and that is
intentional. The registry holds the version the device shipped with; a
follow-up row holds the version reported *for that record*. P-001's wearable
updates from `2.3` to `2.4` between its second and third episode — exactly the
case that makes `device_specs` episode-keyed rather than device-keyed.

Ablation energy sources (`dev_kind = ABL-GEN`) carry `in_use_from` only;
`in_use_to` stays empty, per the codebook.

## What the dataset covers

Exhaustive at study level: all 6 study kinds, both dataset statuses, both
transfer modes, all 4 provision levels, all 5 arm roles, 8 countries, NCT
present/absent, affiliate true/false, open/closed collection periods.

Full sweeps: 13 device kinds, 6 energy sources, 3 episode rhythms, 4 AF
patterns, 10 procedure codes, 6 file kinds,
9 follow-up record kinds, 3 sexes, both visit settings, 3 dating cases, 3
missingness flags, 13 drug classes.

Edge cases:

| Case | Persons |
|---|---|
| not enrolled in any study / no observation period | P-004, P-023, P-024 |
| baseline device but no observation period | P-004, P-023, P-024 |
| enrolled but no cardiac monitoring | P-002, P-003, P-005, P-019–P-022 |
| unenrolled *with* monitoring | P-023, P-024 |
| disaggregated episodes only, no window | P-006 |
| window with linked episodes | P-007, P-017, P-018, P-024 |
| episodes deliberately *not* linked to a window | P-001, P-006 |
| device replacement mid-follow-up | P-008 |
| firmware change mid-series | P-001, P-016 |
| pre-enrolment history | P-001, P-013 |
| every comorbidity explicitly negative | P-011 |
| dating Case 2 and Case 3 in one person | P-012 |
| site-clustered Case 1 (no labs at all) | P-019–P-022 |
| study with zero enrolled persons | S6 |

## Realism notes

- **Missingness rates**: 91.9% of assessment slots hold a value; `not done`
  2.9%, `uninterpretable` 2.9%, `NA` 2.2%. The codebook's teaching excerpt puts
  4 of 9 cells in a missingness case; that density is not realistic and is
  confined to P-001–P-003, which reproduce the codebook verbatim.
- **Case 1 is site-clustered, not random.** S5 (claims) has no labs, devices or
  monitoring at all; S4 (registry) collects no ethnicity and no haemoglobin.
  That is how missingness actually arrives.
- **Comorbidity prevalence** among persons actually asked: hypertension 75%,
  diabetes 27%, heart failure 35%, stroke/TIA 20%, CKD 25%.
- **Mortality is 4/26 (15%)**, chosen over exhaustive death-cause coverage.
  Covering all eight cause options would need eight deaths — roughly triple a
  real 1–3 year AF cohort. Heart failure, atrial fibrillation,
  non-cardiovascular, major bleeding and unknown therefore do not appear *as
  causes of death*.

## Known upstream inconsistency

P-001's Marcumar starts 2024-01-10, before their observation period opens on
2024-02-01, so it lands in `med1_*` on the baseline row. This is carried over
unchanged from the codebook's `drug_exposure` example: prior medication
predating enrolment is clinically normal, but the resulting OMOP row falls
outside the person's observation period.
