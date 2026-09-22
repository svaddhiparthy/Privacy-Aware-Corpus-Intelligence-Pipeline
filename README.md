# Privacy-Aware Corpus Intelligence Pipeline

[![CI](https://github.com/Vaddhiparthy/Privacy-Aware-Corpus-Intelligence-Pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Vaddhiparthy/Privacy-Aware-Corpus-Intelligence-Pipeline/actions/workflows/ci.yml)

**Live:** [vaddhiparthy.com/Privacy-Aware-Corpus-Intelligence-Pipeline](https://vaddhiparthy.com/Privacy-Aware-Corpus-Intelligence-Pipeline)

## Overview

A batch pipeline that turns a large, semi-structured JSON export into three reconciled,
reviewable output queues.

The source is a multi-shard export of nested conversation documents: no fixed schema per
record, deeply nested message trees, variable payload shapes, and a total size that does not
fit comfortably in memory. The pipeline reads it shard by shard, flattens each document into
addressable units, applies a deterministic rule set to route every unit into exactly one
queue, and writes both machine-readable JSON and human-reviewable Markdown.

The design constraints that shaped it are the usual batch-processing ones:

- **Memory-bounded ingestion.** One shard is resident at a time; records stream downstream
  through generators, so peak memory tracks the largest shard, not the export.
- **Total accounting.** Every unit read must appear in exactly one output queue. Inputs and
  outputs reconcile, and the reconciliation is asserted in CI.
- **Deterministic routing.** No sampling, no randomness, no network call in the core path.
  The same input and the same rule tables always produce the same output.
- **Auditability.** Every routing decision carries its evidence — which rule fired, which
  terms matched, which score was computed — so a decision can be reviewed or recalibrated
  later without rerunning anything.
- **Fail-closed policy.** Ambiguity routes to a hold queue, never to the released queue.

The domain happens to be privacy: units carrying direct identifiers or sensitive personal
context are held back, and the rest become publication candidates. The routing logic is
lexical rule matching over versioned term tables, not a learned model.

## Architecture

```text
   export/conversations-*.json        (N shards, JSON array per shard)
                |
                v
 [1] INGEST          iter_conversations()    one shard resident at a time
                |                            non-array shards skipped
                v
 [2] EXTRACT         extract_messages()      walk nested mapping tree
                |                            -> ordered (role, text, created) rows
                v
 [3] UNITIZE         CorpusUnit              1 conversation unit per document
                |                            + chunk units on the recovery path
                v
 [4] DERIVE          text.term_counter()     tokenize, fold suffixes, drop stopwords
                |                            -> term frequency vector
                v
 [5] ROUTE           classifier.classify()   identifiers -> sensitive domains
                |                            -> low signal -> public candidate
                |
                +--- decision starts with "exclude"? ---+
                |                                       |
                |                                       v
                |                            [6] CHUNK RECOVERY
                |                                re-unitize at --chunk-chars
                |                                and route each chunk through [4]-[5]
                |                                       |
                v                                       v
 [7] AGGREGATE       pipeline.build_summary()    counts + distributions
                |
                v
 [8] WRITE           reports.write_outputs()
                |
                +--> public_candidates.{json,md}
                +--> excluded_private.{json,md}
                +--> skipped_low_signal.json
                +--> topic_summary.md
                +--> scan_summary.json          <- reconciliation record
```

## Stages

### 1. Ingest — `reader.iter_conversations`

Reads `conversations-*.json` from the export directory in sorted filename order. Each shard
is expected to be a JSON array of conversation objects; a shard whose top level is not an
array is skipped rather than failing the run. Conversations are yielded lazily, so exactly
one shard is held in memory at a time and no downstream stage ever materializes the corpus.

### 2. Extract — `reader.extract_messages`

Each conversation carries a `mapping` object whose values are message nodes. The extractor
walks those values, pulls text out of `message.content.parts` (accepting both bare strings
and objects with a `text` field), drops nodes with no text, defaults a missing
`message.author.role` to `unknown`, and orders the surviving rows by `create_time`.

### 3. Unitize — `CorpusUnit`

A unit is the addressable record of the pipeline: an immutable dataclass of
`unit_id`, `source_file`, `conversation_id`, `title`, `unit_type`, `chunk_index`, `text`.

| Granularity | `unit_id` | Text |
| --- | --- | --- |
| conversation | `{conversation_id}:conversation` | `TITLE: ...` followed by every message as `ROLE: text` |
| chunk | `{conversation_id}:chunk:{n}` | `TITLE: ...` followed by a contiguous run of messages |

`conversation_id` is the document's own `id` when present, otherwise a deterministic fallback
derived from the shard name and the running record index. Chunking (`reader.chunk_messages`)
accumulates whole messages greedily up to `--chunk-chars` and never splits a message.

### 4. Derive — `text.py`

`tokenize` matches word-shaped spans, lowercases, folds common suffixes (`ies -> y`, and
trailing `ing`, `ed`, `es`, `s`), then drops tokens shorter than three characters, bare
digits, and a fixed stopword list. `term_counter` returns the resulting term frequencies.
Taxonomy entries containing a space or hyphen are matched as literal substrings on the
lowercased text instead, so multi-word phrases are not destroyed by tokenization.

### 5. Route — `classifier.classify`

Produces exactly one decision per unit, plus the evidence behind it. Rules are evaluated in
strict precedence order; the first match wins.

| Order | Condition | Decision |
| ---: | --- | --- |
| 1 | any direct-identifier pattern matches (`pii.PATTERNS`, 7 categories) | `exclude_private_identifier` |
| 2 | any sensitive-domain term matches the body, or a sensitive term appears in the title (`taxonomy.SENSITIVE_DOMAIN_TERMS`, 3 groups) | `exclude_sensitive_domain` |
| 3 | no public topic matched, or fewer than 10 retained tokens | `skip_low_signal` |
| 4 | otherwise | `public_candidate` |

Direct-identifier categories are `ssn`, `email`, `phone`, `card_like_number`, `api_secret`,
`identity_document_context`, and `street_address_context`. Sensitive-domain groups are
`private_health`, `immigration_private`, and `resume_job_search_private`. Public topics come
from ten term families in `taxonomy.py`; the top four scoring families are retained per unit.

A publication score is computed for every unit from four capped components:

```text
score = min(log10(max(char_count, 10)) * 18, 72)   # length, with diminishing returns
      + min(token_count / 35, 35)                  # retained-token volume
      + min(sum(topic term scores), 80)            # topical evidence
      + min(len(top_terms), 30)                    # vocabulary breadth
```

The ceiling is roughly 217. `pipeline.run_pipeline` applies `--min-public-score` (default 55)
as a release gate: a `public_candidate` scoring below the threshold is demoted to the
low-signal queue rather than dropped, which is what keeps the reconciliation exact.

Each unit is also labelled `needs_current_fact_check` or `evergreen_candidate`, based on
whether its topics fall in the time-sensitive set or its text contains currency markers such
as recent years, `latest`, `pricing`, `policy`, or `version`. The label drives ordering in the
Markdown review schedule and nothing else.

### 6. Chunk recovery

A long document is rarely uniform. If a whole conversation is excluded, one sensitive passage
would otherwise discard everything else in the thread. So exclusion triggers a second pass:
the conversation is re-unitized at `--chunk-chars` granularity and each chunk is routed
through the identical `classify` call. Chunks that clear the gate are recovered into the
public queue; the excluded parent stays in the exclusion queue. Chunk fan-out happens **only**
on the exclusion branch, so a clean conversation costs one classification, not many.

### 7. Aggregate — `pipeline.build_summary`

Reduces the three queues to run-level counts plus three distributions: public units by primary
topic, exclusions by reason, and exclusions by identifier category. The CLI merges the run
parameters (`export_dir`, `out_dir`, `min_public_score`, `chunk_chars`) into the same record
so a summary is self-describing.

### 8. Write — `reports.write_outputs`

Writes the JSON row sets, the reconciliation summary, and the Markdown review catalogs.

## Data contracts and invariants

**Input contract.** Export directory containing `conversations-*.json`; each shard a JSON
array; each element an object with optional `id` and `title` and a `mapping` of message nodes.
Violations degrade (shard or node skipped) rather than aborting the run.

**Unit identity.** `unit_id` is unique per `(conversation, granularity, chunk_index)` and is
the join key across every output file, including the validation artifacts.

**Single-queue routing.** `classify` returns exactly one of four decisions, and
`run_pipeline` appends each classified unit to exactly one list. There is no path on which a
unit is counted twice or silently dropped.

**Reconciliation invariant.**

```text
units_scanned == public_candidate_units + excluded_units + skipped_units
```

It holds structurally in `pipeline.run_pipeline` (one increment of `unit_count`, one list
append, per unit) and is written into every run's `scan_summary.json`. It is *enforced* on the
recorded run by `scripts/check_published_numbers.py`, which CI executes on every push:

- the corpus split must sum to `units_scanned`;
- each full-corpus validator's three labels must also sum to `units_scanned`;
- each bounded-sample validator's labels must sum to the sample size;
- the policy classifier's public/private/review counts must equal the pipeline's
  public/excluded/skipped counts, since it is the same code path under a three-label mapping;
- declared topic-group count must match the listed groups, and topic units must not exceed
  public candidates;
- the agreement percentages must total 100.

The same job runs `scripts/export_page_snippets.py`, which re-extracts the functions published
on the project page directly from source and fails if the stored artifact has drifted. Neither
the numbers nor the code shown externally can diverge from this repository without CI failing.

**Redaction contract.** An exclusion record names the category that fired, never the matched
value. Pinned by `test_curated_output_never_carries_the_raw_identifier`, which asserts a
synthetic identifier appears in no field of its own classification.

**Determinism.** Core ingest, routing, and reporting perform no I/O beyond the export and the
output directory, and use no randomness. Rerunning a run reproduces it byte for byte as long
as the term tables are unchanged.

## Outputs

| File | Contents |
| --- | --- |
| `public_candidates.json` | Full row per released unit |
| `public_candidates.md` | Catalog sorted by descending score, plus a detailed preview block for the top 100 |
| `excluded_private.json` | Full row per excluded unit |
| `excluded_private.md` | Catalog grouped by decision, showing reasons and identifier categories |
| `skipped_low_signal.json` | Held units, capped at the first 2000 rows |
| `topic_summary.md` | Topic counts with example titles, exclusion counts, and a weekly draft review schedule (up to 156 rows) |
| `scan_summary.json` | Run parameters, queue counts, topic counts, exclusion counts, identifier counts |

### Row schema

Every JSON row is a serialized `Classification` with the same 18 fields:

| Field | Type | Notes |
| --- | --- | --- |
| `unit_id` | string | Join key |
| `source_file` | string | Originating shard |
| `conversation_id` | string | Document identity |
| `title` | string | Document title, or `(untitled)` |
| `unit_type` | string | `conversation` or `chunk` |
| `chunk_index` | int | 0 for a conversation unit |
| `decision` | string | One of the four routing decisions |
| `score` | float | Publication score, 2 decimal places |
| `char_count` | int | Raw unit length |
| `token_count` | int | Retained tokens after normalization |
| `cleaned_terms` | string[] | Sorted distinct terms, capped at 350 |
| `top_terms` | [string, int][] | 25 most frequent terms with counts |
| `public_topics` | [string, int][] | Up to 4 topic families with evidence scores |
| `exclusion_reasons` | string[] | Sensitive-domain group names |
| `identifier_hits` | string[] | Identifier category names |
| `freshness` | string | `needs_current_fact_check` or `evergreen_candidate` |
| `needs_fact_check` | bool | Same signal as a boolean |
| `preview` | string | Whitespace-collapsed excerpt, 360 characters |

`scan_summary.json` is the authoritative count record for a run; `skipped_low_signal.json` is
truncated by design and should not be used for reconciliation.

## Recorded run

`docs/artifacts/corpus_run/summary.json` is the artifact of record for a full pass over a
private corpus. It contains aggregates only — no text, no titles, no per-record topics, no
source-file names. Every externally published figure is read from this file and checked in CI.

| Metric | Value |
| --- | ---: |
| Units scanned | 11,336 |
| Public candidates | 3,078 |
| Excluded | 8,227 |
| Low signal | 31 |
| Identifier categories | 7 |
| Topic groups | 10 |

Public candidates by topic group, as recorded:

| Topic group | Units |
| --- | ---: |
| Software/Data/Automation | 761 |
| AI/Agents/LLM | 669 |
| Product Reviews/Buying | 388 |
| Infrastructure/Home Lab | 382 |
| Learning/Tutorials | 329 |
| Food/Home | 194 |
| Philosophy/Systems | 130 |
| Consumer Finance | 94 |
| Vehicles/OBD/Mobility | 67 |
| Creative/Culture/Publishing | 64 |

Cross-detector comparison over all 11,336 units, using three-label validator output:

| Validator | Public | Private | Review |
| --- | ---: | ---: | ---: |
| policy_classifier | 3,078 | 8,227 | 31 |
| strict_detector | 2,857 | 7,849 | 630 |
| semantic_score_classifier | 2,961 | 7,938 | 437 |

Agreement across those three: 87.02% unanimous, 12.54% two-to-one, 0.43% three-way split.

These figures were produced before the `private_health` calibration of 2026-09-14, which
stopped bare tokens such as `health`, `lab`, `sleep`, `weight`, and `pain` from excluding
ordinary engineering vocabulary. A rerun on the same corpus would return more public
candidates and fewer sensitive-domain exclusions. The numbers are published as the recorded
run, not as current behaviour; `summary.json` states this in its own provenance block.

## Install

Requires Python 3.10 or newer. The core pipeline has no third-party runtime dependencies.

```bash
python -m venv .venv
.venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Run

Main batch run, as a module or via the installed console script:

```bash
python -m corpus_privacy_intelligence.cli \
  --export-dir /path/to/export \
  --out-dir /path/to/outputs \
  --min-public-score 55 \
  --chunk-chars 9000
```

```bash
corpus-privacy-intelligence --export-dir /path/to/export --out-dir /path/to/outputs
```

| Flag | Default | Effect |
| --- | --- | --- |
| `--export-dir` | required | Directory holding `conversations-*.json` |
| `--out-dir` | required | Created if absent; receives all seven artifacts |
| `--min-public-score` | `55.0` | Release gate; below it a candidate is demoted to low signal |
| `--chunk-chars` | `9000` | Target chunk size on the recovery path |

The summary is printed to stdout as JSON and written to `scan_summary.json`.

Cross-detector validation, which routes each unit through three independent detectors and
records the cases where they disagree:

```bash
python -m corpus_privacy_intelligence.validation \
  --export-dir /path/to/export \
  --out-dir outputs/validation \
  --chunk-chars 9000 \
  --max-disagreements 500
```

Writes `automated_validation_summary.json`, `automated_validation_disagreements.json`, and
`automated_validation_report.md`.

Artifact checks, the same two commands CI runs:

```bash
python scripts/check_published_numbers.py
python scripts/export_page_snippets.py            # verify
python scripts/export_page_snippets.py --write    # regenerate
```

## Optional validation dependencies

Everything below is secondary. The pipeline routes, reconciles, and reports without any of it.
These paths exist to cross-check the rule tables against independent implementations and to
surface disagreements for calibration; they are never in the release path.

```bash
python -m pip install -e ".[nlp]"
```

`[nlp]` pulls in Presidio, spaCy, and scikit-learn. A separate `[embeddings]` extra pulls in
sentence-transformers, and `[all]` pulls in both. When a package is absent, its detector
reports itself unavailable with zero confidence and is excluded from the vote, rather than
being treated as a passing signal.

```bash
python -m corpus_privacy_intelligence.advanced_validation \
  --export-dir /path/to/export \
  --out-dir outputs/advanced_validation \
  --chunk-chars 9000 \
  --limit 300
```

`--limit 0` removes the bound. Presidio and spaCy are CPU-bound, so a bounded sample is the
practical default; the recorded comparison used 300 units for that reason.

### Local-only, optional: model-assisted disagreement review

This stage is opt-in, runs entirely against a service on the local machine, and is not part of
any documented run. It reads the disagreement file produced by
`corpus_privacy_intelligence.validation`, sends each saved record to a model served locally by
Ollama over HTTP, and records the returned label next to the local majority label for
comparison. It requires an Ollama instance already running on the same machine.

```bash
# local machine only; requires a local Ollama service on 127.0.0.1
python -m corpus_privacy_intelligence.ollama_validation \
  --input outputs/validation/automated_validation_disagreements.json \
  --out-dir outputs/ollama_validation \
  --model llama3.2:3b \
  --host http://127.0.0.1:11434 \
  --limit 50 \
  --timeout 180
```

The run resumes from existing results, so already-processed `unit_id` values are skipped, and
an unreachable service marks the item `review` with the error reason instead of failing the
run. The output is a comparison signal only and carries no authority over routing.

## Testing and CI

```bash
python -m pytest -q
python -m compileall src tests
```

86 tests. The suite is structured around the contracts above rather than around line coverage:

| File | Pins |
| --- | --- |
| `tests/test_pii.py` | One positive case per identifier category, plus a meta-test asserting no pattern ships untested, plus negative cases for version strings and clean technical text |
| `tests/test_classifier.py` | Routing precedence on representative units |
| `tests/test_privacy_fixtures.py` | Ten synthetic cases that must never reach the released queue, three legitimate near-misses that must not be excluded, the homonym regression pair, and the redaction contract |
| `tests/test_validators.py` | The three validators, their label bounds, their evidence requirement, and the majority vote |
| `tests/test_ensemble.py` | The weighted router: a strong private signal wins outright, public needs a margin, a detector that could not run does not tilt the route, and the function is deterministic |

Every fixture is synthetic. No corpus text is committed to this repository.

CI (`.github/workflows/ci.yml`) runs three jobs on Python 3.11 for every push and every pull
request into `main`:

1. **Lint** — `ruff check .` and `ruff format --check .`, pinned to ruff 0.8.6.
2. **Tests** — `pip install -e ".[dev]"` then `python -m pytest -q`, from a clean clone, using
   exactly the command this README documents.
3. **Published claims** — `scripts/check_published_numbers.py` and
   `scripts/export_page_snippets.py`, so published figures and published code cannot drift
   from the implementation.

## Repository layout

```text
.
├── .github/workflows/ci.yml                 lint, tests, published-claims jobs
├── pyproject.toml                           packaging, extras, pytest and ruff config
├── src/corpus_privacy_intelligence/
│   ├── cli.py                               batch entry point and run parameters
│   ├── reader.py                            shard ingestion, message extraction, chunking
│   ├── models.py                            CorpusUnit and Classification record types
│   ├── text.py                              tokenization, stopwords, suffix folding, previews
│   ├── pii.py                               direct-identifier patterns
│   ├── taxonomy.py                          public topic families and sensitive-domain terms
│   ├── classifier.py                        routing precedence and publication score
│   ├── pipeline.py                          orchestration, chunk recovery, aggregation
│   ├── reports.py                           JSON and Markdown artifact writers
│   ├── validators.py                        three independent detectors and majority vote
│   ├── validation.py                        cross-detector run and disagreement export
│   ├── advanced_detectors.py                detector wrappers, including optional packages
│   ├── advanced_validation.py               weighted ensemble comparison run
│   └── ollama_validation.py                 optional local-only disagreement review
├── scripts/
│   ├── check_published_numbers.py           reconciliation and consistency gate
│   └── export_page_snippets.py              source-to-artifact snippet generator
├── tests/                                   synthetic fixtures and contract tests
└── docs/
    ├── advanced_non_llm_validation.md       optional detector layer and calibration notes
    └── artifacts/
        ├── corpus_run/summary.json          recorded-run aggregates, the artifact of record
        └── page_snippets.json               extracted verbatim source of published functions
```

## Limitations and scope

- Single-process, single-machine batch. No scheduler, no orchestration layer, no incremental
  state: a rerun reprocesses the whole export. Shard-level parallelism would be the first
  change if throughput mattered.
- Memory is bounded by the largest single shard, not by a constant. A shard that does not fit
  in memory would need an incremental JSON parser in `reader.load_json`.
- Routing is lexical: term and phrase matching over hand-maintained tables. Recall is exactly
  as good as `taxonomy.py` and `pii.py`, and extending coverage means extending those tables
  and their fixtures. There is no learned model in the release path.
- `chunk_messages` never splits an individual message, so a single oversized message produces
  a chunk larger than `--chunk-chars`.
- Message ordering sorts on the stringified `create_time`, which is lexicographic rather than
  numeric. Ordering is stable but not guaranteed chronological for mixed-width timestamps.
- `skipped_low_signal.json` is truncated at 2000 rows; use `scan_summary.json` for counts.
- The source corpus is private and not committed, so a third party cannot reproduce the full
  run. The aggregates, the rule tables, the routing code, and the tests are all reproducible.
- `public_candidates` is a review queue, not a publishing decision. Exclusion reasons,
  identifier categories, topic scores, and previews are there to be read before anything
  derived from a unit is published.
- Policy changes belong in `taxonomy.py` and `pii.py` with matching fixtures in
  `tests/test_privacy_fixtures.py`. Loosening a rule without a fixture is how a privacy
  control silently stops working.

## License

See `LICENSE`.
