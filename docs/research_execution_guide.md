# Research Execution Guide: Standardizing LLM Chess Evaluation

This guide describes how to run the full LLM Chess Engine experiment matrix consisting of **100 games per condition** (300 games total), verify runtime logs, generate comparative reports, and present findings.

---

## Technical Architecture Overview

The testing framework employs a decoupled Python orchestrator (`scripts/run_game.py`) directly communicating with a local Ollama service. White plays random moves (ensuring variable board state branching), while Black queries the LLM under 3 distinct experimental setups:

```
                  ┌───────────────────────────────┐
                  │ scripts/run_experiment_matrix.sh │
                  └───────────────┬───────────────┘
                                  │ (Launches 3 conditions)
      ┌───────────────────────────┼───────────────────────────┐
      ▼ (Temp 0.2, Unconstrained) ▼ (Temp 0.8, Unconstrained) ▼ (Temp 0.8, Constrained)
┌───────────┐               ┌───────────┐               ┌───────────┐
│  Game 1-100 │             │  Game 1-100 │             │  Game 1-100 │
└─────┬─────┘               └─────┬─────┘               └─────┬─────┘
      │                           │                           │
      ├───────────────────────────┴───────────────────────────┤
      ▼ (Aggregated Telemetry Output)
  runs/<RUN_ID>/
    ├── config.resolved.json
    ├── raw_outputs.jsonl
    ├── metrics.json
    └── manifest.json
```

---

## Step 1: Pre-Execution Environment Verification

Before launching the 300-game matrix, runs must verify network configuration and model storage state.

1. Ensure the Ollama background service is running on the host or inside the containers.
2. Verify connectivity and model registry state:
   ```bash
   python scripts/check_ollama_env.py --model llama3.1
   ```
   If it reports `❌ NOT READY`, refer to [docs/runtime_modes_ollama.md](runtime_modes_ollama.md) for network routing rules.

---

## Step 2: Executing the 100-Game Experiment Matrix

Execute the matrix runner by specifying the target model and setting the size to `100` games per condition.

```bash
# Execute the full 300 game matrix (3 conditions * 100 games) using llama3.1
bash scripts/run_experiment_matrix.sh --model llama3.1 --num-games 100
```

### Parameter Controls
- **Seed (`--seed 42`)**: Automatically locked across all runs to ensure White's random moves are identical per game index, establishing a fair basis for baseline comparison.
- **Max Turn Cap**: Default caps game length at 200 ply (100 full moves) to prevent infinite loops.
- **Early Termination (`--early-termination`)**: Aborts the game immediately on the first illegal move (hallucination) or empty response. This matches the legacy GUI's automated test behavior and is **highly recommended for no-GPU laptops** to complete unconstrained runs in minutes rather than hours.
  ```bash
  # Run matrix with early termination for fast CPU execution
  bash scripts/run_experiment_matrix.sh --model llama3.1 --num-games 100 --early-termination
  ```

*Note: Depending on system CPU/GPU specifications under WSL, querying 100 games * ~40 turns per game may take several hours. You can monitor active folder counts in another shell:*
```bash
watch "ls -la runs/"
```

---

## Step 3: Running Telemetry Validation & Aggregation

Once the matrix execution finishes, the raw logs are located under `runs/`. The analyzer evaluates logs dynamically.

```bash
python scripts/analyze_all.py --run-root runs --out reports/experiment_matrix
```

The script performs two critical validation rules automatically:
1. **Schema Check**: Validates that all fields in `metrics.json` exist, conform to expected datatypes, and `legal_move_rate` falls between `0.0` and `1.0`.
2. **Duplicate Check**: Scans `raw_outputs.jsonl` to ensure no coordinate turn (game_id, turn_number) has been recorded twice.

---

## Step 4: Displaying and Visualizing Results

The results are generated in the output directory (e.g., `reports/experiment_matrix/`). To guide readers, structure your final reporting presentation as follows:

### 1. Tabular Summary (`metrics_comparison.csv`)
Presents hard metrics for rapid parsing:

| Tag | Temp | Constrained | Total Moves | Legal Moves | Legal Rate | Mean Latency | Unique Moves |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `t02_unconstrained` | 0.2 | No | 3,450 | 2,301 | **66.7%** | 4.6s | 45 |
| `t08_unconstrained` | 0.8 | No | 3,820 | 1,273 | **33.3%** | 4.8s | 23 |
| `t08_constrained` | 0.8 | Yes | 3,110 | 3,110 | **100.0%** | 11.1s | 112 |

### 2. Pairwise Delta Quadrants
Shows exact changes between conditions:
* **Constraint Efficacy**: Compares `t08_constrained` vs `t08_unconstrained` to demonstrate the percentage increase in move safety (e.g. `+66.7 percentage points`).
* **Randomness Penalty**: Compares `t02_unconstrained` vs `t08_unconstrained` to isolate temperature parameters.
* **Latency Overhead**: Computes the mean response time delta, illustrating the mathematical cost of JSON prompt parsing.

### 3. Matplotlib Visualizations (Saved in `plots/`)
- **`legal_rate_comparison.png`**: Vertical bar chart highlighting success percentages across the three groups.
- **`latency_comparison.png`**: Double bar chart comparing mean vs. median reaction times.
- **`move_diversity_comparison.png`**: Shows total unique moves proposed to determine if constraints limit creativity/diversity.

---

## Clean Repo Maintenance

To prevent committing large local cache folders to public GitHub:
- Do not remove files from `.gitignore` (which blocks `runs/`, `logs/`, `.env`).
- Commit only documentation modifications (`docs/`) and scripts (`scripts/`).
