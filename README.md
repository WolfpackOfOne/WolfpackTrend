# WolfpackTrend

Modular trend-following equity strategy built on QuantConnect LEAN.

## Quick Start (6 Commands)

```bash
mkdir -p "$HOME/Documents/QuantConnect/MyProjects"
cd "$HOME/Documents/QuantConnect"
python3 -m venv venv && source venv/bin/activate
pip install --upgrade pip && pip install lean
cd "$HOME/Documents/QuantConnect/MyProjects" && git clone https://github.com/<your-org>/<your-repo>.git "<qc-project-dir>" && cd "<qc-project-dir>"
lean login && lean cloud pull --project "<qc-project-name>" && lean cloud backtest "<qc-project-name>" --name "Smoke test"
```

## Quick Start (Windows PowerShell, 6 Commands)

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\Documents\QuantConnect\MyProjects"
Set-Location "$HOME\Documents\QuantConnect"
python -m venv venv; .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip; python -m pip install lean
Set-Location "$HOME\Documents\QuantConnect\MyProjects"; git clone https://github.com/<your-org>/<your-repo>.git "<qc-project-dir>"; Set-Location "<qc-project-dir>"
lean login; lean cloud pull --project "<qc-project-name>"; lean cloud backtest "<qc-project-name>" --name "Smoke test"
```

## What This Repository Contains

- `main.py`: algorithm composition root (`WolfpackTrendAlgorithm`)
- `models/`: framework-facing model adapters
- `core/`, `signals/`, `risk/`, `execution/`, `loggers/`: domain modules
- `shared/`: shared utilities (universe definitions)
- `templates/`: strategy configuration templates
- `tools/`: developer utilities (parity comparison)
- `research/`: Jupyter notebooks for analysis
- `docs/`: architecture, strategy, development, parity, and ObjectStore docs

## Prerequisites

- Python 3
- Git
- QuantConnect account
- QuantConnect API credentials (for CLI login)

## 0. First-Time Setup on a New Machine

```bash
mkdir -p "$HOME/Documents/QuantConnect/MyProjects"
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

The `git config` values are required so commits are attributed correctly.

## 1. Create and Activate a Virtual Environment

```bash
cd "$HOME/Documents/QuantConnect"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install lean
```

## 2. Connect to QuantConnect via LEAN CLI

```bash
lean login
lean whoami
```

`lean login` prompts for your QuantConnect credentials/API token and stores them in your local LEAN config.

## 3. Clone the Repository (First Time)

```bash
cd "$HOME/Documents/QuantConnect/MyProjects"
git clone https://github.com/<your-org>/<your-repo>.git "<qc-project-dir>"
cd "<qc-project-dir>"
```

## 4. Create a New GitHub Repository for Your Copy (Optional)

If you want this project under your own GitHub repository after cloning it:

1. In GitHub, create a new empty repository (do not add README, `.gitignore`, or license files).
2. In your local clone, run:

```bash
cd "$HOME/Documents/QuantConnect/MyProjects/<qc-project-dir>"
git remote rename origin upstream
git remote add origin git@github.com:<your-org>/<your-new-repo>.git
# OR: git remote add origin https://github.com/<your-org>/<your-new-repo>.git
git push -u origin main
```

3. Confirm remotes:

```bash
git remote -v
```

`upstream` points to the original source repo, and `origin` points to your new repo.

## 5. Sync With QuantConnect Cloud Project

Use your QuantConnect cloud project name:

```bash
lean cloud pull --project "<qc-project-name>"
```

If you are pushing local changes:

```bash
lean cloud push --project "<qc-project-name>" --force
```

## 6. Run Local Validation

```bash
python -m py_compile main.py
for f in models/*.py core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py shared/*.py templates/*.py; do
    python -m py_compile "$f"
done
```

## 7. Run a Cloud Backtest

```bash
lean cloud backtest "<qc-project-name>" --name "Smoke test"
```

Cloud backtests are the authoritative source of results for this strategy.

## Daily Workflow

```bash
cd "$HOME/Documents/QuantConnect"
source venv/bin/activate
cd MyProjects/"<qc-project-dir>"

# edit code
python -m py_compile main.py
for f in models/*.py core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py shared/*.py templates/*.py; do
    python -m py_compile "$f"
done
lean cloud push --project "<qc-project-name>" --force
lean cloud backtest "<qc-project-name>" --name "Update description"
```

## Files That Should Stay Untracked

The repository ignores environment-specific artifacts such as:

- `config.json`
- `backtests/`
- `live/`
- `.lean/`
- `.claude/`
- `__pycache__/`
- `claude.md`

## Algorithm Flow

```mermaid
flowchart TD
    subgraph INIT["Initialize"]
        A[30 DJIA Stocks<br/>Daily Resolution] --> B[252-Day Warmup]
        B --> C[Wire Alpha → PCM → Execution]
    end

    subgraph DAILY["Every Trading Day"]
        D[Market Open] --> E[Cancel Stale Orders]
        E --> F[OnData]
        F --> G[Update 63-Day<br/>Rolling Returns]
        F --> H[Log Daily Snapshot]
    end

    subgraph ALPHA["Alpha Model — Every 5 Days"]
        I[Compute Signals<br/>per Symbol] --> J{All 3 SMAs<br/>agree on<br/>direction?}
        J -- No --> K[No Signal]
        J -- Yes --> L["Weighted Score<br/>0.2×SMA20 + 0.5×SMA63 + 0.3×SMA252<br/>(ATR-normalised)"]
        L --> M["tanh compression<br/>→ magnitude ∈ (-1,+1)"]
        M --> N{|mag| ≥ 0.05?}
        N -- No --> K
        N -- Yes --> O[Emit Insight<br/>Up / Down]
    end

    subgraph PCM["Portfolio Construction"]
        O --> P[Normalise Weights<br/>by Signal Magnitude]
        P --> Q["Vol-Scale to 10%<br/>Target Volatility"]
        Q --> R["Apply Constraints<br/>±10% per name<br/>150% gross · 50% net"]
        R --> S{Classify Each Symbol}
        S --> S1[NEW_ENTRY<br/>Start 5-day scale-in]
        S --> S2[FLIP<br/>Exit → scale-in next day]
        S --> S3[RESIZE<br/>Jump to new weight]
        S --> S4[HOLD<br/>Inside 1.5% dead-band]
        S --> S5[EXIT<br/>Close position]
    end

    subgraph EXEC["Execution Model"]
        S1 & S2 & S3 & S5 --> T{Signal Strength}
        T -- "Exit" --> U[Market Order]
        T -- "Strong ≥ 0.70" --> V[Limit @ market]
        T -- "Moderate ≥ 0.30" --> W[Limit 0.5% passive]
        T -- "Weak < 0.30" --> X[Limit 1.5% passive]
    end

    subgraph SCALE["Non-Rebalance Days (1-4)"]
        Y[Re-emit Cached Signals] --> Z[Advance Scale Day]
        Z --> AA[Emit Partial Target<br/>per Scaling Schedule]
    end

    INIT --> DAILY
    DAILY --> ALPHA
    ALPHA --> PCM
    PCM --> EXEC
    S4 -. "No order" .-> SCALE
    EXEC --> SCALE
```

## Documentation

- `docs/strategy.md`
- `docs/architecture.md`
- `docs/development.md`
- `docs/objectstore.md`
- `docs/parity.md`
