# Operations

This project is designed for local execution against private text exports.

## Core Run

```powershell
python -m corpus_privacy_intelligence.cli `
  --export-dir "C:\path\to\export" `
  --out-dir "C:\path\to\outputs" `
  --min-public-score 55 `
  --chunk-chars 9000
```

The installed console script `corpus-privacy-intelligence` takes the same flags.

| Flag | Default | Effect |
| --- | --- | --- |
| `--export-dir` | required | Directory holding `conversations-*.json` |
| `--out-dir` | required | Created if absent; receives all seven artifacts |
| `--min-public-score` | `55.0` | Release gate; below it a candidate is demoted to low signal |
| `--chunk-chars` | `9000` | Target chunk size on the recovery path |

## Run Checks

Each run writes `scan_summary.json`. Before trusting a run, confirm the reconciliation holds:

```text
units_scanned == public_candidate_units + excluded_units + skipped_units
```

`scan_summary.json` is the authoritative count record. `skipped_low_signal.json` is truncated at 2000 rows by design and must not be used for reconciliation.

## Cross-Detector Validation

```powershell
python -m corpus_privacy_intelligence.validation `
  --export-dir "C:\path\to\export" `
  --out-dir "outputs\validation" `
  --chunk-chars 9000 `
  --max-disagreements 500
```

Writes `automated_validation_summary.json`, `automated_validation_disagreements.json`, and `automated_validation_report.md`.

## Output Handling

Generated outputs may contain sensitive previews and should stay outside Git unless deliberately sanitized.

Recommended ignored output locations:

- `outputs/`
- `data/`
- `exports/`
- local review folders outside the repository

## Review Rule

`public_candidates` means "safe enough for human review." It does not mean "publish automatically."

Before publishing derived content, inspect:

- exclusion reasons;
- identifier hits;
- topic scores;
- preview text;
- source conversation title.

## Optional Validation

```powershell
python -m corpus_privacy_intelligence.advanced_validation `
  --export-dir "C:\path\to\export" `
  --out-dir "outputs\advanced_validation" `
  --limit 300
```

Use a bounded `--limit` first when optional NLP packages are installed because Presidio and spaCy can be slow on CPU.
