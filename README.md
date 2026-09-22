# Privacy-Aware Corpus Intelligence Pipeline

[![CI](https://github.com/Vaddhiparthy/Privacy-Aware-Corpus-Intelligence-Pipeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Vaddhiparthy/Privacy-Aware-Corpus-Intelligence-Pipeline/actions/workflows/ci.yml)

**Live:** [vaddhiparthy.com/Privacy-Aware-Corpus-Intelligence-Pipeline](https://vaddhiparthy.com/Privacy-Aware-Corpus-Intelligence-Pipeline)

This repository implements a local-first classification pipeline for large text exports that contain a mix of reusable knowledge and sensitive personal material.

## Implemented System

| Capability | Implementation |
| --- | --- |
| Split-export ingestion | Streams `conversations-*.json` files from a local export directory |
| Chunk recovery | Evaluates full conversations and smaller chunks so safe sections can be recovered from mixed threads |
| Private identifier detection | Deterministic checks for SSN-like strings, emails, phones, cards, addresses, and token-like values |
| Sensitive-domain routing | Excludes private health, immigration, resume, recruiter, interview, salary, and job-search material |
| Public topic classification | Scores retained content into explicit topic families with term evidence |
| Text signatures | Normalized terms, stopword removal, light stemming, and term-frequency metadata |
| Output artifacts | Writes Markdown review catalogs and JSON machine-readable outputs |
| Optional validation | Compares the policy classifier against strict rules, semantic scoring, Presidio, and spaCy when optional packages are installed |

## Processing Flow

```text
Local text export
  -> JSON conversation reader
  -> conversation and chunk units
  -> deterministic identifier checks
  -> sensitive-domain policy
  -> public-topic scoring
  -> public / private / low-signal output queues
  -> Markdown and JSON reports
```

The pipeline keeps raw private text local. It does not send the corpus to a hosted LLM or remote embedding service.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `src/corpus_privacy_intelligence/__init__.py` | Package marker and version string |
| `src/corpus_privacy_intelligence/cli.py` | Command-line entry point for the main scan |
| `src/corpus_privacy_intelligence/reader.py` | Reads split JSON exports and builds text units |
| `src/corpus_privacy_intelligence/models.py` | `CorpusUnit` and `Classification` dataclasses |
| `src/corpus_privacy_intelligence/text.py` | Tokenization, stopwords, light stemming, and term counts |
| `src/corpus_privacy_intelligence/pii.py` | Detects hard private identifiers |
| `src/corpus_privacy_intelligence/taxonomy.py` | Public topic families and sensitive-domain terms |
| `src/corpus_privacy_intelligence/classifier.py` | Policy classifier and routing decisions |
| `src/corpus_privacy_intelligence/pipeline.py` | End-to-end scan orchestration |
| `src/corpus_privacy_intelligence/reports.py` | Markdown and JSON output writers |
| `src/corpus_privacy_intelligence/validators.py` | Independent strict, policy, and term-based detector functions |
| `src/corpus_privacy_intelligence/validation.py` | Cross-detector validation run and disagreement export |
| `src/corpus_privacy_intelligence/advanced_validation.py` | Optional multi-detector validation run |
| `src/corpus_privacy_intelligence/advanced_detectors.py` | Policy, strict, semantic, Presidio, and spaCy detector wrappers |
| `src/corpus_privacy_intelligence/ollama_validation.py` | Optional local-LLM check of saved disagreement cases |
| `tests/` | Classifier regression tests |
| `docs/` | Architecture and validation notes |

## Install

Core pipeline:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Optional validation packages:

```powershell
python -m pip install -e ".[nlp]"
```

The optional packages are not required for the main classifier.

## Run

```powershell
python -m corpus_privacy_intelligence.cli `
  --export-dir "C:\path\to\export" `
  --out-dir "C:\path\to\outputs" `
  --min-public-score 55 `
  --chunk-chars 9000
```

Expected input files are named like:

```text
conversations-000.json
conversations-001.json
```

## Outputs

| Output | Purpose |
| --- | --- |
| `public_candidates.md` | Reviewable public-safe candidates |
| `public_candidates.json` | Machine-readable public-safe rows with topic and term metadata |
| `excluded_private.md` | Excluded units with reasons |
| `excluded_private.json` | Machine-readable private exclusions |
| `skipped_low_signal.json` | Low-signal rows retained for audit |
| `topic_summary.md` | Topic counts and review schedule |
| `scan_summary.json` | Run-level counts, topic counts, exclusion counts, and identifier counts |

## Policy

Default exclusions:

- SSN-like identifiers;
- email addresses and phone numbers;
- card-like digit sequences;
- API key and token-like strings;
- identity-document context;
- street-address context;
- private health context;
- immigration and visa context;
- resume, recruiter, interview, salary, employer, and job-search context.

Default retainable categories include technical tutorials, infrastructure notes, software automation, AI systems, product research, general finance explainers, vehicle research, learning material, creative ideas, and philosophy.

## Advanced Validation

The optional validation command compares the primary policy with independent detectors:

```powershell
python -m corpus_privacy_intelligence.advanced_validation `
  --export-dir "C:\path\to\export" `
  --out-dir "outputs\advanced_validation" `
  --limit 300
```

Outputs:

- `advanced_validation_results.json`
- `advanced_validation_summary.json`
- `advanced_validation_report.md`

Presidio and spaCy are optional. If they are unavailable, the validation runner records them as unavailable instead of pretending they ran.

### Optional Ollama Disagreement Validation

When the independent detectors disagree, `validation.py` records those cases to `automated_validation_disagreements.json`. The optional `ollama_validation` command re-checks each saved disagreement with a local Ollama model so a second semantic opinion can be compared against the local majority label. This stays fully local: it calls a model running on `127.0.0.1` and never sends the corpus to a hosted service.

```powershell
python -m corpus_privacy_intelligence.ollama_validation `
  --input "outputs\validation\automated_validation_disagreements.json" `
  --out-dir "outputs\ollama_validation" `
  --model "llama3.2:3b" `
  --host "http://127.0.0.1:11434" `
  --limit 50
```

Outputs:

- `ollama_validation_results.json`
- `ollama_validation_summary.json`
- `ollama_validation_report.md`

Each row records the local majority label, the Ollama label and confidence, and whether the two agree. The run resumes from existing results, so already-classified `unit_id` values are skipped. Ollama is an extra local semantic check, not a source of truth on its own. If the model is unreachable the item is marked `review` with the error reason instead of failing the run.

## Validation

```powershell
python -m pytest -q
python -m compileall src tests
```

## Privacy Notes

- Run against local exports only.
- Do not commit raw exports or generated output directories.
- Treat `public_candidates` as a review queue, not an automatic publishing decision.
- Keep policy changes explicit in `taxonomy.py`, `pii.py`, and classifier tests.
