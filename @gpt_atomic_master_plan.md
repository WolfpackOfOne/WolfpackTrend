# @gpt_atomic_master_plan

## 0. Executive Summary

This document merges `GPT_Atomic.md` and `CC_Atomic.md` into one executable refactor plan.

The plan is intentionally strict about behavior preservation:
- Cloud backtests are authoritative.
- ObjectStore keys and schemas stay unchanged.
- Strategy invariants in `AGENTS.md` stay unchanged.
- Refactor proceeds in small gated phases.

This plan resolves the main conflict between the two analyst plans:
- `GPT_Atomic.md` preference: keep `main.py` as composition root, keep `models/` compatibility, avoid over-engineering.
- `CC_Atomic.md` preference: full domain-grouped atomic architecture and eventual removal of `models/`.

Resolution used here:
1. Mandatory path: complete atomic/domain extraction while preserving compatibility adapters in `models/`.
2. Optional cutover path: remove `models/` only after parity-certified stabilization and explicit approval.

---

## 1. Inputs Consolidated

Primary inputs:
- `GPT_Atomic.md`
- `CC_Atomic.md`
- `AGENTS.md`

Repository context:
- Entrypoint remains `main.py` (`Dow30TrendAlgorithm`).
- Current modules in `models/`: alpha, portfolio, execution, logger, universe.
- Backtest defaults remain:
  - Start: `2022-01-01`
  - End: `2024-01-01`
  - Cash: `100000`
  - Warmup: `252`
  - Benchmark: `SPY`

---

## 2. Non-Negotiable Constraints (Master Set)

These constraints apply to every phase unless explicitly called out as optional in Phase 14.

1. Keep strategy behavior intact:
   - 20/63/252 SMA + ATR normalization.
   - all-horizons-agree signal rule.
   - `tanh(score / 3.0)`.
   - 5-trading-day recalculation cadence + daily emissions.
2. Keep portfolio behavior intact:
   - 10% vol targeting.
   - constraint order: per-name cap, then gross cap, then net cap.
   - scaling remains trading-day based.
3. Keep execution behavior intact:
   - Strong `>= 0.70`, Moderate `>= 0.30`, Weak `< 0.30`.
   - limit offsets unchanged.
   - exits remain market orders.
   - stale cancellation preserves `week_id` cycle behavior, with legacy fallback only when `week_id` unavailable.
4. Keep ObjectStore keys unchanged:
   - `wolfpack/daily_snapshots.csv`
   - `wolfpack/positions.csv`
   - `wolfpack/signals.csv`
   - `wolfpack/slippage.csv`
   - `wolfpack/trades.csv`
   - `wolfpack/targets.csv`
   - `wolfpack/order_events.csv`
5. Keep CSV column schemas and semantic meanings unchanged.
6. Keep `main.py` as composition root.
7. Preserve `PortfolioLogger` public facade API through migration.
8. Do not introduce event bus/pub-sub abstraction.
9. No behavior-changing parameter tweaks during refactor phases.

---

## 3. Unified Target Architecture

Final architecture target from both plans (with compatibility bridge):

```text
WolfpackTrend 1/
  main.py
  core/
    __init__.py
    universe.py
    types.py
    math_utils.py
    formatting.py
  signals/
    __init__.py
    trend.py
    alpha.py
  risk/
    __init__.py
    constraints.py
    vol_estimator.py
    scaling.py
    portfolio.py
  execution/
    __init__.py
    pricing.py
    cancellation.py
    execution.py
  loggers/
    __init__.py
    csv_writer.py
    snapshot_logger.py
    position_logger.py
    signal_logger.py
    slippage_logger.py
    order_event_logger.py
    target_logger.py
    portfolio_logger.py
  models/                     # Compatibility adapters during mandatory path
    __init__.py
    alpha.py
    portfolio.py
    execution.py
    logger.py
    universe.py
  templates/
    strategy_config.py
  tools/
    parity/
      metrics_from_csv.py
      hash_manifest.py
      compare_metrics.py
  backtests/
    atomic_refactor/
      phase_XX_name/
        objectstore/
        metrics/
```

Import policy:
- `core/` is dependency-leaf (no imports from domains).
- Molecules import from `core/` only.
- Organisms import from `core/` + molecules in same domain.
- `main.py` imports only organism-level modules via domain `__init__.py` or compatibility exports.

---

## 4. Delivery Strategy and Stage Model

This master plan uses three stages:

1. Stage A: Baseline + parity tooling + atom extraction + direct wiring in existing models.
2. Stage B: Domain migration (`signals/`, `risk/`, `execution/`, `loggers/`) with compatibility adapters in `models/`.
3. Stage C: Stabilization + typed dataclasses + optional hard cutover removing `models/`.

Why this sequence:
- It captures GPT’s lower-risk sequencing and parity discipline.
- It captures CC’s detailed domain decomposition and future architecture.
- It limits simultaneous changes and makes regressions isolate-able.

---

## 5. Branching, Tags, and Artifact Conventions

Recommended branch:
- `refactor/atomic-master`

Commit format:
- `phase-00: baseline capture`
- `phase-01: parity tooling scaffold`
- ...

Tag format:
- `atomic-phase-00-pass`
- `atomic-phase-01-pass`
- ...

Artifacts:
- `backtests/atomic_refactor/phase_00_baseline/...`
- `backtests/atomic_refactor/phase_01_parity_tooling/...`
- ...

Phase naming map:
- `phase_00_baseline`
- `phase_01_parity_tooling`
- `phase_02_structure_atoms`
- `phase_03_math_extraction`
- `phase_04_formatting_extraction`
- `phase_05_alpha_wiring`
- `phase_06_portfolio_wiring`
- `phase_07_execution_wiring`
- `phase_08_logger_domain`
- `phase_09_signals_domain`
- `phase_10_risk_domain`
- `phase_11_execution_domain`
- `phase_12_composition_finalize`
- `phase_13_typed_dataclasses`
- `phase_14_optional_models_removal`
- `phase_15_final_certification`

---

## 6. Master Phase Gates

Each phase passes only when all conditions below are true:

1. Local compile succeeds:
```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python -m py_compile main.py models/*.py
python -m py_compile core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py tools/parity/*.py
```

2. Cloud run completes:
```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic-PXX-<phase-name>-$(date +%Y%m%d-%H%M%S)"
```

3. ObjectStore artifacts downloaded:
```bash
lean cloud object-store get \
  wolfpack/daily_snapshots.csv \
  wolfpack/positions.csv \
  wolfpack/signals.csv \
  wolfpack/slippage.csv \
  wolfpack/trades.csv \
  wolfpack/targets.csv \
  wolfpack/order_events.csv \
  --destination-folder "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtests/atomic_refactor/phase_XX_name/objectstore"
```

4. Metrics generated:
```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python tools/parity/metrics_from_csv.py \
  --input-dir backtests/atomic_refactor/phase_XX_name/objectstore \
  --output backtests/atomic_refactor/phase_XX_name/metrics/summary.json

python tools/parity/hash_manifest.py \
  --input-dir backtests/atomic_refactor/phase_XX_name/objectstore \
  --output backtests/atomic_refactor/phase_XX_name/metrics/hash_manifest.json
```

5. Parity compare passes:
```bash
python tools/parity/compare_metrics.py \
  --baseline backtests/atomic_refactor/phase_00_baseline/metrics/summary.json \
  --candidate backtests/atomic_refactor/phase_XX_name/metrics/summary.json \
  --mode tolerant
```

6. Exact fields also pass:
- file presence
- row counts
- date index alignment
- symbol set alignment where applicable
- categorical cycle/tier fields

Float tolerances:
- return/drawdown/exposures path: `1e-8`
- turnover/slippage aggregates: `1e-6`
- normalization rounding:
  - path metrics: 10 decimals
  - turnover/slippage metrics: 8 decimals

---

## 7. Detailed Execution Plan

### Phase 00: Baseline Capture (Authoritative)

Objective:
- Freeze an authoritative behavioral baseline from the current code.

Scope:
- No refactor code changes.
- Build baseline artifacts and metrics.

Execution:
1. Validate baseline compiles.
2. Create baseline artifact directories.
3. Run cloud backtest with baseline label.
4. Download all seven ObjectStore files.
5. Compute baseline summary and baseline hash manifest.
6. Save run metadata (`backtest id`, timestamp, git SHA).

Commands:
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
```

Then:
```bash
lean cloud object-store get \
  wolfpack/daily_snapshots.csv \
  wolfpack/positions.csv \
  wolfpack/signals.csv \
  wolfpack/slippage.csv \
  wolfpack/trades.csv \
  wolfpack/targets.csv \
  wolfpack/order_events.csv \
  --destination-folder "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtests/atomic_refactor/phase_00_baseline/objectstore"

cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python tools/parity/metrics_from_csv.py \
  --input-dir backtests/atomic_refactor/phase_00_baseline/objectstore \
  --output backtests/atomic_refactor/phase_00_baseline/metrics/summary.json
python tools/parity/hash_manifest.py \
  --input-dir backtests/atomic_refactor/phase_00_baseline/objectstore \
  --output backtests/atomic_refactor/phase_00_baseline/metrics/hash_manifest.json
```

Exit criteria:
- Baseline summary exists.
- Baseline hash exists.
- Baseline run metadata recorded.

Commit:
- `phase-00: baseline capture artifacts and baseline metrics`

---

### Phase 01: Build and Validate Parity Tooling

Objective:
- Implement parity tooling before major refactor edits.

Deliverables:
- `tools/parity/metrics_from_csv.py`
- `tools/parity/hash_manifest.py`
- `tools/parity/compare_metrics.py`

Required metrics in summary:
- final return
- max drawdown
- daily and aggregate turnover
- daily and aggregate slippage
- exposure paths (`gross`, `net`, `long`, `short`)
- row counts for all seven CSV files

Implementation notes:
- Tolerant mode is default.
- Exact mode exists for diagnostics.
- Script outputs should be deterministic (stable key order and rounding policy).

Execution:
1. Create/implement scripts.
2. Run scripts on phase 00 artifacts.
3. If needed, run a no-behavior-change cloud verification run.
4. Validate compare script can fail/pass correctly against known modified samples.

Exit criteria:
- `compare_metrics.py --mode tolerant` returns pass against identical datasets.
- `compare_metrics.py --mode exact` catches exact mismatch cases.

Commit:
- `phase-01: parity tooling with tolerant and exact compare modes`

---

### Phase 02: Create Atomic Directory Skeleton and Core Atoms

Objective:
- Introduce directory skeleton and initial atoms without touching runtime wiring.

Deliverables:
- `core/`, `signals/`, `risk/`, `execution/`, `loggers/`
- `core/universe.py`
- `core/types.py`
- `core/math_utils.py` (stub)
- `core/formatting.py` (stub)
- domain `__init__.py` files

Rules:
- Runtime imports in `main.py` remain unchanged.
- Existing `models/` behavior untouched.
- No strategy logic migration yet.

`core/types.py` initial dataclasses:
- `Signal`
- `TargetState`
- `OrderRecord`
- `TradeRecord`
- `PositionSnapshot`
- `SlippageRecord`
- `OrderEventRecord`

Exit criteria:
- New directories/files exist and compile.
- Cloud parity unchanged.

Commit:
- `phase-02: directory skeleton and core atom stubs`

---

### Phase 03: Extract Pure Math to `core/math_utils.py`

Objective:
- Centralize pure math and deterministic decision helpers.

Functions to implement:
- `build_scaling_schedule(scaling_days, front_load_factor)`
- `estimate_portfolio_vol(weights, rolling_returns, min_obs)`
- `apply_per_name_cap(weights, max_weight)`
- `apply_gross_cap(weights, max_gross)`
- `apply_net_cap(weights, max_net)`
- `compute_limit_price(price, quantity, offset_pct, tick_size)`
- `compute_composite_signal(price, sma_short, sma_medium, sma_long, atr_value, weights, temperature, min_magnitude)`

Placement note:
- `extract_week_id_from_tag(tag)` ultimately belongs in formatting, not math.
- If initially added in math, move in Phase 04.

Purity rules:
- no `self`
- no `algorithm`
- no QuantConnect runtime objects
- plain inputs and plain outputs only

Behavior-critical implementation notes:
- preserve ATR clamp: `max(atr_value, 1e-8)`
- preserve existing rounding behavior where currently used
- preserve schedule terminal constraint: `schedule[-1] = 1.0`

Exit criteria:
- Functions implemented with docstrings.
- Existing models still function unchanged.
- Cloud parity unchanged.

Commit:
- `phase-03: extract pure math utilities to core`

---

### Phase 04: Extract Formatting and Parsing Utilities to `core/formatting.py`

Objective:
- Centralize formatting/parsing helpers used by execution/logger.

Functions:
- `build_csv(data, columns)`
- `build_order_tag(tier, signal_strength, week_id, scale_day)`
- `extract_week_id_from_tag(tag)`

Rules:
- pure functions only
- no QC imports
- deterministic output for same inputs

Behavior notes:
- Tag format must remain parse-compatible with existing logs.
- CSV output must preserve existing column order and formatting semantics.

Exit criteria:
- formatting helpers are present and tested via parity workflow.
- no behavior change in cloud parity.

Commit:
- `phase-04: extract formatting helpers to core/formatting`

---

### Phase 05: Wire Alpha Model to Core Utilities

Objective:
- Replace inline alpha math with `core/math_utils` calls while preserving output.

Primary file:
- `models/alpha.py`

Required changes:
1. Import `compute_composite_signal`.
2. Replace inline composite-score block with call to utility.
3. Keep class signature and LEAN interfaces unchanged:
   - `Update()`
   - `OnSecuritiesChanged()`
4. Keep coupling points unchanged:
   - cached signal behavior
   - rebalance/day emission behavior
   - logger signal events

Guardrails:
- Preserve direction and magnitude signs exactly.
- Preserve no-signal conditions exactly.

Exit criteria:
- same number/timing/content of emitted signals under parity constraints.
- cloud parity unchanged.

Commit:
- `phase-05: wire models/alpha to core composite signal utility`

---

### Phase 06: Wire Portfolio Model to Core Utilities

Objective:
- Move vol/constraints/schedule logic consumption to `core/math_utils`.

Primary file:
- `models/portfolio.py`

Required changes:
1. Import:
   - `build_scaling_schedule`
   - `estimate_portfolio_vol`
   - `apply_per_name_cap`
   - `apply_gross_cap`
   - `apply_net_cap`
2. Replace schedule initialization calls with core utility.
3. Convert `RollingWindow` objects to plain lists before calling `estimate_portfolio_vol`.
4. Keep compatibility wrapper for `_estimate_portfolio_vol` until logger domain migration is complete.
5. Replace internal cap functions with utility calls.
6. Remove now-duplicate private cap/schedule methods.

Behavior guardrails:
- constraint application order remains unchanged.
- scaling semantics remain trading-day based.
- `current_week_id`, `week_plan`, and public fields used by other models remain intact.

Exit criteria:
- cloud parity unchanged.
- no duplicated math logic except temporary compatibility wrapper.

Commit:
- `phase-06: wire models/portfolio to core vol and constraint utilities`

---

### Phase 07: Wire Execution Model to Core Utilities

Objective:
- Move pricing/tag parsing/formatting usage to core helpers.

Primary file:
- `models/execution.py`

Required changes:
1. Import:
   - `compute_limit_price` from `core.math_utils`
   - `build_order_tag`, `extract_week_id_from_tag` from `core.formatting`
2. Replace internal limit price computation calls.
3. Replace internal tag builder calls, with explicit `week_id` and `scale_day` lookup at call site.
4. Replace internal `week_id` parser calls.
5. Remove duplicated private helper implementations.

Behavior guardrails:
- tier thresholds and offsets unchanged.
- stale order cancellation logic unchanged.
- market exits unchanged.

Exit criteria:
- cloud parity unchanged.
- no duplicated execution utility logic remains.

Commit:
- `phase-07: wire models/execution to core pricing and formatting utilities`

---

### Phase 08: Split Logger into `loggers/` Domain with Facade

Objective:
- Decompose large logger into focused sub-loggers while preserving public interface.

New files:
- `loggers/csv_writer.py`
- `loggers/snapshot_logger.py`
- `loggers/position_logger.py`
- `loggers/signal_logger.py`
- `loggers/slippage_logger.py`
- `loggers/order_event_logger.py`
- `loggers/target_logger.py`
- `loggers/portfolio_logger.py`

Compatibility bridge:
- `models/logger.py` becomes thin re-export:
```python
from loggers.portfolio_logger import PortfolioLogger
```

Public API preservation requirements:
- `PortfolioLogger.log_daily(...)`
- `PortfolioLogger.log_signal(...)`
- `PortfolioLogger.log_slippage(...)`
- `PortfolioLogger.log_order_event(...)`
- `PortfolioLogger.save_to_objectstore(...)`
- properties expected by `main.py` and other models

Behavior guardrails:
- same keys, same columns, same row generation timing.
- same close-detection semantics for trades.

Exit criteria:
- cloud parity unchanged.
- facade remains drop-in compatible.

Commit:
- `phase-08: split logger into sub-loggers with preserved facade`

---

### Phase 09: Create `signals/` Domain and Alpha Organism

Objective:
- Move alpha organism into `signals/` with extracted trend molecule.

New files:
- `signals/trend.py`
- `signals/alpha.py`

Transition:
1. Implement signal computation molecule.
2. Implement alpha organism wrapper using molecule and core utilities.
3. Keep `models/alpha.py` as re-export:
```python
from signals.alpha import CompositeTrendAlphaModel
```

Behavior guardrails:
- same insight cadence and directions.
- same coupling with PCM rebalance markers.

Exit criteria:
- cloud parity unchanged.
- `signals/__init__.py` exports organism.

Commit:
- `phase-09: create signals domain with trend molecule and alpha organism`

---

### Phase 10: Create `risk/` Domain and Portfolio Organism

Objective:
- Move portfolio organism into risk domain with molecule split.

New files:
- `risk/constraints.py`
- `risk/vol_estimator.py`
- `risk/scaling.py`
- `risk/portfolio.py`

Transition:
1. Create molecule abstractions for constraints, vol tracking, and scaling plan logic.
2. Implement portfolio organism using these molecules.
3. Keep `models/portfolio.py` as re-export:
```python
from risk.portfolio import TargetVolPortfolioConstructionModel
```

Behavior guardrails:
- same target generation and scale progression.
- same public attributes used cross-model (`signal_strengths`, `current_week_id`, `expected_prices`).

Exit criteria:
- cloud parity unchanged.
- risk organism/molecules compile and are import-clean.

Commit:
- `phase-10: create risk domain with portfolio organism and molecules`

---

### Phase 11: Create `execution/` Domain and Execution Organism

Objective:
- Move execution organism into execution domain with pricing/cancellation molecules.

New files:
- `execution/pricing.py`
- `execution/cancellation.py`
- `execution/execution.py`

Transition:
1. Implement tier classification + offset logic molecule.
2. Implement cancellation decision molecule (signal-aware and legacy branches).
3. Implement execution organism using molecules.
4. Keep `models/execution.py` as re-export:
```python
from execution.execution import SignalStrengthExecutionModel
```

Behavior guardrails:
- preserve week-aware cancellation priority.
- legacy checks execute only when week_id unavailable.

Exit criteria:
- cloud parity unchanged.
- execution domain import graph has no cycles.

Commit:
- `phase-11: create execution domain with pricing and cancellation molecules`

---

### Phase 12: Finalize Composition and Config Hygiene (Compatibility Path)

Objective:
- Complete composition cleanup while still honoring compatibility in `models/`.

Scope:
1. Add `templates/strategy_config.py` for centralized defaults (if not already present).
2. Keep `main.py` as composition root.
3. Clean imports and module boundaries.
4. Ensure `models/__init__.py` exports remain unchanged for compatibility.
5. Update `claude.md` structure docs to reflect new domains and adapter role.

Important conflict resolution:
- CC suggested deleting `models/` in this stage.
- GPT constraints prefer compatibility retention.
- Master plan keeps `models/` adapters through mandatory path.

Exit criteria:
- cloud parity unchanged.
- docs updated.
- composition boundary clean and explicit.

Commit:
- `phase-12: finalize composition boundaries and compatibility adapters`

---

### Phase 13: Adopt Typed Dataclasses Internally

Objective:
- Replace internal dict-heavy flow with typed dataclasses while preserving output schemas.

Scope:
1. Signal flow transitions to `Signal` dataclass.
2. Target-state flow transitions to `TargetState`.
3. Logging methods accept dataclasses where appropriate.
4. CSV builder supports dict and dataclass input while output remains unchanged.
5. Optional internal execution tracking consolidation using `OrderRecord`.

Behavior guardrails:
- CSV files must be schema-identical and value-equivalent.
- dataclass adoption must not change ordering, field defaults, or serialization semantics.

Exit criteria:
- cloud parity unchanged.
- type-driven internal flow in place.

Commit:
- `phase-13: adopt typed dataclasses for internal data flow`

---

### Phase 14: Optional Hard Cutover (Remove `models/`)

Objective:
- Complete CC end-state by removing compatibility adapters.

Precondition:
- Explicit approval to break compatibility layer.
- All prior phases pass parity and remain stable for at least one clean rerun.

Scope:
1. Rewire `main.py` imports to:
   - `from core import DOW30`
   - `from signals import CompositeTrendAlphaModel`
   - `from risk import TargetVolPortfolioConstructionModel`
   - `from execution import SignalStrengthExecutionModel`
   - `from loggers import PortfolioLogger`
2. Remove `models/` directory.
3. Update docs accordingly.

Risk:
- import path/circular dependency regressions are most likely here.

Exit criteria:
- cloud parity unchanged.
- no import breakages.

Commit:
- `phase-14: optional hard cutover remove models compatibility layer`

---

### Phase 15: Final Certification and Closeout

Objective:
- certify refactor completion and produce release-ready evidence.

Closeout checklist:
1. Run one final cloud backtest with final phase name.
2. Rebuild metrics/hash and compare to baseline.
3. Verify import-policy compliance manually.
4. Verify no schema drift across all ObjectStore CSV outputs.
5. Verify stale-cancel week_id behavior via order_events data.
6. Verify docs:
   - `claude.md`
   - this master plan status table
7. Tag final pass commit.

Final tag:
- `atomic-refactor-final-pass`

Commit:
- `phase-15: final certification and documentation closeout`

---

## 8. Regression Triage Protocol (If Any Gate Fails)

Immediate actions:
1. Stop progression to next phase.
2. Compare baseline and candidate summaries.
3. Check exact-match failures first:
   - missing files
   - row count drift
   - date misalignment
   - symbol-set mismatches
4. Then inspect tolerant float deltas.

Common root causes:
- float precision drift in extracted functions
- altered order of constraints
- list conversion from `RollingWindow` losing ordering/coverage
- implicit default changes during dataclass migration
- tag format parser mismatch
- import cycles or wrong module resolution in cloud packager

Recovery strategy:
1. Fix forward in new commit if issue is isolated.
2. If issue is broad, `git revert <phase_commit_sha>`.
3. Re-run the same phase until pass.
4. Tag pass commit only when gate is clean.

---

## 9. Cloud Run Budget and Timeline

Planned minimum cloud runs:
- Phase 00 baseline: 1
- Phases 01 through 13: 13
- Phase 14 optional cutover: 1 optional
- Phase 15 final certification: 1

Total:
- Mandatory path: 15 runs
- With optional cutover: 16 runs

Pragmatic adjustment:
- If a phase has no runtime wiring changes (for example, pure extraction with no imports consumed yet), you may bundle two adjacent non-wiring phases into one run, but only if:
  - file-level changes are low-risk
  - parity script outputs are clean locally
  - rollback blast radius stays acceptable

---

## 10. Commit and PR Checklist (Per Phase)

Before commit:
1. Read modified files and confirm no accidental drift.
2. Run local compile.
3. Confirm no invariant changes.
4. Confirm schema-preserving behavior.

Commit:
- one phase per commit
- include phase id in commit message
- avoid unrelated file churn

After commit:
1. Cloud run.
2. Pull ObjectStore artifacts.
3. Build metrics/hash.
4. Compare to baseline.
5. Tag pass.

---

## 11. Phase Tracking Template

Use this table in a tracking file (for example `backtests/atomic_refactor/progress.md`):

```markdown
| Phase | Name | Code Complete | Cloud Complete | Parity Pass | Tag | Notes |
|------:|------|---------------|----------------|------------|-----|-------|
| 00 | baseline | yes/no | yes/no | yes/no | atomic-phase-00-pass | |
| 01 | parity_tooling | yes/no | yes/no | yes/no | atomic-phase-01-pass | |
| 02 | structure_atoms | yes/no | yes/no | yes/no | atomic-phase-02-pass | |
| 03 | math_extraction | yes/no | yes/no | yes/no | atomic-phase-03-pass | |
| 04 | formatting_extraction | yes/no | yes/no | yes/no | atomic-phase-04-pass | |
| 05 | alpha_wiring | yes/no | yes/no | yes/no | atomic-phase-05-pass | |
| 06 | portfolio_wiring | yes/no | yes/no | yes/no | atomic-phase-06-pass | |
| 07 | execution_wiring | yes/no | yes/no | yes/no | atomic-phase-07-pass | |
| 08 | logger_domain | yes/no | yes/no | yes/no | atomic-phase-08-pass | |
| 09 | signals_domain | yes/no | yes/no | yes/no | atomic-phase-09-pass | |
| 10 | risk_domain | yes/no | yes/no | yes/no | atomic-phase-10-pass | |
| 11 | execution_domain | yes/no | yes/no | yes/no | atomic-phase-11-pass | |
| 12 | composition_finalize | yes/no | yes/no | yes/no | atomic-phase-12-pass | |
| 13 | typed_dataclasses | yes/no | yes/no | yes/no | atomic-phase-13-pass | |
| 14 | optional_models_removal | yes/no | yes/no | yes/no | atomic-phase-14-pass | optional |
| 15 | final_certification | yes/no | yes/no | yes/no | atomic-refactor-final-pass | |
```

---

## 12. Quick Command Blocks by Phase

Replace `XX_name` and `PXX-NAME` per phase.

Preparation:
```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
mkdir -p backtests/atomic_refactor/phase_XX_name/objectstore
mkdir -p backtests/atomic_refactor/phase_XX_name/metrics
python -m py_compile main.py models/*.py
python -m py_compile core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py tools/parity/*.py
```

Cloud run:
```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic-PXX-NAME-$(date +%Y%m%d-%H%M%S)"
```

Artifact fetch:
```bash
lean cloud object-store get \
  wolfpack/daily_snapshots.csv \
  wolfpack/positions.csv \
  wolfpack/signals.csv \
  wolfpack/slippage.csv \
  wolfpack/trades.csv \
  wolfpack/targets.csv \
  wolfpack/order_events.csv \
  --destination-folder "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtests/atomic_refactor/phase_XX_name/objectstore"
```

Metrics and compare:
```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
python tools/parity/metrics_from_csv.py \
  --input-dir backtests/atomic_refactor/phase_XX_name/objectstore \
  --output backtests/atomic_refactor/phase_XX_name/metrics/summary.json

python tools/parity/hash_manifest.py \
  --input-dir backtests/atomic_refactor/phase_XX_name/objectstore \
  --output backtests/atomic_refactor/phase_XX_name/metrics/hash_manifest.json

python tools/parity/compare_metrics.py \
  --baseline backtests/atomic_refactor/phase_00_baseline/metrics/summary.json \
  --candidate backtests/atomic_refactor/phase_XX_name/metrics/summary.json \
  --mode tolerant
```

---

## 13. Definition of Done

Refactor is complete when:
1. Mandatory phases 00 through 13 and 15 all pass parity gates.
2. No invariant in `AGENTS.md` has changed.
3. ObjectStore outputs retain key names and schema.
4. Import graph follows defined layering.
5. `main.py` remains clean composition root.
6. Documentation reflects actual structure and migration status.

Optional extra completion:
- Phase 14 completed and approved, removing compatibility adapters.

---

## 14. Leadership Decision Record

Decision 1:
- Keep compatibility adapters in `models/` through mandatory path.
- Reason: safest execution path, aligns with GPT constraints and minimizes migration risk.

Decision 2:
- Adopt full domain structure and molecule/organism decomposition.
- Reason: aligns with CC long-term maintainability goals.

Decision 3:
- Enforce script-driven parity checks, not manual metric inspection only.
- Reason: objective, reproducible regression control.

Decision 4:
- Make `models/` removal an explicit optional phase.
- Reason: resolves direct contradiction between source plans without blocking progress.

---

## 15. Immediate Next Action

Start with Phase 00 baseline capture and produce:
- `backtests/atomic_refactor/phase_00_baseline/objectstore/*`
- `backtests/atomic_refactor/phase_00_baseline/metrics/summary.json`
- `backtests/atomic_refactor/phase_00_baseline/metrics/hash_manifest.json`

Then execute Phase 01 tooling before any model rewiring.
