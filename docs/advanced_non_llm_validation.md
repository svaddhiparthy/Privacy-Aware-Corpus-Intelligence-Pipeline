# Advanced Free Non-LLM Validation

This layer adds mature free NLP tooling around the original local classifier.

## Detectors

- `policy`: the production routing classifier.
- `strict_detector`: direct identifier and sensitive-domain patterns.
- `semantic_score_classifier`: independent token-family scorer.
- `presidio`: Microsoft Presidio analyzer with custom recognizers.
- `spacy`: spaCy NER and identifier/context checks.

## Why This Exists

The first version relied mostly on custom rules. The advanced validation layer adds independent checks by comparing the custom classifier against established free NLP libraries.

## Current Ensemble Policy

The ensemble uses weighted votes:

- Presidio receives the highest detector weight because it is purpose-built for PII analysis.
- The production policy remains part of the vote, but it is no longer the only signal.
- Direct private identifiers and sensitive-domain matches are treated as strong private signals.
- Person and location entities from NER are treated as review signals, not automatic private blocks. This matters because public figures, company names, and place names can be legitimate public content.

## Outputs

The advanced validation command writes:

- `advanced_validation_results.json`
- `advanced_validation_summary.json`
- `advanced_validation_report.md`

## Example Command

```powershell
python -m corpus_privacy_intelligence.advanced_validation `
  --export-dir "C:\path\to\export" `
  --out-dir "outputs\advanced_validation" `
  --chunk-chars 9000 `
  --limit 300
```

Use `--limit 0` for a full run. A full run with Presidio and spaCy can be slow on CPU.

## Current Bounded Result

The first calibrated sample used 300 units:

| Detector | Public | Private | Review |
|---|---:|---:|---:|
| policy | 179 | 121 | 0 |
| strict_detector | 120 | 108 | 72 |
| semantic_score_classifier | 154 | 111 | 35 |
| presidio | 86 | 54 | 160 |
| spacy | 49 | 55 | 196 |

Ensemble:

| Label | Count |
|---|---:|
| public | 144 |
| private | 111 |
| review | 45 |

## Calibration Notes

The first Presidio pass was too aggressive because generic `PERSON` and `LOCATION` entities were treated as hard private findings. That was corrected. They now route to review only when repeated, while hard private entities and custom sensitive recognizers still route private.

This makes the detector safer for public figures, places, products, movie names, vehicle names, and general technical content.

