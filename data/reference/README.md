# Reference Data — LLM Chess Engine Research

> **⚠️ This directory contains sanitized research reference data only.**
> These files are NOT personal runtime logs — they are historical experiment
> results retained for reproducibility and comparison.

## Contents

| File | Rows | Description |
|:-----|:-----|:------------|
| `llm_research_log.csv` | 464 | Telemetry from 3 original tournaments (T1–T3). Schema: Timestamp, FEN, Temperature, Latency_ms, Extracted_Move, Is_Legal, Fallback_Used, Raw_Output |
| `llm_hallucinations.csv` | 298 | GUI-captured illegal-move errors (pre-constraint era). Schema: Timestamp, Game_Number, Turn_Number, FEN, Error_Message |

## Provenance

- **Tournament 1** (2026-02-21): Temp=0.1, no legal-move constraint → 49.5% legal rate
- **Tournament 2** (2026-02-22): Temp=0.8, no legal-move constraint → 43.0% legal rate
- **Tournament 3** (2026-02-24): Temp=0.8, with legal-move constraint → 97.4% legal rate

## What was removed

- No personal identifiers were present in the original telemetry.
- Root-level duplicate CSV (`llm_research_log.csv`) and generated chart
  (`llm_analysis_charts.png`) were removed from git tracking.
- New runtime data is written to `runs/` (git-ignored) and is never committed.

## Usage

These files serve as a **baseline reference** for comparing new experiment runs.
The analysis scripts can optionally load them alongside fresh run data to show
historical context. They are **not** loaded automatically — the user must
explicitly opt in via `--include-reference` flags.
