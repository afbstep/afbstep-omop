Table of content

- [AF-B-STEP-OMOP-CDM Structure](#af-b-step-omop-cdm-structure)
  - [Preserving the original source code](#preserving-the-original-source-code)
  - [Table and content description](#table-and-content-description)
    - [`person` table](#person-table)
      - [`race_concepts_id` column](#race_concepts_id-column)
      - [`ethnicity categories` column](#ethnicity-categories-column)
    - [`visit_occurrence` table](#visit_occurrence-table)
    - [`observation_period` table](#observation_period-table)
    - [`procedure_occurrence` table](#procedure_occurrence-table)
    - [`drug_exposure` table](#drug_exposure-table)
    - [`measurement` table and `observation` table](#measurement-table-and-observation-table)
    - [`death` table](#death-table)
      - [`cause_concept_id` column](#cause_concept_id-column)
    - [`study` table](#study-table)
      - [`study_type_concept_id` column](#study_type_concept_id-column)
      - [`dataset_status_concept_id` column](#dataset_status_concept_id-column)
      - [`transfer_frequency_concept_id` column](#transfer_frequency_concept_id-column)
    - [`study_attribute` table](#study_attribute-table)
      - [`attribute_type_concept_id`](#attribute_type_concept_id)
      - [Data provision level values (`study_attribute.value_concept_id` when attribute type is `2000013015`)](#data-provision-level-values-study_attributevalue_concept_id-when-attribute-type-is-2000013015)
    - [`person_study` table](#person_study-table)
      - [`arm_type_concept_id` column](#arm_type_concept_id-column)
  - [Note on custom vocabulary](#note-on-custom-vocabulary)
    - [Custom domain](#custom-domain)
    - [Custom concept](#custom-concept)


# AF-B-STEP-OMOP-CDM Structure

This document describe the AFBSTEP-OMOP data model in more depths: 
- the available tables
- field (columns)
- concept id (values)

## Preserving the original source code

Alongside the standard concept, most tables also have a
`*_source_value` and `*_source_concept_id` pair — e.g.
`condition_source_value`/`condition_source_concept_id`,
`measurement_source_value`/`measurement_source_concept_id`.

`*_source_value` holds the original code or text exactly as it
appeared in the source data (e.g. an ICD-10 code, a local lab test
code, a variable string). `*_source_concept_id` holds the concept for that original
code, if it maps to one in Athena — even if that concept is not
itself standard.

If the standard concept mapping later turns out to be imprecise or 
needs revisiting, the original source code is still there to re-map 
from, without needing to go back to the raw data. 

See example in `mapping_codebook.md` file


## Table and content description

### `person` table

| field | holds |
|---|---|
| `person_id` | Primary key |
| `gender_concept_id` | Required. `8532` (FEMALE), `8507` (MALE), or `2000014000` (DIVERSE) |
| `year_of_birth` | Required |
| `race_concept_id` | Required by the CDM. Pin to `0` ("No matching concept") where the source does not collect race. |
| `ethnicity_concept_id` | Required by the CDM. Same convention as `race_concept_id` — pin to `0` where not collected |
| `person_source_value` | Free-text source identifier |

#### `race_concepts_id` column

| concept_id | concept_name | domain_id | vocabulary_id | concept_class_id | standard_concept | concept_code |
|---|---|---|---|---|---|---|
| `8657` | American Indian or Alaska Native | Race | Race | Race | S | 1 |
| `8515` | Asian | Race | Race | Race | S | 2 |
| `8516` | Black or African American | Race | Race | Race | S | 3 |
| `8557` | Native Hawaiian or Other Pacific Islander | Race | Race | Race | S | 4 |
| `8527` | White | Race | Race | Race | S | 5 |

In addition to the six standard `race` concepts, Athena offers 
more granular classifications. If your source covers a more 
specific category than the six basic categories, search directly 
within Athena for more precise concepts.

#### `ethnicity categories` column

There are no umbrella concepts for the mandatory field `ethnicity`. 
If you have collected data on this, you must search for the 
relevant concepts in the Athena vocabulary. 

### `visit_occurrence` table

| field | hold values (example) |
|---|---|
| `visit_occurrence_id` | Primary key |
| `visit_concept_id` | Required. `9202` (Outpatient Visit), `9201` (Inpatient Visit) |
| `visit_start_date` / `visit_end_date` | Required. A single-day visit has the same start and end date |
| `visit_type_concept_id` | Required — provenance. `32827` ("EHR encounter record") is the standard pin used throughout this guideline |

### `observation_period` table

| field | hold values (example) |
|---|---|
| `observation_period_id` | Primary key |
| `observation_period_start_date` | Typically the enrolment/baseline date |
| `observation_period_end_date` | Date of last known contact, or death |
| `period_type_concept_id` | `44814723` ("Period while enrolled in study") — note: `standard_concept` is `None` for this concept in Athena, not `S` like the other pinned type concepts in this guideline |

### `procedure_occurrence` table

Ablation and other interventional procedures map using the general pattern: 
a concept identifying what was done, a date, and a type concept for provenance.

| field | hold values (example) |
|---|---|
| `procedure_occurrence_id` | Primary key |
| `procedure_concept_id` | The procedure performed |
| `procedure_date` | — |
| `procedure_type_concept_id` | Provenance |
| `visit_occurrence_id` | The visit this procedure was performed during |

### `drug_exposure` table

| field | hold values (example) |
|---|---|
| `drug_exposure_id` | Primary key |
| `drug_concept_id` | The drug or drug class |
| `drug_exposure_start_date` / `drug_exposure_end_date` | — |
| `drug_type_concept_id` | Provenance |

### `measurement` table and `observation` table

Both follow the same shape: a concept identifying what was recorded,
a date, and a type concept for provenance. 
`measurement` is for
numeric results (`value_as_number`, with a required `unit_concept_id`).
`observation` is for categorical findings (`value_as_concept_id`) or facts with no natural numeric value.

| field | hold values (example) |
|---|---|
| `measurement_concept_id` / `observation_concept_id` | What was recorded |
| `measurement_date` / `observation_date` | — |
| `measurement_type_concept_id` / `observation_type_concept_id` | Provenance |
| `value_as_number` (measurement) | The numeric result |
| `unit_concept_id` (measurement) | Required whenever `value_as_number` is set |
| `value_as_concept_id` (either) | The categorical answer, where applicable |

This is the default pattern. Where a later section in this guideline
defines a special case for a specific concept, missingness, AF burden
window/episode scoping, comorbidity dating, that section's rule takes
precedence over this general one.

### `death` table

| field | hold values (example) |
|---|---|
| `person_id` | — |
| `death_date` | — |
| `death_type_concept_id` | Provenance |
| `cause_concept_id` | The cause of death |

#### `cause_concept_id` column

| concept_id | concept_name | domain_id | vocabulary_id | concept_class_id | standard_concept |
|---|---|---|---|---|---|
| `316139` | Heart failure | Condition | SNOMED | Clinical Finding | S |
| `313217` | Atrial fibrillation | Condition | SNOMED | Clinical Finding | S |
| `4329847` | Myocardial infarction | Condition | SNOMED | Clinical Finding | S |
| `2000006000` | Death due to non-cardiovascular cause | Condition | AFBSTEP | Clinical Finding | S |
| `2000006001` | Death due to cardiovascular cause, unspecified | Condition | AFBSTEP | Clinical Finding | S |
| `2000006002` | Death due to stroke (unspecified) | Condition | AFBSTEP | Clinical Finding | S |
| `2000005002` | Major bleeding (ISTH criteria) | Condition | AFBSTEP | Clinical Finding | S |
| `0` | No matching concept | Metadata | None | Undefined | — |

**A note on specificity.** These pinned concepts are the unspecified
default for each category. Where a provider's source data records a
more specific cause, e.g. a stroke subtype (`443454` "Cerebral
infarction," ischaemic; `35609033` "Haemorrhagic stroke"), search
Athena for the closer standard concept and use that instead.


### `study` table

AFBSTEP extension. 
These are AFBSTEP-specific administrative categories, which are 
listed under the custom domain ‘Methodological Concept’. These 
concepts are used in AFBSTEP’s own extension tables, not in the 
official OMOP-CDM tables. Exception: Countries in `study_attribute` 
should be coded using standard OMOP geographical concepts.

| field | holds |
|---|---|
| `study_id` | Primary key |
| `study_name` | Free-text name, defined by the partner site |
| `nct_number` | The study's ClinicalTrials.gov identifier, if registered |
| `contributor` | Free-text name of the legal entity contributing the data |
| `extended_affiliate` | Boolean: was this data contributed on behalf of, or with the authorisation of, another beneficiary? |
| `extended_affiliate_detail` | Free text naming that other beneficiary; populated only when `extended_affiliate` is true |
| `study_type_concept_id` | Study type (see the custom vocabulary below) |
| `n_data_subjects` |(Current) number of data subjects |
| `study_start_date` | Data collection period — start|
| `study_end_date` | Data collection period — end |
| `median_follow_up_months` | Median follow-up, in months |
| `dataset_status_concept_id` | Locked or rolling (see the custom vocabulary below) |
| `transfer_frequency_concept_id` | One-off or periodic (see the custom vocabulary below) |

`study` holds no multi-select attributes. These are stored separately in `study_attribute` to keep the 
actual `study` table as lightweight as possible. 

#### `study_type_concept_id` column

| concept_id | concept_name | domain_id |
|---|---|---|
| `2000013001` | RCT | Methodological Concept |
| `2000013002` | Interventional IDE | Methodological Concept |
| `2000013003` | Observational cohort | Methodological Concept |
| `2000013004` | RPM / registry | Methodological Concept |
| `2000013005` | Claims data | Methodological Concept |
| `2000013006` | Other | Methodological Concept |

#### `dataset_status_concept_id` column 

| concept_id | concept_name | domain_id | notes |
|---|---|---|---|
| `2000013007` | Locked dataset | Methodological Concept | Final, will not be updated further |
| `2000013008` | Rolling dataset | Methodological Concept | Periodically updated |

#### `transfer_frequency_concept_id` column

| concept_id | concept_name | domain_id |
|---|---|---|
| `2000013009` | One-off transfer | Methodological Concept |
| `2000013010` | Periodic transfer | Methodological Concept |


### `study_attribute` table

AFBSTEP extension.
A single table for every study-level attribute that allows more than
one answer per study. This is where the ‘country of data collection’ 
and ‘provision-level information’, as well as any additional 
multi-selection information live.

| field | holds |
|---|---|
| `study_id` | Which study this applies to |
| `attribute_type_concept_id` | Which attribute this row is about (e.g. "country of data collection," "data provision level") |
| `value_concept_id` | The selected value for that attribute |

One row per selected value: A study reporting two countries and two
provision levels has four `study_attribute` rows.

#### `attribute_type_concept_id` 

| concept_id | concept_name | domain_id |
|---|---|---|
| `2000013015` | Data provision level (attribute type) | Methodological Concept |
| `2000013016` | Country of data collection (attribute type) | Methodological Concept |

#### Data provision level values (`study_attribute.value_concept_id` when attribute type is `2000013015`)

| concept_id | concept_name | domain_id |
|---|---|---|
| `2000013011` | Metadata only | Methodological Concept |
| `2000013012` | Tabular analysis data | Methodological Concept |
| `2000013013` | Tabular analysis data incl. raw signals | Methodological Concept |
| `2000013014` | Tabular analysis data incl. raw imaging | Methodological Concept |

### `person_study` table
AFBSTEP extension.

| field | holds |
|---|---|
| `person_id` | — |
| `study_id` | Which study this person was enrolled in |
| `observation_period_id` | The observation period corresponding to this enrolment |
| `enrollment_date` | — |
| `arm_source_value` | Free text, exactly as the provider reported the arm name (e.g. "Intervention," "Clinical Intervention," "Comparator") |
| `arm_type_concept_id` | The arm's role, from a controlled vocabulary (see below) |

#### `arm_type_concept_id` column

| concept_id | concept_name | domain_id |
|---|---|---|
| `37529738` | Treatment Arm | Observation |
| `37542561` | Control Arm | Observation |
| `37530454` | Placebo Comparator Arm | Observation |
| `37543327` | Sham Comparator Arm | Observation |
| `37529223` | No Intervention Arm | Observation |

### `source` table 
AFBSTEP extension.

| field | holds |
|---|---|
| `source_id` | Primary key |
| `person_id` | — |
| `link_to_file` | A UUID identifying the file (see below) |
| `file_concept_id` | What kind of file this is (see the concept table below) |
| `source_event_id` | The id of the record this file documents |
| `source_event_field_concept_id` | Which table/field `source_event_id` refers to |

`source_event_id`/`source_event_field_concept_id` work the same way as
the `episode_event`/`*_event_id` mechanisms used elsewhere in this
guideline: `source_event_id` is a generic integer that could point to
a row in `episode`, `measurement`, `observation`, or elsewhere;
`source_event_field_concept_id` says which.

### `device_specs` table
AFBSTEP extension.

| field | holds |
|---|---|
| `episode_id` | The episode this device information applies to (required) |
| `person_id` | — |
| `device_exposure_id` | Links to the device's identity row (required) |
| `device_algorithm` | Free-text detection algorithm identifier, as reported by the source (e.g. a manufacturer's proprietary AF-detection algorithm name) |
| `device_algorithm_v` | Free-text version of that algorithm |
| `device_sn` | The device's individual serial number. Not covered by `device_exposure.unique_device_id` (UDI-DI only). This is the only place a serial number is recorded |
| `device_v` | Free-text hardware/firmware version of the device itself |

#### Why device_specs is keyed by episode

A single physical device is worn or implanted continuously and
produces many episodes over time. Its serial number and hardware
version do not change between those episodes, so the same values
appear on every `device_specs` row linked to that device. This
repetition is expected, not a modelling error. What can differ between
episodes is the detection algorithm version, if the device receives a
firmware update partway through the monitoring period; recording it
per episode, rather than once per device, is what allows that change
to be captured.


## Note on custom vocabulary

A concept is proposed as custom (`status = custom_proposed`) only
after a documented search of Athena finds no suitable standard
concept. Every custom concept in this vocabulary carries a 
`rationale` explaining why no standard 
concept fit, so the decision can be checked later.

### Custom domain

Two custom *domains*,‘External Data’ and ‘Methodological Concept’, 
were created as parent categories to which a concept belongs, as some 
custom concepts could not be clearly assigned to a standard domain.

| domain_id | domain_name | Used for |
|---|---|---|
| `External Data` | External Data Reference | File-type concepts (`source.file_concept_id`) referencing content stored outside the CDM |
| `Methodological Concept` | AFBSTEP Methodological/Operational Concept | Administrative and study-metadata concepts used in AFBSTEP's own extension tables |

### Custom concept

Custom concept IDs are organised into numbered blocks, each reserved
for one topic, so that related concepts stay grouped.

| Block | ID range | Topic |
|---|---|---|
| 00 | `2000000000`–`2000000999` | AF pattern classification |
| 01 | `2000001000`–`2000001999` | HF phenotype classification |
| 02 | `2000002000`–`2000002999` | Risk scores |
| 03 | `2000003000`–`2000003999` | Procedures |
| 04 | `2000004000`–`2000004999` | Devices and energy sources |
| 05 | `2000005000`–`2000005999` | Follow-up endpoints and complications |
| 06 | `2000006000`–`2000006999` | Causes of death |
| 07 | `2000007000`–`2000007999` | Follow-up and ascertainment context |
| 08 | `2000008000`–`2000008999` | AF burden (aggregated window, Case A) |
| 09 | `2000009000`–`2000009999` | AF episodes (disaggregated, Case B) and device diagnostics |
| 10 | `2000010000`–`2000010999` | External file references |
| 11 | `2000011000`–`2000011999` | AF Episode types |
| 12 | `2000012000`–`2000012999` | Drug classes not covered by RxNorm |
| 13 | `2000013000`–`2000013999` | Methodological/operational concepts (missingness markers, study metadata) |
| 14 | `2000014000`–`2000014999` | Person/demographic concepts |




