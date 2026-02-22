# GPT_Atomic.md Lean Refactor Runbook

## Objective
Refactor WolfpackTrend into a cleaner, modular architecture that improves onboarding and isolated logic changes while preserving behavior.

This version is intentionally lean for the current codebase size and avoids over-engineering.

## Non-Negotiable Constraints
1. Keep `main.py` as the QC composition root (`Dow30TrendAlgorithm`).
2. Keep `models/__init__.py` exports unchanged.
3. Keep strategy invariants in `AGENTS.md` unchanged.
4. Keep ObjectStore keys and CSV schemas unchanged.
5. Use direct method calls (no event bus).
6. Keep `PortfolioLogger` as one public facade.

## Lean Target Structure
Do not use deep atomic layers. Use a practical 3-layer split:

```text
core/
  alpha/
  portfolio/
  execution/
  shared/
templates/
tools/parity/
```

Guidance:
- `core/shared`: dataclasses, constants, tiny helpers.
- `core/alpha|portfolio|execution`: subsystem rules + stateful engine logic.
- `models/*.py`: QC adapters/wrappers during migration (and compatibility thereafter).

## Backtest Artifact Storage (In-Project)
All run artifacts live under:

`backtests/atomic_refactor/`

Per run:
- `objectstore/` -> downloaded CSV outputs
- `metrics/` -> computed parity summaries and comparison results

Example naming:
- `phase_00_baseline`
- `phase_01_parity_tooling`
- `phase_02_alpha`
- `phase_03_portfolio`
- `phase_04_execution`
- `phase_05_finalize`

---

## Phase 00 — Baseline Capture (Cloud)
Purpose: establish authoritative baseline.

```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python -m py_compile main.py models/*.py
mkdir -p backtests/atomic_refactor/phase_00_baseline/objectstore
mkdir -p backtests/atomic_refactor/phase_00_baseline/metrics

cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic-P00-Baseline-$(date +%Y%m%d-%H%M%S)"

lean cloud object-store get \
  wolfpack/daily_snapshots.csv \
  wolfpack/positions.csv \
  wolfpack/signals.csv \
  wolfpack/slippage.csv \
  wolfpack/trades.csv \
  wolfpack/targets.csv \
  wolfpack/order_events.csv \
  --destination-folder "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtests/atomic_refactor/phase_00_baseline/objectstore"
```

---

## Phase 01 — Build Parity Tooling (Local + Cloud Verify)
Purpose: remove hidden dependency by building parity tooling first.

Deliverables:
1. `tools/parity/metrics_from_csv.py`
2. `tools/parity/hash_manifest.py`
3. `tools/parity/compare_metrics.py`

Minimum outputs from `metrics_from_csv.py`:
- final return
- max drawdown
- turnover (daily + aggregate)
- slippage (daily + aggregate)
- exposure paths (`gross/net/long/short`)
- row counts for all 7 CSV files

Also compute baseline summaries now:

```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python tools/parity/metrics_from_csv.py \
  --input-dir backtests/atomic_refactor/phase_00_baseline/objectstore \
  --output backtests/atomic_refactor/phase_00_baseline/metrics/summary.json

python tools/parity/hash_manifest.py \
  --input-dir backtests/atomic_refactor/phase_00_baseline/objectstore \
  --output backtests/atomic_refactor/phase_00_baseline/metrics/hash_manifest.json
```

Cloud run for tooling validation (no intended behavior change):
- `phase_01_parity_tooling`
- compare to baseline using policy below.

---

## Parity Policy (Practical, Not Fragile)

### Exact-match required
1. CSV file presence and row counts.
2. Date index alignment for all path metrics.
3. Symbol set alignment where applicable.
4. Categorical fields used for execution tier/cycle analysis.

### Tolerance-based match for floats
Default tolerances (absolute):
- Return, drawdown, exposures: `1e-8`
- Turnover and slippage aggregates: `1e-6`
- Path values (daily): `1e-8`

Rounding policy:
- Normalize inputs to fixed decimal precision before compare:
  - exposures/returns/drawdown paths: 10 decimals
  - turnover/slippage values: 8 decimals

`compare_metrics.py` should support:
- `--mode exact` (for diagnostics)
- `--mode tolerant` (default gate mode for this refactor)

Gate rule:
- Phase passes only if tolerant compare passes and no exact-match required fields fail.

---

## Phase 02 — Alpha Refactor (Single Major Phase)
Purpose: refactor alpha internals in one pass instead of atom/molecule/organism micro-phases.

Scope:
1. Move pure alpha calculations into `core/alpha/` helpers.
2. Introduce alpha state dataclass in `core/shared/`.
3. Keep `models/alpha.py` as QC adapter delegating to core logic.
4. Preserve:
   - 20/63/252 + ATR model
   - all-horizons-agree rule
   - `tanh(score / 3.0)` behavior
   - 5-trading-day recalc + daily emissions

Validation:
- local compile/smoke
- one cloud backtest: `phase_02_alpha`
- parity compare vs baseline.

---

## Phase 03 — Portfolio Refactor (Single Major Phase)
Purpose: refactor portfolio construction internals in one pass.

Scope:
1. Move target computation and scaling helpers into `core/portfolio/`.
2. Introduce portfolio state dataclass in `core/shared/`.
3. Keep `models/portfolio.py` as QC adapter.
4. Preserve:
   - 10% vol target behavior
   - constraint order: per-name -> gross -> net
   - 5-trading-day scaling semantics
   - `current_week_id`, `week_plan`, stale-cancel timing

Validation:
- local compile/smoke
- one cloud backtest: `phase_03_portfolio`
- parity compare vs baseline.

---

## Phase 04 — Execution Refactor (Single Major Phase)
Purpose: refactor execution internals in one pass.

Scope:
1. Move tiering, limit price, tag parsing/formatting, cancellation checks to `core/execution/`.
2. Introduce execution state dataclass in `core/shared/`.
3. Keep `models/execution.py` as QC adapter.
4. Preserve:
   - tier thresholds/offsets
   - exits as market orders
   - week_id cycle cancellation + legacy fallback

Validation:
- local compile/smoke
- one cloud backtest: `phase_04_execution`
- parity compare vs baseline.

---

## Phase 05 — Finalize and Clean Composition
Purpose: finalize structure, templates, and docs without behavior change.

Scope:
1. Add `templates/strategy_config.py` and wire `main.py` to read defaults.
2. Ensure `main.py` remains clean composition root.
3. Keep logger facade stable (`models/logger.py`).
4. Final cleanup of imports and adapter boundaries.

Validation:
- local compile/smoke
- one cloud backtest: `phase_05_finalize`
- parity compare vs baseline.

---

## Standard Per-Phase Commands
Use for phases `01` through `05`:

```bash
# Local
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python -m py_compile main.py models/*.py core/**/*.py templates/*.py tools/parity/*.py
mkdir -p backtests/atomic_refactor/phase_XX_NAME/objectstore
mkdir -p backtests/atomic_refactor/phase_XX_NAME/metrics

# Cloud
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic-PXX-NAME-$(date +%Y%m%d-%H%M%S)"

lean cloud object-store get \
  wolfpack/daily_snapshots.csv \
  wolfpack/positions.csv \
  wolfpack/signals.csv \
  wolfpack/slippage.csv \
  wolfpack/trades.csv \
  wolfpack/targets.csv \
  wolfpack/order_events.csv \
  --destination-folder "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtests/atomic_refactor/phase_XX_NAME/objectstore"

# Metrics + compare
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python tools/parity/metrics_from_csv.py \
  --input-dir backtests/atomic_refactor/phase_XX_NAME/objectstore \
  --output backtests/atomic_refactor/phase_XX_NAME/metrics/summary.json

python tools/parity/hash_manifest.py \
  --input-dir backtests/atomic_refactor/phase_XX_NAME/objectstore \
  --output backtests/atomic_refactor/phase_XX_NAME/metrics/hash_manifest.json

python tools/parity/compare_metrics.py \
  --baseline backtests/atomic_refactor/phase_00_baseline/metrics/summary.json \
  --candidate backtests/atomic_refactor/phase_XX_NAME/metrics/summary.json \
  --mode tolerant
```

---

## Rollback and Recovery Strategy (Explicit)
Use phase-scoped commits and tags.

Per phase:
1. Start phase branch or stay on one refactor branch with phase commits.
2. Commit once phase code is done (before cloud run).
3. If phase parity fails:
   - `git revert <phase_commit_sha>`
   - fix forward in a new commit
   - rerun same phase until parity passes
4. Tag successful phase commits:
   - `git tag atomic-phase-XX-pass`

Recommended model:
- Branch: `refactor/atomic-lean`
- Commits: `phase-01`, `phase-02`, ... `phase-05`
- Tags: `atomic-phase-01-pass`, etc.

---

## Cloud Backtest Budget
This lean plan targets ~6 cloud runs total:
1. Baseline (Phase 00)
2. Phase 01 parity tooling verify
3. Phase 02 alpha
4. Phase 03 portfolio
5. Phase 04 execution
6. Phase 05 finalize

Use additional runs only when a phase fails parity and needs re-test.

---

## Completion Criteria
Refactor is complete when:
1. All phase gates pass.
2. Required exact-match fields are unchanged.
3. Tolerant parity checks pass for all float metrics and paths.
4. Strategy invariants remain intact.
5. ObjectStore keys and schemas remain unchanged.
6. `main.py` is clean composition root with isolated subsystem logic.
