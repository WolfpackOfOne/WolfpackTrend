# Dow 30 Trend (Alpha → Portfolio Construction → Execution) in QuantConnect LEAN  
**Goal:** A simple, modular **trend-following** strategy using the **Dow 30** stocks, implemented with LEAN’s model architecture:  
- **Alpha Model**: emits *direction + magnitude* signals using short/medium/long trend horizons  
- **Portfolio Construction**: converts signals into target weights, **targets 10% annualized portfolio volatility**, and enforces **gross/net exposure caps**  
- **Execution**: places **market orders** (simple baseline)

You’ll be able to:
1) **Run locally** with the LEAN CLI (fast iteration)  
2) **Commit and run in QuantConnect Cloud** (LEAN Cloud backtesting/live)

This document is written as instructions you can hand directly to **Claude Code** to implement.

---

## 0) What you are building (spec)

### Universe
- **Static basket**: the **Dow 30** tickers (defined explicitly in code; no dynamic universe)

### Data / Resolution
- **Daily bars** for all equities

### Signal (Trend definition)
You want **3 horizons**:
- Short = **20** trading days  
- Medium = **63** trading days  
- Long = **252** trading days

For each symbol and each horizon `h`, compute:
- `dist_h = (price - SMA(h)) / ATR(14)`

Then compute a composite score:
- `score = 0.5*dist_short + 0.3*dist_medium + 0.2*dist_long`

Convert to a smooth bounded magnitude:
- `mag = tanh(score)`  → in `(-1, +1)`

Signal:
- **Direction**: Up if `mag > 0`, Down if `mag < 0`
- **Magnitude**: `abs(mag)`

Skip tiny signals to reduce churn:
- if `abs(mag) < 0.05`: emit no insight for that symbol today

Emit insights:
- Frequency: **daily**
- Horizon: `timedelta(days=1)` is fine for daily rebalancing
- Provide `weight=abs(mag)` and `confidence=abs(mag)`

### Portfolio construction
Given the set of daily insights:
1) Convert insight directions/weights into raw signed scores:
   - `raw_weight_i = sign_i * insight_weight_i`
2) Normalize into **unit gross**:
   - `raw_weight_i /= sum(abs(raw_weight_j))`
3) Estimate portfolio volatility using a **diagonal approximation**:
   - Maintain rolling daily returns per symbol over `vol_lookback=63`
   - Compute per-symbol daily stdev `sigma_i`
   - Portfolio daily variance:
     - `var_p = sum( (w_i^2) * (sigma_i^2) )`
   - Annual vol:
     - `vol_annual = sqrt(var_p) * sqrt(252)`
4) Scale the whole portfolio to hit **target_vol = 10% annualized**:
   - `scale = target_vol / vol_annual`
   - `w_i *= scale`
5) Enforce constraints:
   - **Max gross exposure**: 1.5  
   - **Max absolute net exposure**: 0.5  
   - **Max absolute per-name weight**: 0.10 (10% cap per stock)

Finally output `PortfolioTarget.Percent(symbol, w_i)`.

### Execution
- Use **ImmediateExecutionModel()** for now (market orders)

### Benchmark
- Benchmark = **SPY**

### Backtest window
- **1 year** (choose explicit dates in code for reproducibility; you can change quickly)

---

## 1) Repo + file layout (recommended)

A clean layout that works for:
- Local LEAN CLI runs
- QuantConnect Cloud sync
- Claude Code edits

Suggested structure:

```
qc-dow30-trend/
├── README.md
├── .gitignore
├── lean.json
├── requirements.txt               # optional (LEAN usually handles python packages)
└── Dow30Trend/
    ├── main.py                    # algorithm entrypoint (QC calls this file)
    └── models/
        ├── __init__.py
        ├── alpha.py               # CompositeTrendAlphaModel
        ├── portfolio.py           # TargetVolPortfolioConstructionModel
        └── universe.py            # Dow 30 tickers constant
```

Why split like this?
- **main.py** is small and readable (wiring only)
- Models are isolated, easy to test/iterate
- The same code runs locally and in the cloud

> If you prefer single-file for QC convenience, you *can* put everything in `main.py`.  
> But the above multi-file layout is still LEAN-compatible as long as imports are correct.

---

## 2) Local LEAN CLI setup (run locally)

### 2.1 Install LEAN CLI
If you haven’t already:

- Install Docker (needed for LEAN local runs)
- Install LEAN CLI:
  - `pip install lean`

Verify:
- `lean --version`

### 2.2 Initialize project config
From the repo root:

- `lean init`

This creates/updates `lean.json`.

### 2.3 Create a QuantConnect project for local runs
Create a project folder named `Dow30Trend`:

- `lean create-project "Dow30Trend" --language python`

This will create a folder with a starter `main.py`.

We will replace that content.

### 2.4 Run locally
From repo root:

- `lean backtest "Dow30Trend"`

LEAN will run the backtest locally via Docker and produce results in:
- `./.lean/` (and output logs)

---

## 3) QuantConnect Cloud setup (commit + run in cloud)

You want to “commit via LEAN cloud” (QuantConnect Cloud). The LEAN CLI supports syncing.

### 3.1 Authenticate
From repo root:

- `lean login`

Follow prompts (QuantConnect credentials/token).

### 3.2 Create cloud project (if not created)
If you haven’t created it in the cloud yet:

- `lean cloud create-project "Dow30Trend" --language python`

(or use the QC web UI to create, then you can link/sync)

### 3.3 Push local code to the cloud project
- `lean cloud push --project "Dow30Trend"`

### 3.4 Run a cloud backtest
- `lean cloud backtest --project "Dow30Trend"`

This is useful to confirm that:
- imports work in cloud environment
- the project is properly linked

> Tip: Keep your local and cloud project names identical to reduce confusion.

---

## 4) Implementation instructions for Claude Code (VERY explicit)

### 4.1 Create `Dow30Trend/models/universe.py`
Define the Dow 30 tickers explicitly:

```python
DOW30 = [
    "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM",
    "CSCO", "CVX", "DIS", "DOW", "GS", "HD",
    "HON", "IBM", "INTC", "JNJ", "JPM", "KO",
    "MCD", "MMM", "MRK", "MSFT", "NKE", "PG",
    "TRV", "UNH", "V", "VZ", "WBA", "WMT"
]
```

### 4.2 Create `Dow30Trend/models/alpha.py`
Implement `CompositeTrendAlphaModel(AlphaModel)`:

**State per symbol:**
- SMA(20), SMA(63), SMA(252)
- ATR(14)

**OnSecuritiesChanged:**
- For added securities:
  - create indicators via `algorithm.SMA(...)` and `algorithm.ATR(...)`
  - store in dictionaries keyed by symbol
- For removed:
  - delete from dicts

**Update():**
- Emit at most once per day:
  - track `last_emit_date`
- For each symbol:
  - require all indicators ready
  - require bar present in `data.Bars`
  - compute:
    - `dist_short = (price - smaS) / atr`
    - `dist_med = (price - smaM) / atr`
    - `dist_long = (price - smaL) / atr`
  - compute `score = 0.5*dist_short + 0.3*dist_med + 0.2*dist_long`
  - compute `mag = tanh(score)`
  - if `abs(mag) < 0.05`: skip
  - direction:
    - Up if `mag > 0` else Down
  - emit:
    - `Insight.Price(symbol, timedelta(days=1), direction, weight=abs(mag), confidence=abs(mag))`

**Important implementation notes:**
- Use `max(atr_value, 1e-8)` to avoid divide-by-zero
- Use `math.tanh`

### 4.3 Create `Dow30Trend/models/portfolio.py`
Implement `TargetVolPortfolioConstructionModel(PortfolioConstructionModel)` with these parameters:
- `target_vol_annual = 0.10`
- `max_gross = 1.50`
- `max_net = 0.50`
- `max_weight = 0.10`
- `vol_lookback = 63`

**Performance requirement:**
- Do NOT call `History()` inside `CreateTargets()` daily.
- Maintain rolling returns incrementally.

**State per symbol:**
- `RollingWindow[float]` of length `vol_lookback` for daily returns
- `prev_close[symbol]` for return calculation

**Method `UpdateReturns(algorithm, data)`:**
- For each tracked symbol:
  - if bar exists in `data.Bars`:
    - if prev_close exists: compute daily return `close/prev_close - 1`
    - add to rolling window
    - update prev_close

**Method `CreateTargets(algorithm, insights)`:**
1) Convert insights → signed weights
2) Normalize to unit gross
3) Estimate annual vol using diagonal approximation:
   - compute each symbol’s daily stdev from its rolling window (require at least 20 obs)
   - compute portfolio daily variance and annualize
4) Scale to target vol:
   - if vol estimate missing, use scale=1 (or skip targeting until ready)
5) Apply per-name cap first:
   - clip each weight to [-0.10, +0.10]
6) Apply gross cap:
   - if gross > 1.5, scale down
7) Apply net cap:
   - if abs(net) > 0.5, scale down proportionally
8) Output `PortfolioTarget.Percent(...)`

**Order of constraint application matters.**  
Use: per-name cap → gross cap → net cap.

> Net-capping by proportional scaling is a simple first pass.  
> A fancier approach would shift longs/shorts asymmetrically, but we keep it simple.

### 4.4 Create `Dow30Trend/main.py`
This file wires everything together.

Requirements:
- `SetStartDate`, `SetEndDate` for a 1-year window (pick explicit dates)
- `SetCash(100000)` (or any)
- `SetBenchmark("SPY")`
- Add all Dow 30 equities at daily resolution
- Instantiate and set:
  - Alpha model
  - Portfolio construction model (store reference so we can call `UpdateReturns`)
  - Execution model = `ImmediateExecutionModel()`

**Also ensure settings:**
- `self.Settings.RebalancePortfolioOnInsightChanges = True`
- `self.Settings.RebalancePortfolioOnSecurityChanges = True`

**In `OnData`:**
- call `self.pcm.UpdateReturns(self, data)` once per day (for daily bars, OnData is once per day)

---

## 5) Minimal “done” checklist (sanity checks)

When Claude finishes coding, verify:

### Local backtest
Run:
- `lean backtest "Dow30Trend"`

Confirm:
- No import errors
- Indicators warm up (initial period may have fewer trades until SMA(252) ready)
- Trades occur after warmup
- Gross and net exposure obey caps (inspect holdings / logs)

### Cloud backtest
Push then run:
- `lean cloud push --project "Dow30Trend"`
- `lean cloud backtest --project "Dow30Trend"`

Confirm same behavior.

---

## 6) Practical notes (things that WILL come up)

### 6.1 Warmup
SMA(252) needs ~252 daily bars to be ready. With a 1-year backtest window, you’ll have little or no time after warmup.

**Strong recommendation:**
- Either:
  1) Backtest 2+ years but evaluate last 1 year, OR  
  2) Use a shorter “long” horizon (e.g., 126) for the initial version

If you insist on exactly 1 year start-to-end, expect:
- long SMA may be barely ready
- signals will be delayed / reduced early

A clean compromise:
- Set start date 2 years back
- Use `self.SetWarmUp(252, Resolution.Daily)`
- In analysis, focus on last year

Tell Claude to implement `SetWarmUp(252, Resolution.Daily)`.

### 6.2 Long/short availability
Dow stocks are generally shortable in QC, but short availability can vary.
If shorts fail for some symbols:
- you’ll see rejected orders or no fills
- you can add a check:
  - `if not security.IsShortable: treat as long-only or skip`

For the MVP, ignore and observe logs.

### 6.3 Transaction costs / slippage
Default QC models may be optimistic. Later improvements:
- set realistic fee model
- add slippage model
But keep it simple for v1.

### 6.4 Rebalance frequency vs churn
Daily rebalancing can churn. You already reduced noise with:
- skip `abs(mag) < 0.05`
Next minimal churn control (optional later):
- only trade if target weight differs from current by > 1–2%

---

## 7) .gitignore (recommended)

Create `.gitignore` at repo root:

```
# LEAN outputs
.lean/
**/backtests/
**/live/
**/*.log

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.ipynb_checkpoints/

# OS
.DS_Store
Thumbs.db
```

---

## 8) What to ask Claude Code (copy/paste prompt)

Use this as your Claude Code instruction:

> Implement a QuantConnect LEAN Python algorithm called `Dow30Trend` using the attached spec.  
> Use a modular architecture: `CompositeTrendAlphaModel` (in models/alpha.py), `TargetVolPortfolioConstructionModel` (models/portfolio.py), a Dow30 tickers list (models/universe.py), and `main.py` that wires Alpha → PortfolioConstruction → ImmediateExecution.  
> Must run locally via `lean backtest` and sync to QuantConnect cloud via `lean cloud push/backtest`.  
> Enforce: target vol 10% annual, max gross 1.5, max abs net 0.5, max abs single-name 0.10.  
> Use daily data. Trend horizons 20/63/252, ATR(14) normalization, composite weights (0.5/0.3/0.2), magnitude = tanh(score), skip abs(mag) < 0.05.  
> Maintain rolling returns for volatility estimation (no History calls inside CreateTargets).  
> Add `SetWarmUp(252, Resolution.Daily)` and use a backtest window that includes enough warmup (2+ years), but we will evaluate last year.  
> Provide clean imports and ensure it runs in both local and cloud environments.

---

## 9) Optional next upgrade (don’t do yet)
Once v1 runs:
- add Top-N strongest signals filter
- add regime filter (e.g. SPY 200d MA)
- add turnover control band
- add covariance-based vol estimate

---

If you want, tell me your preferred explicit backtest dates (start/end) and I’ll edit the exact date block you should use.

---

## 10) Downloading Equity Price History via LEAN (Local Data Cache)

You **can and should** download the Dow 30 equity price history locally using the LEAN CLI.  
This allows:
- fast local backtests
- reproducible results
- offline research using the same data LEAN uses

LEAN stores data in a **local cache** and automatically uses it when running locally.

---

### 10.1 How LEAN stores equity data (mental model)

LEAN maintains a local data directory (do **not** commit this to git):

```
~/.lean/data/
└── equity/
    └── usa/
        └── daily/
            ├── aapl.zip
            ├── msft.zip
            ├── jpm.zip
            └── ...
```

Each ZIP contains a CSV with rows:

```
YYYYMMDD,open,high,low,close,volume
```

Once downloaded:
- **Local backtests automatically use it**
- **Cloud backtests ignore it** (QuantConnect Cloud has its own managed data)

---

### 10.2 Download Dow 30 daily price history

Run this once from your repo root (or anywhere):

```bash
lean data download \
  --asset-type Equity \
  --market USA \
  --resolution Daily \
  --tickers AAPL AMGN AXP BA CAT CRM CSCO CVX DIS DOW GS HD HON IBM INTC JNJ JPM KO MCD MMM MRK MSFT NKE PG TRV UNH V VZ WBA WMT
```

LEAN will:
- authenticate with QuantConnect
- download **full available daily history**
- cache it locally under `~/.lean/data/`

> You do **not** need to specify start/end dates — LEAN pulls all available data.

---

### 10.3 Verify the data exists

Check the directory:

```bash
ls ~/.lean/data/equity/usa/daily | head
```

Inspect one file:

```bash
unzip -l ~/.lean/data/equity/usa/daily/aapl.zip
```

You should see:
```
aapl.csv
```

---

### 10.4 Using the data in local backtests (automatic)

No code changes are required.

This already works:

```python
self.AddEquity("AAPL", Resolution.Daily)
```

When you run:

```bash
lean backtest "Dow30Trend"
```

LEAN will:
1. Check the local cache
2. Use the downloaded data if present
3. Fall back to cloud download only if missing

---

### 10.5 Warmup considerations (important for this strategy)

Your strategy uses:
- SMA(252)
- 63-day rolling volatility

Therefore you **must have enough history** before the evaluation window.

**Recommended setup:**
- Download full history (default behavior)
- In code:
  ```python
  self.SetWarmUp(252, Resolution.Daily)
  ```
- Backtest over **2+ years**
- Evaluate performance on the **last 1 year**

This avoids distorted early-period signals.

---

### 10.6 (Optional) Download higher-resolution data later

If you ever want intraday data:

```bash
lean data download \
  --asset-type Equity \
  --market USA \
  --resolution Minute \
  --tickers AAPL MSFT JPM
```

⚠️ Minute data is much larger.  
Daily data is **correct** for this trend strategy.

---

### 10.7 Using LEAN data outside LEAN (research notebooks)

LEAN data is plain CSV inside ZIP files and can be reused for research:

```python
import zipfile
import pandas as pd
from pathlib import Path

path = Path.home() / ".lean/data/equity/usa/daily/aapl.zip"

with zipfile.ZipFile(path) as z:
    with z.open("aapl.csv") as f:
        df = pd.read_csv(
            f,
            names=["date","open","high","low","close","volume"],
            parse_dates=["date"]
        )

df.head()
```

This is useful for:
- validating indicators
- checking volatility estimates
- debugging portfolio math outside LEAN

---

### 10.8 Git + cloud notes (read this once)

- ❌ Do **not** commit `.lean/data` to git  
- ✔ Local backtests use your downloaded data  
- ✔ Cloud backtests use QuantConnect-managed data  
- Small price/date differences between local and cloud are normal

Your existing `.gitignore` already handles this correctly.

---
