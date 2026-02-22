# Development Workflow

## Prerequisites

- Python 3 with `lean` CLI installed
- QuantConnect account with API credentials
- Git configured for GitHub access

## Environment Setup

```bash
cd ~/Documents/QuantConnect
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install lean
lean login
```

## Three-System Sync

The project lives in three independent systems that must be kept in sync:

| System | Location | Purpose |
|--------|----------|---------|
| Local Git | `.git/` in project directory | Version control |
| GitHub | `WolfpackOfOne/WolfpackTrend` | Remote backup, collaboration |
| QC Cloud | WolfpackTrend 1 project | Backtest execution (full data) |

Git and QC Cloud are **independent**. Pushing to one does not update the other.

## Daily Workflow

### 1. Activate Environment

```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
```

### 2. Make Changes

Edit files in `WolfpackTrend 1/`. The composition root is `main.py`.

### 3. Compile Check

```bash
cd "WolfpackTrend 1"
python -m py_compile main.py
for f in models/*.py core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py; do
    python -m py_compile "$f"
done
```

### 4. Push to QC Cloud and Backtest

```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Description of run"
```

Use `--force` if you get a collaboration lock error.

### 5. Commit to Git

```bash
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
git add <files>
git commit -m "Description of changes"
git push
```

### 6. Pull from Cloud (if needed)

```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud pull --project "WolfpackTrend 1"
```

## Cloud vs Local Backtests

**Always use cloud backtests** for authoritative results. The cloud has full market data access. Local backtests may fail due to missing data.

## Files NOT Tracked in Git

These are in `.gitignore`:

- `config.json` - Contains QC organization/cloud project IDs
- `backtests/` - Backtest artifacts (regeneratable)
- `__pycache__/` - Python cache
- `.DS_Store` - macOS metadata
- `.lean/` - LEAN CLI cache
- `live/` - Live trading artifacts

## Branching

- `main` - Default branch, stable
- Feature branches for development (e.g., `Atomic_Refactor`)
- Merge to main after verification via cloud backtest

## Verification

For any code change, verify with:

1. **Compile check** - All `.py` files compile without errors
2. **Cloud backtest** - Run on QC cloud and confirm expected behavior
3. **Parity check** (for refactors) - Use parity tools to verify exact metric match (see [parity.md](parity.md))
