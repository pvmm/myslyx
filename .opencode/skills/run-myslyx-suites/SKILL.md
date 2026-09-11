---
name: run-myslyx-suites
description: Use when running or debugging Myslyx acceptance suites via the repo's debug runner. Triggers on "run the tests", "run suite", "run smoke/fold/multiedit/header/plugins suite", "debug <suite>", "-f <filter>", "verify the suites". Always prefer ./tests/debug_suite.py over ad-hoc Playwright scripts.
---

# Running Myslyx acceptance suites

Always use the shared debug runner `./tests/debug_suite.py` (the project's
single testing entry point) instead of writing throwaway Playwright scripts or
starting the server manually. It handles server launch on a free port, browser
setup, per-suite resets, and full cleanup (browser close, server force-kill,
and killing orphan test browsers), so nothing lingers after a run.

## Invocation

```bash
PYTHONPATH=. timeout 600 .venv/bin/python tests/debug_suite.py [-f <filter>...] [-b firefox|chromium]
```

- `-f <filter>` selects suites whose registered name contains the filter
  (case-insensitive substring over the suite name, e.g. `fold`, `lang-combo`,
  `multiedit`, `settings`). Multiple filters may be given.
- No `-f` runs every suite in `ALL_SUITES` (from `tests/runner.py`).
- `-b firefox` runs Firefox (default: chromium). Prefer chromium unless the
  change targets Firefox-specific behaviour.
- The last line of output prints `console errors:` collected from the page;
  an empty list is the expected clean result.

## Behaviour

- Each suite runs in its own freshly-reset editor page (`?reset=1`), reusing
  one browser instance. Per-suite console errors are collected and printed at
  the end; a run is considered green only when every `PASS`ed suite also ends
  with `console errors: []`.
- The runner owns everything it starts: it always closes the browser and
  context, force-kills the server if `terminate()` stalls, and sweeps away any
  lingering test browser (processes whose argv contains a localhost test URL,
  i.e. leftover headless firefox/chromium) — the user's own browser is never
  touched. Do not start your own server or browser for tests; do not `pkill
  -f firefox` (that also kills the user's GUI Firefox).
- Run a single narrow filter while debugging; prefer that over the full suite
  on every iteration.

## Adding a suite

1. Write `async def <name>(page, msgs)` in `tests/test_*.py` following the
   existing helpers in `tests/helpers.py` (use poll-based waits via
   `wait_for_function`; avoid fixed `wait_for_timeout` settles).
2. Register it in the suite list of that module (e.g. `SMOKE_SUITES` in
   `tests/test_smoke.py`).
3. Verify with `-f <suite-name>` so it passes in isolation before committing.