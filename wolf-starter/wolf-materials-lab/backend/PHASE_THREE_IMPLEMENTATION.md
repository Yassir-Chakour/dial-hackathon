# Phase Three Implementation Plan: France Ingestion Engine

This document translates Phase Three of `GOALS.md` into an implementation plan.

Phase Three should turn the supplied France source fixture into validated, provenance-preserving records. It should make source structure and uncertainty explicit, but it should not yet perform full version reconciliation, recommendation generation, agent orchestration, or approval enforcement.

## 1. Phase-three outcome

At the end of this phase, the backend should be able to:

- accept the supplied France raw-row and CSV representations;
- preserve source row numbers, sheet/section names and raw cell values;
- preserve duplicate-header context instead of silently dropping rows;
- classify data rows, headers, repeated invoice totals, credits and cancellations;
- normalize suppliers, products, dates, quantities, units, currencies and signed values;
- calculate line-level values only when evidence supports the calculation;
- validate required fields and route ambiguity to structured review items;
- identify France replacement-supplier update mode and declared scope;
- persist accepted records and exceptions through Phase Two services;
- produce deterministic and replayable ingestion results;
- keep model suggestions separate from validated facts.

The engine must be deterministic for the same source bytes, parser version and rules configuration.

## 2. Scope and boundaries

### Included

- France fixture ingestion;
- raw matrix and CSV parsing;
- source metadata and row provenance;
- canonical record construction;
- schema and business validation;
- record classification;
- replacement-scope detection as metadata;
- persistence of records and review exceptions;
- parser/rules versioning and result hashes;
- adversarial tests.

### Deferred

- applying the replacement to the prior current version;
- preserving unrelated suppliers in the final current dataset;
- previous/incoming/current reconciliation;
- recommendation calculation;
- LangGraph or autonomous agent decisions;
- OCR or scanned-invoice vision;
- reviewer approval enforcement;
- real source-system integrations.

Phase Three may produce an update scope and candidate records. Phase Four decides how those records change the current dataset.

## 3. Recommended project structure

Extend the backend with:

```text
backend/
├── app/
│   ├── ingestion/
│   │   ├── contracts.py          # Typed internal input/output models
│   │   ├── csv_reader.py         # CSV decoding and row preservation
│   │   ├── matrix_reader.py      # Raw fixture adapter
│   │   ├── headers.py            # Header and duplicate-header detection
│   │   ├── classifier.py         # Row-kind classification
│   │   ├── normalizers.py        # Pure field normalization
│   │   ├── france_rules.py       # France-specific layout and scope rules
│   │   ├── validators.py         # Required/cross-field validation
│   │   ├── evidence.py           # Source references and hashes
│   │   └── pipeline.py           # Deterministic orchestration
│   ├── schemas/ingestion.py
│   ├── services/ingestion_service.py
│   └── repositories/ingestion_reviews.py
└── tests/ingestion/
    ├── fixtures/
    ├── test_readers.py
    ├── test_headers.py
    ├── test_classification.py
    ├── test_normalization.py
    ├── test_validation.py
    ├── test_france_rules.py
    └── test_replay.py
```

Keep parsing, normalization and validation pure where possible. The pipeline coordinates stages; the ingestion service owns transactions and persistence.

## 4. Input contract and provenance

Define one internal contract for both CSV and raw matrices:

```python
class SourceRow(BaseModel):
    source_file_id: str
    source_version_id: str
    row_number: PositiveInt
    sheet_name: str | None
    cells: list[str | int | float | None]
    raw_text: str | None
    header_context: HeaderContext
```

Every row must retain:

- one-based source row number;
- sheet/section when available;
- original cell values before normalization;
- original column positions, including empty cells;
- active header context;
- encoding, representation and parser version.

Do not immediately convert rows into dictionaries keyed only by column name. That loses duplicate headers, positions and review evidence.

## 5. Safe CSV and raw-matrix reading

### CSV

The reader should:

- enforce a maximum byte size before reading;
- use an explicit encoding policy and report decoding failures;
- handle UTF-8 BOM where required;
- preserve empty cells and row positions;
- support quoted delimiters and embedded newlines;
- reject malformed rows or route them to review with exact row references;
- avoid formula evaluation;
- treat cells beginning with `=`, `+`, `-` or `@` as data, never executable content;
- enforce bounded row and column counts.

Do not evaluate formulas, macros or external links. CSV values are data only.

### Raw matrix

Adapt the supplied raw representation into the same `SourceRow` contract. Validate that it is a bounded list of rows and reject unsupported nested values rather than silently flattening arbitrary JSON.

### Identity

Compute the exact source hash before parsing. Store representation, parser name and parser version in metadata. The same bytes, parser and rules must produce the same row sequence and result hash.

## 6. Header handling

Headers are evidence, not guaranteed schema. Record:

- candidate header row numbers;
- normalized labels used only for matching;
- original labels and positions;
- duplicate labels and their positions;
- blank/preamble rows;
- repeated headers and section changes;
- confidence and reasons for the selected context.

When a label appears more than once, never overwrite a dictionary value. Represent columns by position and map them through an explicit fixture rule. Repeated headers inside a file remain stored raw evidence but are classified as `header` and excluded from commercial calculations.

If the header cannot be selected confidently, mark the affected section `needs_review`.

## 7. Row classification

Create a deterministic classifier returning `record_kind` and reasons:

```text
header | line | invoice_total | credit | cancellation | note | blank | unknown
```

Use explicit evidence:

- header labels and repeated-header position;
- invoice/document identifiers;
- description markers;
- quantity and unit presence;
- signed amount and total columns;
- credit/cancellation indicators;
- subtotal/total labels;
- position within a document section.

A numeric value alone is not evidence of a line item.

### Repeated invoice totals

A repeated document total must be stored as evidence but excluded from line-total aggregation. Record the reason:

```json
{
  "record_kind": "invoice_total",
  "calculation_role": "excluded_from_line_sum",
  "reason_code": "repeated_document_total"
}
```

This is classification, not deletion.

### Credits and cancellations

Credits and cancellations remain signed business events. Never take absolute values or discard negative lines. Store:

- original sign and raw amount;
- normalized amount;
- event type;
- affected document/line reference when available;
- an exception if that relationship cannot be established.

Keep a cancellation and the line it reverses as separate records. Later reconciliation applies the business semantics.

## 8. Normalization pipeline

Normalization must be explicit, deterministic and reversible enough for review. Store raw and normalized values together.

Recommended stages:

1. trim non-semantic whitespace while retaining raw cells;
2. normalize Unicode for comparisons;
3. map known labels through versioned aliases;
4. parse dates using explicit locale/format rules;
5. parse decimals without binary floating point;
6. normalize currency codes to uppercase;
7. normalize units only when a supported mapping exists;
8. normalize supplier/product identifiers through controlled aliases;
9. calculate derived line values only when required fields are valid;
10. attach warnings for every lossy or uncertain transformation.

Use `Decimal` for monetary and calculation-affecting quantities. Store scale and currency explicitly. Never silently convert currencies without an approved exchange-rate source and effective date; preserve source currency otherwise.

### Dates and numbers

Accept only documented France fixture formats. Reject ambiguous dates such as `01/02/03` without unambiguous source context. Support the fixture's decimal/thousands separators through explicit locale configuration. Do not apply global replacements that turn malformed values into plausible numbers.

### Units

Normalize only known units. `box`, `piece`, `liter` and similar values are not interchangeable without a verified conversion factor. Without a pack conversion, preserve the source unit and mark review.

### Suppliers and products

Use a versioned alias table for the supplied France fixture. Preserve the source label and canonical ID separately. An unknown supplier/product becomes an exception, not a fabricated canonical entity.

## 9. Canonical record contract

Define a typed record suitable for later phases:

```python
class CanonicalSourceRecord(BaseModel):
    source_record_key: str
    source_version_id: str
    source_row_number: int
    sheet_name: str | None
    record_kind: Literal[
        "line", "invoice_total", "credit", "cancellation", "unknown"
    ]
    supplier_id: str | None
    supplier_label: str | None
    product_id: str | None
    product_label: str | None
    document_id: str | None
    transaction_date: date | None
    quantity: Decimal | None
    unit: str | None
    currency: str | None
    unit_price: Decimal | None
    signed_value: Decimal | None
    validation_status: Literal["valid", "needs_review", "invalid"]
    warnings: list[str]
    errors: list[str]
    evidence: list[EvidenceRef]
```

Use `None` for unavailable values. Never use zero, empty strings or guessed identifiers to hide missing evidence.

## 10. France-specific rules

Keep France behavior behind a rules module. It should:

- recognize the supplied France layout and representation;
- map source columns by position and known labels;
- identify replacement-supplier update mode;
- extract declared market/supplier scope as metadata;
- identify candidate replacement records;
- leave unrelated-supplier preservation to Phase Four;
- return its rules version in every ingestion result.

Example scope result:

```json
{
  "market": "FR",
  "update_mode": "replacement",
  "supplier_scope": ["supplier-key"],
  "confidence": "high",
  "evidence": [{"source_row": 2, "field": "update_type"}]
}
```

If scope is unclear, do not default to full-market replacement. Return `needs_review` with the candidate scope and supporting evidence.

## 11. Validation and review routing

Separate:

- **error** — cannot safely participate in a calculation;
- **warning** — usable but has a limitation;
- **review** — human decision required;
- **valid** — required evidence and supported transformations exist.

Required checks include:

- supplier/product identity where required;
- document/line identity where available;
- valid date and numeric formats;
- currency for monetary values;
- unit for quantities;
- signed-value consistency with credit/cancellation markers;
- no unsupported unit conversion;
- no duplicate source-record key within a version;
- row reference points to preserved raw source;
- invoice totals are not counted as line values;
- source version and parser version are attached.

Persist review items with source version, record, exact row/sheet, field, raw value, proposed normalized value, reason code, severity and status.

Never silently repair an ambiguous value. Abstention is safer than an unsupported guess.

## 12. Provenance and deterministic output

Every canonical record links to source file, version, row and relevant columns. Evidence references should remain stable if display labels change.

Calculate an ingestion result hash from a canonical sorted representation containing:

- source file hash;
- source version;
- parser/rules versions;
- canonical record values;
- validation statuses and reason codes;
- update-scope result.

Do not include timestamps or random IDs in the business result hash. Use a deterministic `source_record_key` derived from source version, row/section and stable document/line fields. Document limitations when the source has no stable line identifier.

## 13. Security and privacy

### Security

- Enforce file-size, row-count, column-count and field-length limits before processing.
- Treat every cell as untrusted data; do not evaluate formulas, macros, links or embedded instructions.
- Accept bytes, not server filesystem paths, from clients.
- Never use source labels to construct SQL, shell commands, URLs or dynamic imports.
- Use parameterized persistence methods from Phase Two.
- Apply explicit processing budgets to avoid unbounded or quadratic work.
- Record parser/rules versions for reproducibility and incident investigation.
- Keep raw values out of normal logs; log source hash, row number, error code and request ID.
- If a model assists classification, treat output as a proposal requiring deterministic checks.

### Privacy

- Process only fields needed for the procurement decision and evidence trail.
- Keep raw source inside the configured storage boundary; do not send it externally in this phase.
- Do not expose full raw rows in API errors; return safe row references and review IDs.
- Redact source fields from logs and telemetry.
- Keep synthetic-data labels attached to fixture-derived records.
- Define retention/deletion before accepting real supplier files.
- Do not infer people, contacts or identities from supplier rows without a documented need.

## 14. Reusable functions

Keep core transformations pure and reusable across Italy, Hungary and Kosovo:

- `read_source_rows(payload, representation)`;
- `detect_header_context(rows)`;
- `normalize_header(label)`;
- `classify_row(row, context)`;
- `parse_decimal(value, locale)`;
- `parse_date(value, formats)`;
- `normalize_currency(value)`;
- `normalize_unit(value, aliases)`;
- `normalize_identifier(value, aliases)`;
- `build_source_record_key(context, row)`;
- `build_evidence_ref(source_version_id, row_number, columns)`;
- `validate_record(record)`;
- `compute_ingestion_result_hash(result)`;
- `persist_ingestion_result(result, transaction)`.

Country-specific rules should provide mappings/configuration instead of duplicating these functions.

## 15. Testing strategy

Use the supplied fixture plus focused adversarial fixtures.

### Reader tests

- quoted commas and embedded newlines;
- UTF-8 BOM;
- empty cells and trailing columns;
- malformed row width;
- oversized input;
- unsupported nested raw-matrix values;
- exact one-based row preservation.

### Header tests

- duplicate header labels;
- repeated headers in the middle of a file;
- blank preamble rows;
- multiple sections;
- ambiguous header selection routed to review.

### Classification tests

- ordinary line;
- repeated invoice total;
- credit and negative cancellation;
- note, blank and unknown rows;
- deceptive numeric row without line evidence.

### Normalization tests

- France decimal separators;
- invalid and ambiguous dates;
- currency preservation;
- supported and unsupported units;
- supplier/product aliases;
- missing values remain `None`;
- raw and normalized values are both retained.

### Pipeline tests

- full France fixture produces expected record kinds;
- repeated invoice totals do not become line records;
- cancellation sign is preserved;
- replacement scope is detected with evidence;
- ambiguous records become review items;
- same source/parser/rules produce the same result hash;
- same event does not create duplicate records;
- parser failure rolls back persistence.

Do not test only aggregates. Assert row-level provenance and classification because those are the later decision evidence contract.

## 16. Implementation order

1. Add ingestion schemas and parser/rules version constants.
2. Implement bounded CSV and raw-matrix readers.
3. Implement header context and duplicate-header handling.
4. Implement deterministic row classification.
5. Implement pure normalization using `Decimal` and explicit locale rules.
6. Implement France mapping and replacement-scope detection.
7. Implement validation and review-item creation.
8. Connect the pipeline to Phase Two source/version/event/record services.
9. Add result hashing and replay handling.
10. Add the full fixture and adversarial test suite.
11. Run migrations, tests, linting and type checks from a clean checkout.
12. Document unsupported layouts and every intentional abstention.

## 17. Explicitly out of scope for Phase Three

Do not implement:

- merging incoming records into the current France dataset;
- preserving unrelated suppliers in a current version;
- final reconciliation against expected totals;
- recommendation or savings calculations;
- approval state changes;
- autonomous model decisions;
- OCR/scanned-document extraction;
- real supplier-system imports;
- production object storage or multi-tenant access control.

## Definition of done

Phase Three is complete when the France source produces immutable, typed and provenance-preserving records; repeated headers and invoice totals are excluded from line calculations; credits and cancellations retain their sign; replacement scope is explicit; ambiguous rows become review items; replay is deterministic and idempotent; and the full result passes security, privacy, migration, lint, type and test checks.

