# Source

This directory contains all the files that defined the AFBSTEP-OMOP schema:
- `custom`: custom tables that extend the OMOP schema blackbone
- `structural`: the actual OMOP schema with version flag
- `spec`: a set of files defining the scope and the minimal data set. Each file answers one question:
    - `standard_vocabulary` / `custom_vocabulary`: "which concepts exist, and where does each belong?"
    - `tables`: "which tables do I populate at all?" Mandatory, expected, optional and out-of-scope tables
    - `minimal_dataset`: "which *fields* must actually be populated, and how completely?"
    - `minimal_concepts`: "which *concepts* must be present?" The consortium's Part C questionnaire
    - `plausibility`: "what may a value be?" Unit and range constraints (e.g. heart rate in /min, 20-300)
    - `custom_domains`: OMOP domains AFBSTEP declares that the standard vocabulary does not

## Editing rules

These apply to every file under `source/`.

| Directory | Who edits it | Rule |
|---|---|---|
| `structural/` | nobody | Vendored from OHDSI CommonDataModel. **Never hand-edit** — it must stay diffable against future CDM releases. If a stock constraint is wrong for AFBSTEP, resolve it in the spec, not in the DDL. |
| `custom/` | AFBSTEP maintainers | Structural additions only: tables AFBSTEP needs that the CDM does not have. |
| `spec/` | AFBSTEP maintainers and clinicians | Project decisions. Append and modify freely, following the formats below. |

General conventions for every `spec/` CSV:

- UTF-8, comma-separated, one header row, **no index column**.
- No leading or trailing whitespace in any field.
- Dates are ISO `YYYY-MM-DD`.
- **One row = one decision.** Never encode two decisions in one row.
- Some file carries a `rationale` column. This helps the review process.
- **No partner-specific or site-specific content.** TRUST variable names, REDCap
  sheet names and source codings belong in `cdm/`, not here. This
  package is consumed by every AFBSTEP site; anything naming one site's instrument
  will be read by the others as a requirement.

The Python layer is the *interpreter* of these files, never their author. If a
clinical decision requires a code change, the layering is wrong — domain experts
would be locked out of their own spec.

## Spec file formats

### `standard_vocabulary.csv` — pinned standard concepts

The standard OMOP concepts AFBSTEP commits to, pinned so that validation resolves
offline and reproducibly against this file rather than a vocabulary server.

**This list is not exhaustive and is not a whitelist.** It covers the concepts
needed for the minimal data set, plus some common but optional fields. Partners
may legitimately submit standard concepts that do not appear here — a concept
being absent from this file is not, on its own, an error. What a field will
accept is decided by the concept's `domain_id` and OMOP's own conformance rules,
not by membership of this file.

| Column | Content |
|---|---|
| `concept_id` | OHDSI standard concept id |
| `concept_name`, `domain_id`, `vocabulary_id`, `concept_class_id`, `standard_concept`, `concept_code` | copied verbatim from the OHDSI vocabulary |
| `valid_start_date`, `valid_end_date` | copied verbatim |
| `CDM_table` | the table this concept is expected to land in |
| `CDM_variable` | the concept field within that table |
| `valid_for_question` | for an **answer** concept (category name), the **question** concept (categories) it answers. Empty otherwise |

`CDM_table` is **not** derivable from `domain_id` and both columns carry
information — 23 rows deliberately disagree (e.g. a Condition concept routed to
`death` as a cause of death). Do not "fix" a disagreement without recording why.

### `custom_vocabulary.csv` — AFBSTEP-minted concepts

Same columns as `standard_vocabulary.csv`, plus three:

| Column | Content |
|---|---|
| `status` | lifecycle of the concept: `custom_proposed`, later `custom_accepted` / `retired` |
| `rationale` | **why this concept had to be minted.** Every row is a departure from the standard vocabularies, and this is the audit trail for it |
| `valid_for_episode_type` | the `episode` this concept may appear within. AF burden summarises a monitoring window, a peak rate describes one arrhythmia episode, and each is meaningless in the other's context |

`concept_id` must be in the `2000000000+` range reserved for local concepts, and
`vocabulary_id` is always `AFBSTEP`.

An **empty `CDM_table` and `CDM_variable` mean the concept is vocabulary
infrastructure** — a domain or a relationship declaration — rather than data that
lands in a column. Two concepts are legitimately unbound on these grounds. A
*half*-declared binding, one of the two filled, is always an error.

### Questions and answers — `valid_for_question`

A categorical variable needs two kinds of concept, and OMOP calls both
"concept", which is the source of most confusion here:

- a **question** concept names the category — *AF pattern*, *HF phenotype*,
  *Tobacco smoking status*. It goes in a question field such as
  `observation.observation_concept_id`.
- an **answer** concept is one permitted category — *Paroxysmal atrial
  fibrillation*, *Former smoker*. It goes in `observation.value_as_concept_id`.

`valid_for_question` is set on the **answer**, naming its question. Without it,
every answer sits in one undifferentiated pool and nothing can tell that

```
observation_concept_id = 2000008003   ("AF burden estimation method")
value_as_concept_id    = 45883458     ("Former smoker")
```

is nonsense: right table, right domain, both concepts pinned, both permitted in
their fields, and clinically meaningless.

A question needs an answer for **every** state it can take. A yes/no question
with only the "yes" answer pinned cannot record "no", which puts it back into
the same ambiguity as a bare condition row.

### `tables.csv` — scope and tier

One row per table AFBSTEP has an opinion about. Answers whether a partner has to
populate it at all — the coarsest gate in validation.

A table that is **not listed is out of scope**. The file therefore stays short and
every row is a decision someone actually made, rather than 40 rows asserting that
AFBSTEP does not care about `note_nlp`.

| Column | Content |
|---|---|
| `table` | table name, must exist in `structural/` or `custom/` |
| `tier` | `mandatory` / `expected` / `out_of_scope` |
| `rationale` | why it sits in that tier |

### `minimal_dataset.csv` — field-level requirements

One row per field AFBSTEP has an opinion about. This is where the project states
a requirement the DDL cannot: `person.race_concept_id` is `NOT NULL` in the CDM,
but AFBSTEP does not require it to be *informative* and accepts concept `0`.

A project requirement may be **stricter than the DDL, never looser** — a field
the CDM declares `NOT NULL` must still be present.

| Column | Content |
|---|---|
| `table`, `column` | must resolve against the parsed schema |
| `requirement` | `required` / `expected` / `optional` / `not_used` |
| `rationale` | why |

> There was a `min_completeness` column, and a validation layer that checked the
> proportion of populated rows against it. Both were removed. The measure could
> not be trusted: a threshold keyed by `(table, field)` averages over rows with
> opposite expectations. In the example export, 32 chronic comorbidities
> correctly had no end date and 22 hospitalisations correctly had one, giving
> "41% complete" against a 50% target — a number describing neither group. It
> also penalised the correct encoding of a lost value, which is an existing row
> with an empty `value_as_number`. If completeness returns, its thresholds need
> to be keyed by concept, as `plausibility.csv` already is.

### `minimal_concepts.csv` — the minimal data set, as concepts

The consortium's Part C questionnaire: the items a partner must be able to
supply. Where `minimal_dataset.csv` says which *fields* must be populated, this
says which *concepts* must be present — a dataset can satisfy one and fail the
other, with every field filled and no heart failure recorded anywhere.

| Column | Content |
|---|---|
| `part_c_domain` | Part C domain code, e.g. `MH`, `CE/AE` |
| `part_c_domain_label` | the domain's display name, repeated on each of its items |
| `part_c_item` | the item's **clinical** name, which is authoritative for display and deliberately differs from the OMOP concept name |
| `concept_id` | the concept carrying the item. May be empty: several device and resolution items have no concept yet, and that is a real state |
| `rationale` | why the domain is collected |

Row order is Part C display order. Every `concept_id` here must also appear in
one of the vocabulary files, which the source validator checks.

### `plausibility.csv` — unit and value constraints

**Keyed by concept, not by column.** `measurement.value_as_number` holds heart rate
and LVEF and AF burden; a range attached to the column alone is meaningless. 
Additional columns may be added in the futur to further enforce data distributions beyond min-max values.

| Column | Content |
|---|---|
| `concept_id` | the concept whose values are being constrained |
| `CDM_table`, `CDM_variable` | where those values live |
| `unit_concept_id` | required unit, blank if unitless |
| `min_value`, `max_value` | inclusive bounds. Give both or neither; a row with neither constrains nothing |
| `rationale` | clinical basis for the bounds |

## Modelling conventions

Need update