# Architecture

A batch pipeline that converts a local multi-shard JSON export into reconciled, reviewable output catalogs. Ingestion, routing, and reporting are deterministic and local: the core path makes no network call and uses no randomness.

## Pipeline

```text
Split JSON export (conversations-*.json)
  -> shard reader, one shard resident at a time
  -> message extraction from the nested mapping tree
  -> conversation units, plus chunk units on the recovery path
  -> term normalization and frequency counts
  -> identifier detector
  -> sensitive-domain policy
  -> public-topic scorer and release gate
  -> output router
  -> Markdown and JSON artifacts
```

## Runtime Components

| Component | Path | Role |
| --- | --- | --- |
| CLI | `src/corpus_privacy_intelligence/cli.py` | Parses run parameters, invokes the pipeline, merges parameters into the summary |
| Reader | `src/corpus_privacy_intelligence/reader.py` | Reads one shard at a time, extracts ordered messages, and builds chunks |
| Models | `src/corpus_privacy_intelligence/models.py` | `CorpusUnit` and `Classification` record types |
| Text layer | `src/corpus_privacy_intelligence/text.py` | Normalizes terms, removes stopwords, folds suffixes, and builds previews |
| PII detector | `src/corpus_privacy_intelligence/pii.py` | Applies deterministic private-identifier patterns |
| Taxonomy | `src/corpus_privacy_intelligence/taxonomy.py` | Defines public topic families and sensitive-domain terms |
| Classifier | `src/corpus_privacy_intelligence/classifier.py` | Routes each unit into public, private, or low-signal queues |
| Pipeline | `src/corpus_privacy_intelligence/pipeline.py` | Coordinates scanning, chunk recovery, classification, and summaries |
| Reports | `src/corpus_privacy_intelligence/reports.py` | Writes Markdown and JSON artifacts |
| Validators | `src/corpus_privacy_intelligence/validators.py` | Three independent detectors and the majority vote between them |
| Validation run | `src/corpus_privacy_intelligence/validation.py` | Cross-detector comparison and disagreement export |
| Advanced detectors | `src/corpus_privacy_intelligence/advanced_detectors.py` | Detector wrappers, including the optional Presidio and spaCy paths |
| Advanced validation | `src/corpus_privacy_intelligence/advanced_validation.py` | Weighted ensemble comparison across all five detectors |
| Local review pass | `src/corpus_privacy_intelligence/ollama_validation.py` | Optional local-only re-check of saved disagreement cases |

## Routing Decisions

Rules are evaluated in strict precedence order; the first match wins, and every unit receives exactly one decision.

| Order | Queue | Condition |
| ---: | --- | --- |
| 1 | `exclude_private_identifier` | A direct private identifier was detected |
| 2 | `exclude_sensitive_domain` | A sensitive-domain term matched the body, or a sensitive term appeared in the title |
| 3 | `skip_low_signal` | No public topic matched, or fewer than 10 tokens survived normalization |
| 4 | `public_candidate` | Everything else |

`pipeline.run_pipeline` then applies `--min-public-score` as a release gate. A `public_candidate` scoring below the threshold is demoted to the low-signal queue rather than dropped, so nothing leaves the accounting.

## Reconciliation Invariant

```text
units_scanned == public_candidate_units + excluded_units + skipped_units
```

The invariant holds structurally in `run_pipeline`: each unit increments the counter once and is appended to exactly one queue. It is written into every run's `scan_summary.json`, and it is enforced on the recorded run by `scripts/check_published_numbers.py`, which CI executes on every push. The same script asserts that each validator's label counts also account for the whole corpus, and that the policy classifier's counts equal the pipeline's own.

## Chunk Recovery

The scanner evaluates full conversations first. If a full conversation is excluded, the pipeline re-unitizes that conversation at `--chunk-chars` granularity and routes each chunk through the identical classifier call. This prevents one sensitive section from discarding unrelated safe technical content in a long thread. Chunk fan-out happens only on the exclusion branch, so a clean conversation costs one classification rather than many. Chunks are built from whole messages, so a single oversized message produces a chunk larger than the target size.

## Validation Layer

The advanced validation path is intentionally separate from the production policy. It is used to compare classifier behavior against additional free NLP detectors and identify disagreement rows for review.

Optional detectors:

- Microsoft Presidio;
- spaCy;
- strict rule detector;
- semantic token-family scorer.

Unavailable optional detectors are reported as unavailable rather than treated as passing signals.
