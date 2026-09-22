# Validation

## Test Commands

```powershell
python -m pytest -q
python -m compileall src tests
```

86 tests. Every fixture is synthetic; no corpus text is committed to this repository.

## Continuous Integration

`.github/workflows/ci.yml` runs three jobs on Python 3.11 for every push and every pull request into `main`:

1. Lint: `ruff check .` and `ruff format --check .`, pinned to ruff 0.8.6.
2. Tests: `pip install -e ".[dev]"` then `python -m pytest -q`, from a clean clone.
3. Published claims: `scripts/check_published_numbers.py` asserts the recorded aggregates reconcile and match this documentation set, and `scripts/export_page_snippets.py` asserts the code shown on the project page still exists verbatim in `src/`.

## Covered Behaviors

The suite covers, per module:

- every direct-identifier category, with a test asserting no pattern ships untested;
- the three full-corpus validators and the majority vote between them;
- the weighted ensemble router, including that privacy overrides a public majority and that a
  detector which could not run does not tilt the route;
- synthetic privacy fixtures: ten cases that must never reach public output, three legitimate
  public near-misses, and a check that a classification never republishes the identifier it
  excluded on.

## Regression Gate

`tests/test_privacy_fixtures.py` is the policy gate. It caught a real calibration defect: the
bare tokens `health`, `lab`, `sleep`, `weight` and `pain` in `private_health` were excluding
ordinary engineering vocabulary such as "health check", "home lab", "sleep mode", "weight
matrix" and "pain point". Those terms are now matched as phrases, and both directions are
pinned: the engineering homonyms must stay available, and the same words in a genuine health
context must stay excluded.

## Policy Review Areas

When changing classifier behavior, add fixtures for:

- one hard-private example;
- one sensitive-domain example;
- one legitimate public example from a nearby vocabulary;
- one borderline example that should remain low signal or review-only.

This keeps broad terms such as finance, technology, health, or immigration from becoming accidental blanket filters.
