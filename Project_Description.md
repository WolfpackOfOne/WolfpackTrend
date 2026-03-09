# WolfpackTrend Project Assignment

## Table of Contents

- [Overview](#overview)
- [Project Selection](#project-selection)
- [Milestone 1: Project Proposal (Week 2)](#milestone-1-project-proposal-week-2--1-2-minutes)
- [Milestone 2: Final Presentation](#milestone-2-final-presentation-5-10-minutes)
  - [Backtest Requirements](#backtest-requirements)
- [Deliverables](#deliverables)
- [Presentation Format](#presentation-format-5-10-minutes)
- [Evaluation Criteria](#evaluation-criteria)

---

## Overview

In teams of 2-3, you will select one project from the [Project Ideas list](Project_Ideas.md), modify the WolfpackTrend codebase, run backtests across four different market environments, and deliver a 5-10 minute team presentation explaining your changes and findings.

---

## Project Selection

Choose any one project from the 30 options in `Project_Ideas.md`. Projects are organized by difficulty:

- **Easy (E1-E10)** — Parameter and universe changes. No new classes or logic required.
- **Medium (M1-M11)** — Logic and model changes. Typically involves editing one model file plus `main.py`.
- **Hard (H1-H10)** — Architectural and research-intensive changes across multiple files.

All difficulty levels are open to all teams.

---

## Milestone 1: Project Proposal (Week 2) — 1-2 minutes

Each team delivers a brief presentation introducing their chosen project. No code changes are required at this stage.

**What to cover:**
- Which project you selected (e.g., "E3 — Adjust Signal Temperature")
- What the modification does in plain terms
- Which files in the codebase you will be working with and where the relevant logic lives
- Your initial hypothesis — what do you expect to happen and why?

**Purpose:** Confirm your team has read the codebase, understands the project scope, and has a clear starting point.

---

## Milestone 2: Final Presentation (5-10 minutes)

### Backtest Requirements

Run **4 backtests**, each covering a different **2-year period**:

| Period Type | Count | Description |
|-------------|-------|-------------|
| Normal market | 2 | Periods without a major crisis or dislocation |
| Major market event | 2 | Periods containing a significant market event (e.g., 2008 Financial Crisis, 2020 COVID crash, 2000 dot-com bust, 2022 rate shock) |

**Guidelines:**
- You choose your own 2-year windows — justify why you selected each one
- Keep all parameters identical across runs except the start and end dates
- Run both the **baseline** (unmodified) strategy and your **modified** strategy for each period
- A comparison notebook will be provided to generate results from the ObjectStore logs

---

## Deliverables

### 1. Code Changes
- Clearly identify which files you modified and what you changed
- Explain the purpose of each change

### 2. Hypothesis
- State what you expect to happen and why
- Be specific: which metrics do you expect to improve or degrade?

### 3. Results Summary
Provide a table of key metrics for baseline vs. modified strategy across all 4 periods:

| Metric | Period 1 (Normal) | Period 2 (Normal) | Period 3 (Crisis) | Period 4 (Crisis) |
|--------|-------------------|-------------------|--------------------|--------------------|
| Total Return | | | | |
| Sharpe Ratio | | | | |
| Sortino Ratio | | | | |
| Calmar Ratio | | | | |
| Max Drawdown | | | | |

### 4. Deep Dive
Select the most interesting period and analyze the results in detail. Why did your modification produce the outcome it did? Reference specific market conditions, signal behavior, or portfolio dynamics.

### 5. Crisis vs. Normal Analysis (Required)
Dedicate a section of your presentation to explaining **why** your modification performed differently during crisis periods compared to normal periods. Consider:
- How did market conditions interact with your change?
- Did your modification amplify or dampen the strategy's response to stress?
- What does this reveal about the robustness of your approach?

---

## Presentation Format (5-10 minutes)

| Section | Time | Content |
|---------|------|---------|
| Hypothesis & motivation | ~1 min | What you changed, what you expected, and why |
| Implementation walkthrough | ~2-3 min | Walk through the code changes — what files, what logic |
| Results across 4 periods | ~2-3 min | Summary table + deep dive on the most interesting period |
| Crisis vs. normal analysis | ~1-2 min | Why did performance differ across market regimes? |
| Q&A | ~1-2 min | Questions from the class |

---

## Evaluation Criteria

| Criterion | What We're Looking For |
|-----------|----------------------|
| **Hypothesis** | Clear, specific, and testable — not vague |
| **Code quality** | Correct, minimal, well-integrated with the existing codebase |
| **Results analysis** | Depth of reasoning about *why* results occurred, not just reporting numbers |
| **Crisis vs. normal insight** | Thoughtful explanation of regime-dependent behavior |
| **Limitations** | Honest assessment of tradeoffs, risks, and caveats |
| **Presentation** | Clear, concise, well-organized, good use of the time |
